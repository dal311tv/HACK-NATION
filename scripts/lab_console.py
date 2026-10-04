"""CRUCIBLE Lab Console: run the lab from a browser instead of the terminal.

Start it with:  uv run --python 3.12 scripts/lab_console.py
Then open:      http://127.0.0.1:8765

Standard library only. Binds to 127.0.0.1. Every action is a POST from this page; requests from
any other origin are rejected. The console never edits or deletes ledger entries: the only ledger
write it makes itself is a human approval, through crucible/approval.py.
"""
from __future__ import annotations

import html
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from collections import deque
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from crucible.approval import ApprovalError, approve_preregistration, is_approved  # noqa: E402
from crucible.ledger import read_entries, verify_chain  # noqa: E402

HOST, PORT = "127.0.0.1", 8765
ALLOWED_ORIGINS = {f"http://127.0.0.1:{PORT}", f"http://localhost:{PORT}"}
ALLOWED_HOSTS = {f"127.0.0.1:{PORT}", f"localhost:{PORT}"}
OMNIGENT_UI = "http://127.0.0.1:6767"

LEDGER_PATH = REPO_ROOT / "ledger" / "ledger.jsonl"
STOP_FILE = REPO_ROOT / "STOP"
ACTIONS_LOG = REPO_ROOT / "logs" / "console_actions.jsonl"
RUNS_DIR = REPO_ROOT / "logs" / "console_runs"
AGENT_COMMAND = ["omnigent", "run", "agents/crucible_lab.yaml", "-p"]
EXPLAIN_PROMPT = (
    "Do not run any phase. Using only read_ledger, explain step by step why {entry_id} was decided "
    "the way it was, citing ledger entry ids for every claim."
)
TAIL_LINES = 40
TERMINATE_GRACE_SECONDS = 5.0
MAX_BODY = 64 * 1024
SESSION_PREFIX = "Omnigent session:"
APPROVAL_FIELDS = [
    ("spec", "Candidate spec (what the agent-designed arm does)"),
    ("protocol_overrides", "Protocol overrides (changes to the human-set protocol)"),
    ("protocol", "Protocol"),
    ("success_criterion", "Success criterion"),
    ("decision_rules", "Decision rules (what each outcome will mean)"),
    ("limitations_declared", "Limitations declared"),
]
ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,100}$")
ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def record_action(action: str, **details) -> None:
    ACTIONS_LOG.parent.mkdir(parents=True, exist_ok=True)
    with ACTIONS_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"timestamp": utc_now(), "action": action, **details}) + "\n")


# ---------------------------------------------------------------- ledger (read-only views)

def ledger_view() -> dict:
    """Everything the page needs from the ledger. Reads only."""
    try:
        ok, message = verify_chain(LEDGER_PATH)
        entries = read_entries(LEDGER_PATH)
    except Exception as exc:  # unreadable ledger: show it, fail closed
        return {"ok": False, "message": f"ledger could not be read ({type(exc).__name__})", "entries": []}
    return {"ok": ok, "message": message, "entries": entries}


def has_run(entries: list[dict], prereg_id: str) -> bool:
    return any(
        e.get("type") == "run" and (e.get("id") == f"run-{prereg_id}" or prereg_id in e.get("parents", []))
        for e in entries
    )


def pending_preregistrations(entries: list[dict]) -> list[dict]:
    return [e for e in entries if e.get("type") == "preregistration" and not is_approved(entries, e["id"])]


def runnable_preregistrations(view: dict) -> list[dict]:
    if not view["ok"]:
        return []  # the blinding policy fails closed on a broken chain; so does the console
    entries = view["entries"]
    return [
        e for e in entries
        if e.get("type") == "preregistration" and is_approved(entries, e["id"]) and not has_run(entries, e["id"])
    ]


def decisions(entries: list[dict]) -> list[dict]:
    return [e for e in entries if e.get("type") == "decision"]


# ---------------------------------------------------------------- runs

class RunError(Exception):
    pass


def _descendants(root_pid: int) -> list[int]:
    """All descendant pids of root_pid, found with ps (children may have left the process group)."""
    try:
        out = subprocess.run(["ps", "-A", "-o", "pid=,ppid="], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    children: dict[int, list[int]] = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            children.setdefault(int(parts[1]), []).append(int(parts[0]))
    found, todo = [], [root_pid]
    while todo:
        for child in children.get(todo.pop(), []):
            if child not in found:
                found.append(child)
                todo.append(child)
    return found


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _wait_tree_exit(proc: subprocess.Popen, pids: list[int], timeout: float) -> bool:
    """Wait until the run and every listed child have exited. True if they all did within timeout."""
    deadline = time.monotonic() + timeout
    while True:
        if proc.poll() is not None and not any(_alive(pid) for pid in pids):
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.1)


def _signal_tree(pgid: int, pids: list[int], sig: int) -> None:
    try:
        os.killpg(pgid, sig)
    except (ProcessLookupError, PermissionError):
        pass
    for pid in pids:
        try:
            os.kill(pid, sig)
        except (ProcessLookupError, PermissionError):
            pass


class RunManager:
    """Runs one agent command at a time and keeps the tail of its output."""

    def __init__(self):
        self.lock = threading.Lock()
        self.proc: subprocess.Popen | None = None
        self.state = {"status": "idle"}
        self.tail: deque[str] = deque(maxlen=TAIL_LINES)

    def active(self) -> bool:
        with self.lock:
            return self.proc is not None and self.proc.poll() is None

    def start(self, label: str, prompt: str) -> None:
        with self.lock:
            if self.proc is not None and self.proc.poll() is None:
                raise RunError("Another run is still in progress. Only one run at a time is allowed.")
            if STOP_FILE.exists():
                raise RunError("The kill switch is ON (STOP file present). Press Resume first.")
            exe = shutil.which(AGENT_COMMAND[0])
            if exe is None:
                raise RunError(f"'{AGENT_COMMAND[0]}' was not found on PATH. Start the console from a terminal where it works.")
            cmd = [exe, *AGENT_COMMAND[1:], prompt]
            RUNS_DIR.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            log_path = RUNS_DIR / f"{stamp}.log"
            n = 1
            while log_path.exists():
                n += 1
                log_path = RUNS_DIR / f"{stamp}-{n}.log"
            env = dict(os.environ, PYTHONPATH=str(REPO_ROOT), PYTHONUNBUFFERED="1")
            log = log_path.open("w", encoding="utf-8")
            log.write(f"# {label}\n# started {utc_now()}\n# command: {' '.join(AGENT_COMMAND)} {json.dumps(prompt)}\n\n")
            log.flush()
            try:
                proc = subprocess.Popen(
                    cmd, cwd=REPO_ROOT, env=env, stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,  # Omnigent prints the session line on stderr
                    text=True, encoding="utf-8", errors="replace", bufsize=1,
                    start_new_session=True,  # own process group, so Stop can terminate the run and its children
                )
            except OSError as exc:
                log.write(f"# failed to start: {exc}\n")
                log.close()
                raise RunError(f"The command could not be started: {exc}") from exc
            self.proc = proc
            self.tail.clear()
            self.state = {
                "status": "running", "label": label, "prompt": prompt, "started": utc_now(),
                "finished": None, "exit_code": None, "session_url": None,
                "log_file": str(log_path.relative_to(REPO_ROOT)) if log_path.is_relative_to(REPO_ROOT) else str(log_path),
            }
        record_action("run_started", label=label, prompt=prompt, log_file=self.state["log_file"])
        threading.Thread(target=self._pump, args=(proc, log), daemon=True).start()

    def _pump(self, proc: subprocess.Popen, log) -> None:
        code = None
        try:
            for line in proc.stdout:
                log.write(line)
                log.flush()
                clean = ANSI_RE.sub("", line).rstrip("\r\n")
                with self.lock:
                    self.tail.append(clean)
                    stripped = clean.strip()
                    if stripped.startswith(SESSION_PREFIX) and self.state.get("session_url") is None:
                        self.state["session_url"] = stripped[len(SESSION_PREFIX):].strip()
            code = proc.wait()
            log.write(f"\n# finished {utc_now()} with exit code {code}\n")
        except Exception as exc:
            with self.lock:
                self.tail.append(f"[Lab Console] lost the output of this run: {exc!r}")
        finally:
            log.close()
        if code is None:
            code = proc.wait()
        with self.lock:
            stopped = bool(self.state.get("terminating"))
            self.state.update(status="stopped" if stopped else "finished", finished=utc_now(), exit_code=code)
            label = self.state.get("label")
        record_action("run_finished", label=label, exit_code=code, terminated_by_console=stopped)

    def terminate(self, reason: str) -> dict | None:
        """Terminate the active run and all its child processes. Returns what was done, or None if nothing ran."""
        with self.lock:
            proc = self.proc
            if proc is None or proc.poll() is not None:
                return None
            self.state["terminating"] = True
            label = self.state.get("label")
        pids = _descendants(proc.pid)
        _signal_tree(proc.pid, pids, signal.SIGTERM)
        forced = not _wait_tree_exit(proc, pids, TERMINATE_GRACE_SECONDS)
        if forced:
            pids += [pid for pid in _descendants(proc.pid) if pid not in pids]
            _signal_tree(proc.pid, pids, signal.SIGKILL)
            _wait_tree_exit(proc, pids, 5.0)
        result = {
            "label": label, "pid": proc.pid, "child_pids": pids, "forced_kill": forced,
            "exit_code": proc.poll(), "still_alive": [pid for pid in [proc.pid, *pids] if _alive(pid)],
        }
        with self.lock:
            self.state.update(terminated_at=utc_now(), terminated_reason=reason, forced_kill=forced)
        record_action("run_terminated", reason=reason, **result)
        return result

    def snapshot(self) -> dict:
        with self.lock:
            snap = dict(self.state)
            snap["active"] = self.proc is not None and self.proc.poll() is None
            snap["tail"] = list(self.tail)
        return snap


RUNS = RunManager()
APPROVAL_LOCK = threading.Lock()


# ---------------------------------------------------------------- actions

class ActionError(Exception):
    pass


def action_stop(_body: dict) -> dict:
    existed = STOP_FILE.exists()
    if not existed:
        STOP_FILE.write_text(f"Kill switch engaged from the Lab Console at {utc_now()}.\n", encoding="utf-8")
    record_action("stop", stop_file_already_present=existed)
    # The STOP file is written first, so the kill-switch policy denies agent actions while the run shuts down.
    terminated = RUNS.terminate("Stop all agents")
    message = "Kill switch ON. Every agent action is now denied."
    if terminated is None:
        message += " No console run was active."
    elif terminated["still_alive"]:
        message += f" The run could not be fully terminated; processes still alive: {terminated['still_alive']}."
    else:
        how = "force-killed" if terminated["forced_kill"] else "terminated"
        message += f" The current run ({terminated['label']}) and {len(terminated['child_pids'])} child process(es) were {how}."
    return {"message": message}


def action_resume(_body: dict) -> dict:
    existed = STOP_FILE.exists()
    if existed:
        if not STOP_FILE.is_file():
            raise ActionError("STOP exists but is not a regular file; remove it by hand.")
        STOP_FILE.unlink()
    record_action("resume", stop_file_was_present=existed)  # Resume never restarts a run
    return {"message": "Kill switch OFF. Agents may act again."}


def _id_from(body: dict, key: str) -> str:
    value = body.get(key)
    if not isinstance(value, str) or not ID_RE.match(value):
        raise ActionError("Please choose an entry from the list first.")
    return value


def action_run(body: dict) -> dict:
    kind = body.get("kind")
    view = ledger_view()
    if kind == "plan":
        label, prompt = "Plan a new experiment", "Phase 1"
    elif kind == "run":
        prereg_id = _id_from(body, "prereg_id")
        if prereg_id not in {e["id"] for e in runnable_preregistrations(view)}:
            raise ActionError(f"{prereg_id} is not an approved preregistration waiting to be run.")
        label, prompt = f"Run approved preregistration {prereg_id}", f"Phase 2 {prereg_id}"
    elif kind == "loop":
        decision_id = _id_from(body, "decision_id")
        if decision_id not in {e["id"] for e in decisions(view["entries"])}:
            raise ActionError(f"{decision_id} is not a decision entry in the ledger.")
        label, prompt = f"Next loop from {decision_id}", f"Loop 2 from {decision_id}"
    elif kind == "explain":
        entry_id = _id_from(body, "entry_id")
        if entry_id not in {e.get("id") for e in view["entries"]}:
            raise ActionError(f"{entry_id} is not in the ledger.")
        label, prompt = f"Explain {entry_id}", EXPLAIN_PROMPT.format(entry_id=entry_id)
    else:
        raise ActionError("Unknown run type.")
    if APPROVAL_LOCK.locked():
        raise ActionError("An approval is being written. Try again in a moment.")
    try:
        RUNS.start(label, prompt)
    except RunError as exc:
        raise ActionError(str(exc)) from exc
    return {"message": f"Started: {label}"}


def action_approve(body: dict) -> dict:
    prereg_id = _id_from(body, "prereg_id")
    approver = body.get("approver")
    note = body.get("note") or ""
    confirm = body.get("confirm")
    if not isinstance(approver, str) or not isinstance(note, str):
        raise ActionError("Invalid form data.")
    approver = " ".join(approver.split())
    note = note.strip()
    if not approver:
        raise ActionError("Not approved: an accountable human must be named.")
    if len(approver) > 200 or len(note) > 4000:
        raise ActionError("The name or the note is too long.")
    if confirm != "YES":
        raise ActionError("Not approved: type YES (capital letters) in the confirmation field.")
    if not APPROVAL_LOCK.acquire(blocking=False):
        raise ActionError("Another approval is being written. Try again in a moment.")
    try:
        if RUNS.active():
            raise ActionError("Agents are running and may be writing to the ledger. Approve after the run has finished.")
        entry = approve_preregistration(prereg_id, approver, note, path=LEDGER_PATH)
    except ApprovalError as exc:
        raise ActionError(str(exc)) from exc
    finally:
        APPROVAL_LOCK.release()
    record_action("approve", prereg_id=prereg_id, approver=approver, entry_id=entry["id"])
    return {"message": f"Approved: {entry['id']} by {approver}."}


ACTIONS = {"/api/stop": action_stop, "/api/resume": action_resume, "/api/run": action_run, "/api/approve": action_approve}


# ---------------------------------------------------------------- status JSON

def status() -> dict:
    view = ledger_view()
    entries = view["entries"]
    last = entries[-1] if entries else {}
    return {
        "ledger": {
            "ok": view["ok"], "message": view["message"], "count": len(entries),
            "last_id": last.get("id"), "last_time": last.get("timestamp"),
        },
        "stop": STOP_FILE.exists(),
        "run": RUNS.snapshot(),
        "runnable": [e["id"] for e in runnable_preregistrations(view)],
        "decisions": [{"id": e["id"], "time": e.get("timestamp")} for e in reversed(decisions(entries))],
        "entries": [{"id": e.get("id"), "type": e.get("type")} for e in reversed(entries)],
        "pending": [e["id"] for e in pending_preregistrations(entries)],
    }


# ---------------------------------------------------------------- HTML

def esc(value) -> str:
    return html.escape(str(value), quote=True)


def render_value(value, depth: int = 0) -> str:
    """Readable HTML for a JSON value from a ledger payload."""
    if depth > 6:
        return f"<pre>{esc(json.dumps(value, indent=2))}</pre>"
    if isinstance(value, dict):
        if not value:
            return "<p class='muted'>(empty)</p>"
        rows = "".join(
            f"<dt title='{esc(k)}'>{esc(str(k).replace('_', ' '))}</dt><dd>{render_value(v, depth + 1)}</dd>"
            for k, v in value.items()
        )
        return f"<dl>{rows}</dl>"
    if isinstance(value, list):
        if not value:
            return "<p class='muted'>(none)</p>"
        if all(isinstance(v, dict) and "if" in v and "then" in v for v in value):
            items = "".join(
                f"<li><strong>If</strong> {render_value(v['if'], depth + 1)} <strong>then</strong> "
                f"{render_value(v['then'], depth + 1)}"
                + "".join(f"<div><em>{esc(k)}:</em> {render_value(x, depth + 1)}</div>"
                          for k, x in v.items() if k not in ("if", "then"))
                + "</li>"
                for v in value
            )
            return f"<ol class='rules'>{items}</ol>"
        return "<ul>" + "".join(f"<li>{render_value(v, depth + 1)}</li>" for v in value) + "</ul>"
    if isinstance(value, str):
        return f"<span class='text'>{esc(value)}</span>"
    return f"<code>{esc(json.dumps(value))}</code>"


def render_pending(entries: list[dict]) -> str:
    pending = pending_preregistrations(entries)
    if not pending:
        return "<p class='empty'>No preregistrations are waiting for approval.</p>"
    blocks = []
    for e in pending:
        pid = e["id"]
        payload = e.get("payload") or {}
        fields = "".join(
            f"<h4>{esc(title)}</h4><div class='field'>{render_value(payload[key])}</div>"
            for key, title in APPROVAL_FIELDS if key in payload
        )
        missing = [key for key, _ in APPROVAL_FIELDS if key not in payload]
        missing_note = (
            f"<p class='muted'>Not stated in this preregistration: {esc(', '.join(missing))}.</p>" if missing else ""
        )
        fid = re.sub(r"[^A-Za-z0-9_-]", "_", pid)
        blocks.append(f"""
<article class="prereg" aria-labelledby="h-{fid}">
  <h3 id="h-{fid}">{esc(pid)}</h3>
  <p class="meta">Written by {esc(e.get('agent', '?'))} at {esc(e.get('timestamp', '?'))} &middot;
     builds on: {esc(', '.join(e.get('parents', [])) or 'nothing')}</p>
  <h4>What the agents propose</h4>
  <div class="field"><span class="text">{esc(e.get('text', ''))}</span></div>
  {fields}{missing_note}
  <details><summary>Show the complete preregistration payload (JSON)</summary>
    <pre>{esc(json.dumps(payload, indent=2, ensure_ascii=False))}</pre></details>
  <form class="approve-form" data-prereg="{esc(pid)}" autocomplete="off">
    <h4>Your approval</h4>
    <p>Approving unlocks this experiment. It is permanent: it is written to the ledger with your name
       and cannot be edited or deleted. Only approve if you have read the plan above.</p>
    <label for="name-{fid}">Your full name (the accountable owner of this decision) <span aria-hidden="true">*</span></label>
    <input id="name-{fid}" name="approver" type="text" required maxlength="200" autocomplete="name">
    <label for="note-{fid}">Note recorded with the approval (optional)</label>
    <textarea id="note-{fid}" name="note" rows="3" maxlength="4000"></textarea>
    <label for="confirm-{fid}">Type <strong>YES</strong> to confirm</label>
    <input id="confirm-{fid}" name="confirm" type="text" required maxlength="3" spellcheck="false">
    <button type="submit" class="btn btn-approve" disabled>Approve {esc(pid)}</button>
    <p class="form-msg" role="status" aria-live="polite"></p>
  </form>
</article>""")
    return "\n".join(blocks)


PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>CRUCIBLE Lab Console</title>
<style>
:root { --bg:#f6f7f9; --card:#fff; --ink:#1b1f24; --muted:#59636e; --line:#d0d7de;
        --red:#b42318; --red-bg:#fde8e7; --green:#1a7f37; --green-bg:#dcf5e3; --blue:#0b5cad; --amber:#9a6700; --amber-bg:#fff4d4; }
* { box-sizing: border-box; }
body { margin:0; background:var(--bg); color:var(--ink); font:17px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif; }
main { max-width:1100px; margin:0 auto; padding:16px; }
h1 { font-size:1.6rem; margin:.2rem 0 1rem; }
h2 { font-size:1.3rem; margin:0 0 .6rem; }
h3 { font-size:1.15rem; margin:0; }
h4 { font-size:1rem; margin:1rem 0 .3rem; }
section, .statusbar { background:var(--card); border:1px solid var(--line); border-radius:10px; padding:18px; margin-bottom:18px; }
.statusbar { display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); gap:12px; align-items:center; }
.stat .k { color:var(--muted); font-size:.85rem; text-transform:uppercase; letter-spacing:.04em; }
.stat .v { font-weight:600; word-break:break-word; }
.ok { color:var(--green); } .bad { color:var(--red); }
#killstate { grid-column:1/-1; font-size:1.7rem; font-weight:800; padding:12px 16px; border-radius:8px; text-align:center; }
#killstate.on { background:var(--red-bg); color:var(--red); border:2px solid var(--red); }
#killstate.off { background:var(--green-bg); color:var(--green); border:2px solid var(--green); }
.btn { font:inherit; font-weight:600; border-radius:8px; border:2px solid transparent; padding:10px 18px; cursor:pointer; }
.btn:focus-visible, input:focus-visible, select:focus-visible, textarea:focus-visible, summary:focus-visible { outline:3px solid var(--blue); outline-offset:2px; }
.btn[disabled] { opacity:.45; cursor:not-allowed; }
.btn-stop { background:var(--red); color:#fff; font-size:1.4rem; padding:16px 28px; }
.btn-resume { background:#fff; color:var(--green); border-color:var(--green); }
.btn-run { background:var(--blue); color:#fff; }
.btn-explain { background:#fff; color:var(--blue); border-color:var(--blue); }
.btn-approve { background:var(--green); color:#fff; margin-top:12px; }
.row { display:flex; flex-wrap:wrap; gap:12px; align-items:center; }
.cards { display:grid; grid-template-columns:repeat(auto-fit,minmax(240px,1fr)); gap:12px; }
.card { border:1px solid var(--line); border-radius:8px; padding:14px; display:flex; flex-direction:column; gap:8px; }
.card p { margin:0; color:var(--muted); font-size:.95rem; }
.card .btn { margin-top:auto; }
.real { font-size:.8rem; font-weight:700; color:var(--amber); background:var(--amber-bg); border-radius:4px; padding:1px 6px; align-self:flex-start; }
label { display:block; font-weight:600; margin-top:10px; }
input[type=text], textarea, select { font:inherit; width:100%; padding:8px 10px; border:1px solid #8c959f; border-radius:6px; background:#fff; color:var(--ink); }
.notice { padding:10px 14px; border-radius:8px; background:var(--amber-bg); color:#5c3d00; margin:0 0 12px; }
.notice:empty { display:none; }
#run-status { font-weight:700; }
pre { background:#0d1117; color:#e6edf3; padding:12px; border-radius:8px; overflow:auto; font-size:.82rem; line-height:1.4; max-height:480px; white-space:pre-wrap; word-break:break-word; }
.muted { color:var(--muted); }
.empty { font-size:1.1rem; color:var(--muted); }
.prereg { border:1px solid var(--line); border-radius:8px; padding:16px; margin-top:14px; }
.prereg .meta { color:var(--muted); margin:.2rem 0 0; font-size:.9rem; }
.field { background:var(--bg); border-radius:6px; padding:10px 12px; }
.text { white-space:pre-wrap; }
dl { margin:0; display:grid; grid-template-columns:minmax(120px,max-content) 1fr; gap:4px 14px; }
dt { font-weight:600; color:var(--muted); }
dd { margin:0; }
ol.rules li { margin-bottom:6px; }
details { margin-top:12px; } summary { cursor:pointer; color:var(--blue); }
.form-msg { font-weight:600; }
a { color:var(--blue); }
@media (max-width:600px) { dl { grid-template-columns:1fr; } body { font-size:16px; } }
</style>
</head>
<body>
<main>
<h1>CRUCIBLE Lab Console</h1>

<div class="statusbar" aria-label="Lab status">
  <div id="killstate" role="status" aria-live="assertive">Checking the kill switch&hellip;</div>
  <div class="stat"><div class="k">Ledger chain</div><div class="v" id="chain">&hellip;</div></div>
  <div class="stat"><div class="k">Entries</div><div class="v" id="count">&hellip;</div></div>
  <div class="stat"><div class="k">Last entry</div><div class="v" id="last">&hellip;</div></div>
</div>

<section aria-labelledby="stop-h">
  <h2 id="stop-h">Emergency stop</h2>
  <p>"Stop all agents" switches the kill switch ON, so every action any agent tries is refused, and it ends the run
     started from this console together with all its child processes. "Resume" only switches the kill switch off:
     it does not restart the stopped run. Start a new run yourself when you are ready.</p>
  <div class="row">
    <button class="btn btn-stop" id="btn-stop" type="button">Stop all agents</button>
    <button class="btn btn-resume" id="btn-resume" type="button">Resume</button>
  </div>
  <p class="form-msg" id="stop-msg" role="status" aria-live="polite"></p>
</section>

<section aria-labelledby="run-h">
  <h2 id="run-h">Run the lab</h2>
  <p class="notice" id="run-notice"></p>
  <div class="cards">
    <div class="card">
      <span class="real">Starts real agents &middot; writes to the ledger</span>
      <h3>Plan a new experiment</h3>
      <p>The agents gather evidence, propose and criticise hypotheses, and write a preregistration for you to approve below.</p>
      <button class="btn btn-run run-btn" type="button" data-kind="plan">Plan a new experiment</button>
    </div>
    <div class="card">
      <span class="real">Starts real agents &middot; writes to the ledger</span>
      <h3>Run approved preregistration</h3>
      <p>Executes a preregistration you approved, exactly once, then the agents interpret the result.</p>
      <label for="sel-run">Approved and not yet run</label>
      <select id="sel-run"></select>
      <button class="btn btn-run run-btn" type="button" data-kind="run" data-select="sel-run" data-field="prereg_id">Run approved preregistration</button>
    </div>
    <div class="card">
      <span class="real">Starts real agents &middot; writes to the ledger</span>
      <h3>Next loop from a decision</h3>
      <p>The designer writes a new preregistration that follows up on a decision. You approve it below.</p>
      <label for="sel-loop">Decision</label>
      <select id="sel-loop"></select>
      <button class="btn btn-run run-btn" type="button" data-kind="loop" data-select="sel-loop" data-field="decision_id">Next loop from a decision</button>
    </div>
    <div class="card">
      <h3>Explain a decision</h3>
      <p>The agents explain, step by step and citing ledger ids, why an entry was decided the way it was. They are told to only read the ledger.</p>
      <label for="sel-explain">Ledger entry</label>
      <select id="sel-explain"></select>
      <button class="btn btn-explain run-btn" type="button" data-kind="explain" data-select="sel-explain" data-field="entry_id">Explain a decision</button>
    </div>
  </div>
  <p class="form-msg" id="run-msg" role="status" aria-live="polite"></p>

  <h3 style="margin-top:18px">Current run</h3>
  <p><span id="run-status" role="status" aria-live="polite">No run started from this console yet.</span></p>
  <p id="run-details" class="muted"></p>
  <p id="run-session"></p>
  <pre id="run-tail" aria-label="Last 40 lines of output">(no output yet)</pre>
</section>

<section aria-labelledby="appr-h">
  <h2 id="appr-h">Approve a preregistration</h2>
  <p class="notice" id="appr-notice"></p>
  <p>The agents cannot run any experiment until a named human approves its preregistration. Read the plan, then sign it.</p>
  __PENDING__
</section>

<section aria-labelledby="help-h">
  <h2 id="help-h">How to use</h2>
  <ol>
    <li><strong>Plan a new experiment.</strong> Watch the agents live with the session link that appears under "Current run",
        or in the <a href="__OMNIGENT_UI__" target="_blank" rel="noopener">Omnigent web UI</a>.</li>
    <li><strong>Approve.</strong> When the run has finished, the new preregistration appears under "Approve a preregistration".
        Read it, type your full name and YES, and approve. Nothing is ever approved automatically.</li>
    <li><strong>Run approved preregistration.</strong> Choose it in the list and start it. Each one can run only once.</li>
    <li><strong>Next loop from a decision.</strong> After a run, the lab writes a decision. Use it to design the next experiment, then approve and run that.</li>
    <li><strong>Explain a decision</strong> at any time to see why the lab concluded what it did.</li>
    <li>If anything looks wrong, press <strong>Stop all agents</strong>. Press <strong>Resume</strong> when you are ready.</li>
  </ol>
  <p class="muted">Every run's full output is saved in logs/console_runs/. Stop, resume, run and approval actions are logged in logs/console_actions.jsonl.
     This page updates every 3 seconds. The Omnigent server must already be running (<code>omnigent</code>) for runs to work.</p>
</section>
</main>

<script>
const PENDING_AT_LOAD = __PENDING_IDS__;
let latest = null;

async function post(path, body) {
  const r = await fetch(path, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body || {})});
  let data = {};
  try { data = await r.json(); } catch (e) { data = {error: "Unexpected response from the console (" + r.status + ")."}; }
  if (!r.ok) throw new Error(data.error || ("Request failed (" + r.status + ")."));
  return data;
}

function setText(id, text) { document.getElementById(id).textContent = text; }

function fillSelect(sel, items, emptyText) {
  const keep = sel.value;
  const sig = JSON.stringify(items);
  if (sel.dataset.sig === sig) return;
  sel.dataset.sig = sig;
  sel.textContent = "";
  if (!items.length) {
    const o = document.createElement("option"); o.value = ""; o.textContent = emptyText; sel.appendChild(o);
  }
  for (const it of items) {
    const o = document.createElement("option"); o.value = it.value; o.textContent = it.label; sel.appendChild(o);
  }
  if (items.some(it => it.value === keep)) sel.value = keep;
}

function render(s) {
  latest = s;
  const ks = document.getElementById("killstate");
  ks.className = s.stop ? "on" : "off";
  ks.textContent = s.stop ? "KILL SWITCH ON \\u2014 all agents are stopped" : "Kill switch off \\u2014 agents may act";
  const chain = document.getElementById("chain");
  chain.textContent = s.ledger.ok ? "Intact (" + s.ledger.message + ")" : "BROKEN: " + s.ledger.message;
  chain.className = "v " + (s.ledger.ok ? "ok" : "bad");
  setText("count", String(s.ledger.count));
  setText("last", s.ledger.last_id ? s.ledger.last_id + " at " + s.ledger.last_time : "(empty ledger)");
  document.getElementById("btn-stop").disabled = s.stop;
  document.getElementById("btn-resume").disabled = !s.stop;

  fillSelect(document.getElementById("sel-run"), s.runnable.map(id => ({value: id, label: id})), "None approved and waiting");
  fillSelect(document.getElementById("sel-loop"), s.decisions.map(d => ({value: d.id, label: d.id + " (" + d.time + ")"})), "No decisions yet");
  fillSelect(document.getElementById("sel-explain"), s.entries.map(e => ({value: e.id, label: e.id + " (" + e.type + ")"})), "Ledger is empty");

  const run = s.run;
  const blocked = s.stop || run.active;
  for (const b of document.querySelectorAll(".run-btn")) {
    const sel = b.dataset.select ? document.getElementById(b.dataset.select) : null;
    b.disabled = blocked || (sel !== null && !sel.value);
  }
  for (const id of ["sel-run", "sel-loop", "sel-explain"]) document.getElementById(id).disabled = blocked;
  setText("run-notice", s.stop ? "The kill switch is ON, so all run buttons are disabled. Press Resume to allow runs again."
                       : run.active ? "A run is in progress. Only one run at a time is allowed." : "");
  setText("appr-notice", run.active ? "Agents are running. Approve after the run has finished, so your approval is not written while agents are writing." : "");
  if (!s.ledger.ok) setText("appr-notice", "The ledger chain is broken. Approvals and runs are refused until it is repaired.");
  if (JSON.stringify(s.pending) !== JSON.stringify(PENDING_AT_LOAD) && !document.getElementById("reload-hint")) {
    const p = document.createElement("p"); p.id = "reload-hint"; p.className = "notice";
    p.append("The list of preregistrations waiting for approval has changed. ");
    const b = document.createElement("button"); b.type = "button"; b.className = "btn btn-explain"; b.textContent = "Refresh this section";
    b.onclick = () => location.reload(); p.append(b);
    document.getElementById("appr-h").after(p);
  }
  for (const b of document.querySelectorAll(".btn-approve")) updateApproveButton(b.form);

  if (run.status === "idle") return;
  let head;
  if (run.active && run.terminating) head = "\\u25A0 STOPPING (Stop all agents was pressed): " + run.label;
  else if (run.active) head = "\\u25B6 RUNNING: " + run.label;
  else if (run.status === "stopped") head = "\\u25A0 STOPPED by \\u201cStop all agents\\u201d: " + run.label
    + (run.forced_kill ? " (it did not exit in time and was force-killed)" : " (terminated)");
  else head = "\\u2714 FINISHED: " + run.label + " (exit code " + run.exit_code + (run.exit_code === 0 ? ", success" : ", check the output") + ")";
  setText("run-status", head);
  setText("run-details", "Started " + run.started
    + (run.terminated_at ? ", terminated " + run.terminated_at : "")
    + (run.finished ? ", ended " + run.finished : "") + ". Full output: " + run.log_file);
  const sess = document.getElementById("run-session");
  sess.textContent = "";
  if (run.session_url && /^https?:\\/\\//.test(run.session_url)) {
    sess.append("Watch the agents live: ");
    const a = document.createElement("a"); a.href = run.session_url; a.target = "_blank"; a.rel = "noopener";
    a.textContent = run.session_url; sess.append(a);
  } else if (run.session_url) {
    sess.textContent = "Omnigent session: " + run.session_url;
  } else if (run.active) {
    sess.textContent = "Waiting for the Omnigent session link\\u2026";
  }
  const tail = document.getElementById("run-tail");
  const atBottom = tail.scrollHeight - tail.scrollTop - tail.clientHeight < 30;
  tail.textContent = run.tail.length ? run.tail.join("\\n") : "(no output yet)";
  if (atBottom) tail.scrollTop = tail.scrollHeight;
}

async function refresh() {
  try {
    const r = await fetch("/api/status", {cache: "no-store"});
    render(await r.json());
  } catch (e) {
    setText("killstate", "The console is not responding. Is scripts/lab_console.py still running?");
  }
}

document.getElementById("btn-stop").onclick = async () => {
  if (!confirm("Stop all agents?\\n\\nThis creates the STOP file, so every action any agent tries is refused, and it terminates the current run and all its child processes.\\n\\nResume will not restart it.")) return;
  try { setText("stop-msg", (await post("/api/stop")).message); } catch (e) { setText("stop-msg", e.message); }
  refresh();
};
document.getElementById("btn-resume").onclick = async () => {
  if (!confirm("Resume?\\n\\nThis deletes the STOP file. Agents will be allowed to act again.\\n\\nNothing is restarted: start a new run yourself if you need one.")) return;
  try { setText("stop-msg", (await post("/api/resume")).message); } catch (e) { setText("stop-msg", e.message); }
  refresh();
};

const REAL = "This will START THE REAL RESEARCH AGENTS and they will WRITE NEW ENTRIES TO THE SCIENTIFIC LEDGER.\\nLedger entries are permanent: they cannot be edited or deleted.\\n\\n";
for (const b of document.querySelectorAll(".run-btn")) {
  b.onclick = async () => {
    const kind = b.dataset.kind;
    const body = {kind};
    let target = "";
    if (b.dataset.select) { target = document.getElementById(b.dataset.select).value; if (!target) return; body[b.dataset.field] = target; }
    const msg = {
      plan: REAL + "Plan a new experiment (Phase 1)?",
      run: REAL + "Run " + target + " now? A preregistration can be executed only once.",
      loop: REAL + "Design the next loop from " + target + "?",
      explain: "Start the agents to explain " + target + "?\\n\\nThey are instructed to only read the ledger.",
    }[kind];
    if (!confirm(msg)) return;
    try { setText("run-msg", (await post("/api/run", body)).message); } catch (e) { setText("run-msg", e.message); }
    refresh();
  };
}

function updateApproveButton(form) {
  const ok = form.approver.value.trim() !== "" && form.confirm.value === "YES" && !(latest && (latest.run.active || !latest.ledger.ok));
  form.querySelector(".btn-approve").disabled = !ok;
}
for (const form of document.querySelectorAll(".approve-form")) {
  form.addEventListener("input", () => updateApproveButton(form));
  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const out = form.querySelector(".form-msg");
    const body = {prereg_id: form.dataset.prereg, approver: form.approver.value, note: form.note.value, confirm: form.confirm.value};
    try {
      const r = await post("/api/approve", body);
      out.textContent = r.message + " Reloading\\u2026";
      setTimeout(() => location.reload(), 1500);
    } catch (e) { out.textContent = e.message; }
  });
}

refresh();
setInterval(refresh, 3000);
</script>
</body>
</html>
"""


def render_page() -> str:
    entries = ledger_view()["entries"]
    pending_ids = json.dumps([e["id"] for e in pending_preregistrations(entries)]).replace("<", "\\u003c")
    return (
        PAGE.replace("__PENDING__", render_pending(entries))
        .replace("__PENDING_IDS__", pending_ids)
        .replace("__OMNIGENT_UI__", esc(OMNIGENT_UI))
    )


# ---------------------------------------------------------------- HTTP

class Handler(BaseHTTPRequestHandler):
    server_version = "CrucibleLabConsole"
    sys_version = ""

    def log_message(self, fmt, *args):
        if self.command == "GET" and self.path.startswith("/api/status"):
            return  # the page polls every 3 seconds; do not flood the terminal
        super().log_message(fmt, *args)

    def _send(self, code: int, body: str, ctype: str) -> None:
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "same-origin")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; "
            "form-action 'none'; frame-ancestors 'none'; base-uri 'none'",
        )
        self.end_headers()
        self.wfile.write(data)

    def _json(self, code: int, obj: dict) -> None:
        self._send(code, json.dumps(obj), "application/json; charset=utf-8")

    def _host_ok(self) -> bool:
        # Blocks DNS-rebinding pages from reading the console through another host name.
        return self.headers.get("Host", "") in ALLOWED_HOSTS

    def _origin_ok(self) -> bool:
        origin = self.headers.get("Origin")
        referer = self.headers.get("Referer")
        if origin is None and referer is None:
            return False
        if origin is not None and origin not in ALLOWED_ORIGINS:
            return False
        if referer is not None and not any(referer == o or referer.startswith(o + "/") for o in ALLOWED_ORIGINS):
            return False
        return True

    def do_GET(self):
        if not self._host_ok():
            return self._json(403, {"error": "Forbidden host."})
        path = self.path.split("?", 1)[0]
        if path == "/":
            return self._send(200, render_page(), "text/html; charset=utf-8")
        if path == "/api/status":
            return self._json(200, status())
        return self._json(404, {"error": "Not found."})

    def do_POST(self):
        if not self._host_ok() or not self._origin_ok():
            return self._json(403, {"error": "Forbidden: actions are only accepted from the Lab Console page."})
        action = ACTIONS.get(self.path)
        if action is None:
            return self._json(404, {"error": "Not found."})
        if self.headers.get("Content-Type", "").split(";")[0].strip().lower() != "application/json":
            return self._json(415, {"error": "Expected application/json."})
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = -1
        if length < 0 or length > MAX_BODY:
            return self._json(413, {"error": "Request too large."})
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except (json.JSONDecodeError, UnicodeDecodeError):
            return self._json(400, {"error": "Invalid JSON."})
        if not isinstance(body, dict):
            return self._json(400, {"error": "Invalid JSON."})
        try:
            return self._json(200, action(body))
        except ActionError as exc:
            return self._json(409, {"error": str(exc)})
        except Exception as exc:  # never leak a traceback to the page
            self.log_error("action %s failed: %r", self.path, exc)
            return self._json(500, {"error": f"Internal error ({type(exc).__name__}). See the console terminal."})


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    server.daemon_threads = True
    print(f"CRUCIBLE Lab Console: http://{HOST}:{PORT}  (press Ctrl+C to stop the console)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        # The run has its own process group, so Ctrl+C no longer reaches it; end it here instead of orphaning it.
        if RUNS.terminate("Lab Console shut down (Ctrl+C)") is not None:
            print("\nThe active run was terminated.")
        print("\nLab Console stopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

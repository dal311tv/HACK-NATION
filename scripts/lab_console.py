"""CRUCIBLE Lab Console: a minimal browser page to run the lab, steer its focus and approve its plans.

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
import unicodedata
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
RESULTS_DIR = REPO_ROOT / "results"
STOP_FILE = REPO_ROOT / "STOP"
ACTIONS_LOG = REPO_ROOT / "logs" / "console_actions.jsonl"
RUNS_DIR = REPO_ROOT / "logs" / "console_runs"
AGENT_COMMAND = ["omnigent", "run", "agents/crucible_lab.yaml", "-p"]
EXPLAIN_PROMPT = (
    "Do not run any phase. Using only read_ledger, explain step by step why {entry_id} was decided "
    "the way it was, citing ledger entry ids for every claim."
)
RESEARCH_QUESTION = (
    "Which inorganic crystals vibrate at the highest frequencies, and how can we find them with fewer "
    "expensive simulations?"
)
FOCUS_MAX = 600
FOCUS_SUFFIX = ". Human research focus: {focus}"
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
# The six steps of the research loop shown on the page, and the ledger entry types counted under each.
# The research question is fixed by the human and is not a ledger entry, so it has no count.
STEPS = [
    ("Question", ()),
    ("Evidence", ("evidence",)),
    ("Hypotheses", ("hypothesis", "critique", "prediction")),
    ("Experiment", ("experiment_design", "preregistration", "approval")),
    ("Result", ("run", "result")),
    ("Decision", ("decision",)),
]
FINDING_CHARS = 280
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


def runnable_preregistrations(entries: list[dict], ledger_ok: bool) -> list[dict]:
    if not ledger_ok:
        return []  # the blinding policy fails closed on a broken chain; so does the console
    return [
        e for e in entries
        if e.get("type") == "preregistration" and is_approved(entries, e["id"]) and not has_run(entries, e["id"])
    ]


def decisions(entries: list[dict]) -> list[dict]:
    return [e for e in entries if e.get("type") == "decision"]


def current_focus(entries: list[dict]) -> str | None:
    """The human_focus recorded in the latest preregistration, if it has one."""
    preregs = [e for e in entries if e.get("type") == "preregistration"]
    if not preregs:
        return None
    focus = (preregs[-1].get("payload") or {}).get("human_focus")
    return focus.strip() if isinstance(focus, str) and focus.strip() else None


def _mmss(seconds) -> str:
    seconds = max(0, int(seconds or 0))
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def lab_state(entries: list[dict], ledger_ok: bool, run: dict) -> dict:
    """Decide the "Now" sentence, the highlighted step and the primary button. Pure: reads its arguments only."""
    pending = pending_preregistrations(entries)
    runnable = runnable_preregistrations(entries, ledger_ok)
    decs = decisions(entries)
    last_decision = decs[-1]["id"] if decs else None

    if pending:
        primary = {"kind": "review", "prereg_id": pending[0]["id"]}
    elif runnable:
        primary = {"kind": "run", "prereg_id": runnable[0]["id"]}
    else:
        primary = {"kind": "plan"}

    if run.get("active"):
        kind = "running"
        now = f"Agents are working: {run.get('label', 'a run')} (elapsed {_mmss(run.get('elapsed_seconds'))})"
    elif pending:
        kind, now = "pending", "A plan is waiting for your approval"
    elif runnable:
        kind, now = "ready", "An approved experiment is ready to run"
    else:
        kind, now = "idle", f"Idle. Last decision: {last_decision or 'none yet'}"

    counts: dict[str, int] = {}
    for e in entries:
        counts[e.get("type")] = counts.get(e.get("type"), 0) + 1
    step_of_type = {t: i for i, (_, types) in enumerate(STEPS) for t in types}
    current = step_of_type.get(entries[-1].get("type"), 0) if entries else 0
    steps = [
        {"name": name, "count": sum(counts.get(t, 0) for t in types) if types else None,
         "types": {t: counts.get(t, 0) for t in types}}
        for name, types in STEPS
    ]
    return {"kind": kind, "now": now, "primary": primary, "steps": steps, "current_step": current,
            "last_decision": last_decision}


# ---------------------------------------------------------------- results (read-only)

def latest_summary(results_dir: Path | None = None) -> dict | None:
    """The most recent results/run-*/summary.json (folders starting with "_" are ignored). Reads only."""
    base = results_dir or RESULTS_DIR
    found = [
        p for p in base.glob("run-*/summary.json")
        if p.is_file() and not p.parent.name.startswith("_")
    ]
    if not found:
        return None
    path = max(found, key=lambda p: (p.stat().st_mtime, p.parent.name))
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {"_error": f"{path.parent.name}/summary.json could not be read ({type(exc).__name__})"}
    if not isinstance(data, dict):
        return {"_error": f"{path.parent.name}/summary.json is not a JSON object"}
    data.setdefault("run_id", path.parent.name)
    return data


_MISSING = object()


def _dig(obj, *keys):
    for k in keys:
        if not isinstance(obj, dict) or k not in obj:
            return _MISSING
        obj = obj[k]
    return obj


def _num(value, suffix: str = "", always_decimal: bool = False) -> str:
    """Format a stored number without inventing precision: at most one decimal."""
    if value is _MISSING:
        return "not available"
    if value is None:
        return "not reached"
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return "not available"
    if not always_decimal and float(value).is_integer():
        return f"{int(value)}{suffix}"
    return f"{value:.1f}{suffix}"


def speed_view(summary: dict | None) -> dict:
    if summary is None:
        return {"empty": True}
    if "_error" in summary:
        return {"empty": True, "error": summary["_error"]}
    return {
        "empty": False,
        "run_id": str(summary.get("run_id", "")),
        "speedup": _num(_dig(summary, "speedup_vs_random_calls_to_50pct", "C_crucible"), "x", always_decimal=True),
        "agent_calls": _num(_dig(summary, "arms", "C_crucible", "median_calls_to_50pct")),
        "random_calls": _num(_dig(summary, "random_analytic", "expected_calls_to_50pct")),
        "vs_pipeline": _num(_dig(summary, "C_vs_B_calls_to_50pct_ratio"), "x", always_decimal=True),
        "caveat": str(summary.get("caveat") or "No caveat recorded."),
    }


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

    def start(self, label: str, prompt: str, focus: str | None = None) -> None:
        with self.lock:
            if self.proc is not None and self.proc.poll() is None:
                raise RunError("Another run is still in progress. Only one run at a time is allowed.")
            if STOP_FILE.exists():
                raise RunError("The kill switch is ON (STOP file present). Press Resume first.")
            exe = shutil.which(AGENT_COMMAND[0])
            if exe is None:
                raise RunError(f"'{AGENT_COMMAND[0]}' was not found on PATH. Start the console from a terminal where it works.")
            cmd = [exe, *AGENT_COMMAND[1:], prompt]  # the prompt is one argument; no shell is involved
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
                "status": "running", "label": label, "prompt": prompt, "focus": focus, "started": utc_now(),
                "started_epoch": time.time(),
                "finished": None, "exit_code": None, "session_url": None,
                "log_file": str(log_path.relative_to(REPO_ROOT)) if log_path.is_relative_to(REPO_ROOT) else str(log_path),
            }
        record_action("run_started", label=label, prompt=prompt, focus=focus, log_file=self.state["log_file"])
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
        started = snap.pop("started_epoch", None)
        snap["elapsed_seconds"] = int(time.time() - started) if snap["active"] and started else None
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


def clean_focus(value) -> str:
    """The human research focus as one line of plain text: control characters removed, at most FOCUS_MAX chars."""
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ActionError("Invalid form data.")
    text = "".join(
        " " if unicodedata.category(ch) in ("Zl", "Zp") or ch in "\t\n\r" else ch for ch in value
    )
    text = "".join(ch for ch in text if unicodedata.category(ch) not in ("Cc", "Cf", "Cs", "Co", "Cn"))
    text = " ".join(text.split())
    if len(text) > FOCUS_MAX:
        raise ActionError(f"The research focus is too long ({len(text)} characters, at most {FOCUS_MAX}).")
    return text


def with_focus(prompt: str, focus: str) -> str:
    return prompt + FOCUS_SUFFIX.format(focus=focus) if focus else prompt


def action_run(body: dict) -> dict:
    kind = body.get("kind")
    view = ledger_view()
    focus = ""
    if kind == "plan":
        focus = clean_focus(body.get("focus"))
        label, prompt = "Plan a new experiment", with_focus("Phase 1", focus)
    elif kind == "run":
        prereg_id = _id_from(body, "prereg_id")
        if prereg_id not in {e["id"] for e in runnable_preregistrations(view["entries"], view["ok"])}:
            raise ActionError(f"{prereg_id} is not an approved preregistration waiting to be run.")
        label, prompt = f"Run approved preregistration {prereg_id}", f"Phase 2 {prereg_id}"
    elif kind == "loop":
        decision_id = _id_from(body, "decision_id")
        if decision_id not in {e["id"] for e in decisions(view["entries"])}:
            raise ActionError(f"{decision_id} is not a decision entry in the ledger.")
        focus = clean_focus(body.get("focus"))
        label, prompt = f"Next loop from {decision_id}", with_focus(f"Loop 2 from {decision_id}", focus)
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
        RUNS.start(label, prompt, focus=focus or None)
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

def page_fingerprint(entries: list[dict], summary: dict | None) -> str:
    """Changes whenever the server-rendered parts of the page (finding, speed, plans to approve) would change."""
    last = entries[-1].get("id") if entries else ""
    return f"{len(entries)}:{last}:{(summary or {}).get('run_id', '')}"


def status() -> dict:
    view = ledger_view()
    entries = view["entries"]
    last = entries[-1] if entries else {}
    run = RUNS.snapshot()
    summary = latest_summary()
    return {
        "state": lab_state(entries, view["ok"], run),
        "fingerprint": page_fingerprint(entries, summary),
        "ledger": {
            "ok": view["ok"], "message": view["message"], "count": len(entries),
            "last_id": last.get("id"), "last_time": last.get("timestamp"),
        },
        "stop": STOP_FILE.exists(),
        "run": run,
        "runnable": [e["id"] for e in runnable_preregistrations(entries, view["ok"])],
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


def _plain(value) -> str:
    if isinstance(value, dict):
        return ", ".join(f"{str(k).replace('_', ' ')} {_plain(v)}" for k, v in value.items())
    if isinstance(value, list):
        return ", ".join(_plain(v) for v in value)
    return str(value)


def plan_summary(payload: dict) -> list[tuple[str, str]]:
    """The few facts a human needs to decide on a preregistration, in plain words, straight from its payload."""
    spec = payload.get("spec")
    tested = (
        f"The agent-designed strategy ({_plain(spec)}) against random screening and the standard pipeline."
        if isinstance(spec, dict) and spec else "Not stated."
    )
    if payload.get("primary_metric"):
        tested += f" Measured by: {_plain(payload['primary_metric'])}"
    protocol = payload.get("protocol_effective")
    if not isinstance(protocol, dict):
        protocol = {**(payload.get("protocol") or {}), **(payload.get("protocol_overrides") or {})}
    budget = protocol.get("budget")
    budget_text = f"{budget} expensive simulations per strategy and seed" if budget is not None else "Not stated."
    if budget is not None and protocol.get("initial_size") is not None:
        budget_text += f", after {protocol['initial_size']} initial ones"
    seeds = protocol.get("n_seeds")
    seeds_text = f"{seeds} repeats with different random starts" if seeds is not None else "Not stated."
    if seeds is not None and protocol.get("seed_offset") is not None:
        seeds_text += f" (starting at seed {protocol['seed_offset']})"
    focus = payload.get("human_focus")
    return [
        ("What will be tested", tested),
        ("Budget", budget_text),
        ("Seeds", seeds_text),
        ("Success criterion", _plain(payload["success_criterion"]) if payload.get("success_criterion") else "Not stated."),
        ("Your focus", focus if isinstance(focus, str) and focus.strip() else "None set."),
    ]


def render_pending(entries: list[dict]) -> str:
    pending = pending_preregistrations(entries)
    if not pending:
        return "<p class='muted'>No plans are waiting for approval.</p>"
    blocks = []
    for e in pending:
        pid = e["id"]
        payload = e.get("payload") or {}
        summary = "".join(f"<dt>{esc(k)}</dt><dd>{esc(v)}</dd>" for k, v in plan_summary(payload))
        limitation_keys = [k for k in payload if k.startswith("limitations")]
        extra = ""
        if "decision_rules" in payload:
            extra += f"<h4>Decision rules (what each outcome will mean)</h4>{render_value(payload['decision_rules'])}"
        for k in limitation_keys:
            extra += f"<h4>{esc(k.replace('_', ' ').capitalize())}</h4>{render_value(payload[k])}"
        if not limitation_keys:
            extra += "<p class='muted'>This plan declares no limitations.</p>"
        fid = re.sub(r"[^A-Za-z0-9_-]", "_", pid)
        blocks.append(f"""
<article class="plan" aria-labelledby="h-{fid}">
  <h3 id="h-{fid}">Plan {esc(pid)}</h3>
  <dl class="summary">{summary}</dl>
  <details><summary>Details</summary>
    <p class="muted">Written by {esc(e.get('agent', '?'))} at {esc(e.get('timestamp', '?'))}. Builds on:
       {esc(', '.join(e.get('parents', [])) or 'nothing')}.</p>
    <h4>The agents' description</h4><p class="text">{esc(e.get('text', ''))}</p>
    {extra}
    <h4>Full plan (JSON)</h4><pre>{esc(json.dumps(payload, indent=2, ensure_ascii=False))}</pre>
  </details>
  <form class="approve-form" data-prereg="{esc(pid)}" autocomplete="off">
    <p>Approving lets the agents run this experiment once. Your name is written to the ledger permanently.</p>
    <label for="name-{fid}">Your full name</label>
    <input id="name-{fid}" name="approver" type="text" required maxlength="200" autocomplete="name">
    <label for="note-{fid}">Note <span class="muted">(optional)</span></label>
    <textarea id="note-{fid}" name="note" rows="2" maxlength="4000"></textarea>
    <label for="confirm-{fid}">Type YES to confirm</label>
    <input id="confirm-{fid}" name="confirm" type="text" required maxlength="3" spellcheck="false" class="short">
    <div><button type="submit" class="btn primary btn-approve" disabled>Approve</button></div>
    <p class="form-msg" role="status" aria-live="polite"></p>
  </form>
</article>""")
    return "\n".join(blocks)


def render_investigating(entries: list[dict]) -> str:
    focus = current_focus(entries)
    return (
        f"<p class='lead'>{esc(RESEARCH_QUESTION)}</p>"
        f"<p class='muted'>Current focus: {esc(focus) if focus else 'none set'}</p>"
        "<p class='muted'>Prototype scope: this question and dataset are fixed.</p>"
    )


def render_speed(summary: dict | None) -> str:
    v = speed_view(summary)
    if v["empty"]:
        note = f"<p class='muted'>{esc(v['error'])}</p>" if v.get("error") else ""
        return f"<p>No experiment has been run yet</p>{note}"
    return f"""
<p class="big">{esc(v['speedup'])}</p>
<p>fewer expensive simulations than random screening to find half of the top 5% materials</p>
<p class="muted">{esc(v['agent_calls'])} simulations with the agent strategy vs {esc(v['random_calls'])} expected with random screening.</p>
<p>Agent strategy vs standard pipeline: {esc(v['vs_pipeline'])}</p>
<p class="muted">Most of the speed-up comes from ML-guided screening; the agents' own design choice adds little so far.</p>
<details><summary>Details</summary>
  <p class="muted">{esc(v['caveat'])}</p>
  <p class="muted">Run: {esc(v['run_id'])}</p>
</details>"""


def render_finding(entries: list[dict]) -> str:
    decs = decisions(entries)
    if not decs:
        return "<p class='muted'>No decision has been made yet.</p>"
    d = decs[-1]
    text = str(d.get("text", ""))
    short = text[:FINDING_CHARS]
    more = ""
    if len(text) > FINDING_CHARS:
        more = (
            f"<span class='rest' hidden>{esc(text[FINDING_CHARS:])}</span><span class='ellipsis'>&hellip;</span> "
            "<button type='button' class='linkbtn' id='read-more' aria-expanded='false'>Read more</button>"
        )
    return f"<p class='text finding'>{esc(short)}{more}</p><p class='muted'>{esc(d.get('id'))}</p>"


PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>CRUCIBLE</title>
<style>
:root { --bg:#ffffff; --ink:#1d1d1f; --muted:#6e6e73; --line:#e5e5ea; --soft:#f5f5f7;
        --accent:#2f62d9; --accent-ink:#ffffff; --red:#c62828; --green:#2e7d32; }
@media (prefers-color-scheme: dark) {
  :root { --bg:#141416; --ink:#ececf0; --muted:#9a9aa2; --line:#2c2c31; --soft:#1e1e22;
          --accent:#7aa2ff; --accent-ink:#0b1020; --red:#ff6b6b; --green:#66bb6a; }
}
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--ink); font:16px/1.55 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif; }
main { max-width:720px; margin:0 auto; padding:0 16px 64px; }
header.hdr { display:flex; justify-content:space-between; align-items:center; padding:28px 0 20px; gap:12px; flex-wrap:wrap; }
.brand { font-weight:700; letter-spacing:.18em; }
.hdr-right { display:flex; align-items:center; gap:16px; font-size:13px; color:var(--muted); }
.dot { display:inline-block; width:8px; height:8px; border-radius:50%; background:var(--muted); margin-right:6px; vertical-align:middle; }
.dot.on { background:var(--green); box-shadow:0 0 0 3px color-mix(in srgb, var(--green) 25%, transparent); }
.stopbar { display:flex; justify-content:space-between; align-items:center; gap:12px; flex-wrap:wrap;
           background:var(--red); color:#fff; padding:14px 16px; margin:16px 0 8px; border-radius:8px; font-weight:600; }
.stopbar[hidden], header.hdr[hidden] { display:none; }
.stopbar button { font:inherit; font-weight:600; background:#fff; color:var(--red); border:0; border-radius:6px; padding:6px 16px; cursor:pointer; }
section { border-top:1px solid var(--line); padding:28px 0; }
section[hidden] { display:none; }
h2 { font-size:13px; font-weight:600; text-transform:uppercase; letter-spacing:.08em; color:var(--muted); margin:0 0 12px; }
h3 { font-size:16px; margin:0 0 6px; }
h4 { font-size:13px; margin:16px 0 4px; color:var(--muted); }
p { margin:0 0 8px; }
.lead { font-size:20px; line-height:1.4; }
.muted { color:var(--muted); font-size:13px; }
.big { font-size:44px; font-weight:700; line-height:1.1; margin:0 0 4px; color:var(--accent); }
.text { white-space:pre-wrap; }
a { color:var(--accent); }
.btn { font:inherit; font-weight:600; border-radius:8px; border:1px solid var(--line); background:transparent; color:var(--ink); padding:9px 18px; cursor:pointer; }
.btn.primary { background:var(--accent); color:var(--accent-ink); border-color:var(--accent); }
.btn[disabled] { opacity:.4; cursor:not-allowed; }
.linkbtn { font:inherit; background:none; border:0; padding:0; color:var(--accent); cursor:pointer; }
.linkbtn.danger { color:var(--red); }
.linkbtn[disabled] { opacity:.4; cursor:not-allowed; }
:focus-visible { outline:2px solid var(--accent); outline-offset:2px; }
label { display:block; margin:14px 0 4px; }
input[type=text], textarea, select { font:inherit; width:100%; padding:8px 10px; border:1px solid var(--line); border-radius:8px; background:var(--soft); color:var(--ink); }
input.short { width:8em; }
textarea { resize:vertical; }
.counter { text-align:right; }
.row { margin-top:12px; }
details { margin-top:10px; }
summary { cursor:pointer; color:var(--muted); font-size:13px; }
details[open] > summary { margin-bottom:8px; }
pre { background:var(--soft); padding:12px; border-radius:8px; overflow:auto; font-size:12px; line-height:1.45; max-height:420px; white-space:pre-wrap; word-break:break-word; }
ol.steps { list-style:none; display:grid; grid-template-columns:repeat(6,1fr); padding:0; margin:20px 0 0; }
ol.steps li { border-top:2px solid var(--line); padding-top:8px; font-size:13px; color:var(--muted); text-align:center; }
ol.steps li.done { border-top-color:color-mix(in srgb, var(--accent) 40%, var(--line)); }
ol.steps li.cur { border-top-color:var(--accent); color:var(--ink); font-weight:600; }
ol.steps .n { display:block; }
.action { padding:12px 0; border-top:1px solid var(--line); }
.action:first-of-type { border-top:0; }
.plan { padding-top:8px; }
.approve-form { margin-top:20px; padding-top:16px; border-top:1px solid var(--line); }
.plan + .plan { border-top:1px solid var(--line); margin-top:16px; padding-top:20px; }
dl.summary { display:grid; grid-template-columns:minmax(110px,max-content) 1fr; gap:6px 16px; margin:8px 0; }
dl.summary dt { color:var(--muted); }
dl.summary dd { margin:0; }
dl { margin:0; display:grid; grid-template-columns:minmax(100px,max-content) 1fr; gap:4px 14px; }
dt { color:var(--muted); } dd { margin:0; }
.form-msg, .msg { font-size:13px; margin-top:8px; }
.notice { font-size:13px; color:var(--red); }
.notice:empty, .msg:empty, .form-msg:empty { display:none; }
@media (max-width:560px) {
  ol.steps { grid-template-columns:repeat(3,1fr); row-gap:12px; }
  dl.summary, dl { grid-template-columns:1fr; }
  .big { font-size:36px; }
}
</style>
</head>
<body>
<main>
<header class="hdr" id="hdr">
  <div class="brand">CRUCIBLE</div>
  <div class="hdr-right">
    <span><span class="dot" id="dot"></span><span id="dot-text">&hellip;</span></span>
    <button class="linkbtn danger" id="btn-stop" type="button">Stop all agents</button>
  </div>
</header>
<div class="stopbar" id="stopbar" role="alert" hidden>
  <span>All agents are stopped</span>
  <button id="btn-resume" type="button">Resume</button>
</div>
<p class="msg" id="stop-msg" role="status" aria-live="polite"></p>

<section aria-labelledby="inv-h">
  <h2 id="inv-h">Investigating</h2>
  __INVESTIGATING__
</section>

<section aria-labelledby="now-h">
  <h2 id="now-h">Now</h2>
  <p class="lead" id="now" role="status" aria-live="polite">&hellip;</p>
  <p class="muted" id="now-extra"></p>
  <p class="notice" id="ledger-warn"></p>
  <p class="muted" id="refresh-hint" hidden>The lab has new information. <button type="button" class="linkbtn" id="btn-refresh">Refresh</button></p>
  <ol class="steps" id="steps" aria-label="Research steps"></ol>
</section>

<section aria-labelledby="speed-h">
  <h2 id="speed-h">Speed</h2>
  __SPEED__
</section>

<section aria-labelledby="find-h">
  <h2 id="find-h">Latest finding</h2>
  __FINDING__
</section>

<section aria-labelledby="next-h">
  <h2 id="next-h">What to do next</h2>
  <div id="p-review" hidden>
    <p>The agents wrote a plan. Read it and decide whether to approve it.</p>
    <button class="btn primary" id="btn-review" type="button">Review the plan</button>
  </div>
  <div id="p-run" hidden>
    <p>Plan <span id="run-target"></span> is approved. Running it uses its budget once and records the result.</p>
    <button class="btn primary run-btn" id="btn-run" type="button" data-kind="run">Run the approved experiment</button>
  </div>
  <div id="p-plan" hidden>
    <label for="focus-plan">What should the lab investigate? <span class="muted">(optional)</span></label>
    <textarea id="focus-plan" rows="3" maxlength="600"
      placeholder="For example: Test whether diversity-aware batching helps at a budget of 60"></textarea>
    <p class="muted counter" data-for="focus-plan">0 / 600</p>
    <button class="btn primary run-btn" type="button" data-kind="plan" data-focus="focus-plan">Plan a new experiment</button>
  </div>
  <p class="muted" id="next-note"></p>
  <p class="msg" id="run-msg" role="status" aria-live="polite"></p>
  <details>
    <summary>More actions</summary>
    <div class="action">
      <h3>Next loop from a decision</h3>
      <p class="muted">The agents design a follow-up experiment from a decision. Nothing runs until you approve it.</p>
      <label for="sel-loop">Decision</label>
      <select id="sel-loop"></select>
      <label for="focus-loop">What should the lab investigate? <span class="muted">(optional)</span></label>
      <textarea id="focus-loop" rows="3" maxlength="600"
        placeholder="For example: Find the smallest budget at which the agent-designed strategy separates from the baseline"></textarea>
      <p class="muted counter" data-for="focus-loop">0 / 600</p>
      <button class="btn run-btn" type="button" data-kind="loop" data-select="sel-loop" data-field="decision_id" data-focus="focus-loop">Start next loop</button>
    </div>
    <div class="action">
      <h3>Explain a decision</h3>
      <p class="muted">The agents explain why an entry was decided, citing the ledger. They are told only to read.</p>
      <label for="sel-explain">Ledger entry</label>
      <select id="sel-explain"></select>
      <div class="row"><button class="btn run-btn" type="button" data-kind="explain" data-select="sel-explain" data-field="entry_id">Explain</button></div>
    </div>
  </details>
</section>

<section id="approval" aria-labelledby="appr-h" hidden>
  <h2 id="appr-h">Plan waiting for your approval</h2>
  <p class="notice" id="appr-notice"></p>
  __PENDING__
</section>

<section aria-labelledby="out-h">
  <h2 id="out-h" hidden>Agent output</h2>
  <details id="out">
    <summary>Show agent output</summary>
    <p class="muted" id="run-status">No run started from this console yet.</p>
    <pre id="run-tail" aria-label="Last 40 lines of agent output">(no output yet)</pre>
  </details>
  <p class="muted" style="margin-top:20px">Full output of every run: logs/console_runs/. Actions: logs/console_actions.jsonl.
    <a href="__OMNIGENT_UI__" target="_blank" rel="noopener">Omnigent web UI</a></p>
</section>
</main>

<script>
const FINGERPRINT_AT_LOAD = __FINGERPRINT__;
let latest = null;

async function post(path, body) {
  const r = await fetch(path, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body || {})});
  let data = {};
  try { data = await r.json(); } catch (e) { data = {error: "Unexpected response from the console (" + r.status + ")."}; }
  if (!r.ok) throw new Error(data.error || ("Request failed (" + r.status + ")."));
  return data;
}
const $ = id => document.getElementById(id);
function setText(id, text) { $(id).textContent = text; }

function fillSelect(sel, items, emptyText) {
  const keep = sel.value, sig = JSON.stringify(items);
  if (sel.dataset.sig === sig) return;
  sel.dataset.sig = sig;
  sel.textContent = "";
  if (!items.length) { const o = document.createElement("option"); o.value = ""; o.textContent = emptyText; sel.appendChild(o); }
  for (const it of items) { const o = document.createElement("option"); o.value = it.value; o.textContent = it.label; sel.appendChild(o); }
  if (items.some(it => it.value === keep)) sel.value = keep;
}

function renderSteps(st) {
  const ol = $("steps");
  const sig = JSON.stringify([st.steps, st.current_step]);
  if (ol.dataset.sig === sig) return;
  ol.dataset.sig = sig;
  ol.textContent = "";
  st.steps.forEach((s, i) => {
    const li = document.createElement("li");
    li.className = i === st.current_step ? "cur" : (i < st.current_step ? "done" : "");
    if (i === st.current_step) li.setAttribute("aria-current", "step");
    li.title = s.count === null ? "Set by the human scientist" : Object.entries(s.types).map(([t, n]) => t + ": " + n).join(", ");
    li.append(s.name);
    const n = document.createElement("span"); n.className = "n"; n.textContent = s.count === null ? "fixed" : String(s.count);
    li.append(n); ol.append(li);
  });
}

function render(s) {
  latest = s;
  const st = s.state, run = s.run;
  $("hdr").hidden = s.stop;
  $("stopbar").hidden = !s.stop;
  $("dot").className = "dot" + (run.active ? " on" : "");
  setText("dot-text", run.active ? "Agents active" : "Stopped");
  $("dot-text").title = run.active ? "A run started from this console is in progress" : "No agents are running from this console";

  setText("now", st.now);
  const extra = $("now-extra");
  extra.textContent = "";
  if (run.active) {
    const url = run.session_url && /^https?:\/\//.test(run.session_url) ? run.session_url : null;
    if (url) {
      const a = document.createElement("a"); a.href = url; a.target = "_blank"; a.rel = "noopener"; a.textContent = "Watch live";
      extra.append(a);
    } else extra.textContent = run.terminating ? "Stopping…" : "Waiting for the live session link…";
  }
  setText("ledger-warn", s.ledger.ok ? "" : "The ledger chain is broken (" + s.ledger.message + "). Runs and approvals are refused until it is repaired.");
  renderSteps(st);
  if (s.fingerprint !== FINGERPRINT_AT_LOAD) $("refresh-hint").hidden = false;

  const kind = st.primary.kind;
  $("p-review").hidden = kind !== "review";
  $("p-run").hidden = kind !== "run";
  $("p-plan").hidden = kind !== "plan";
  if (kind === "run") { $("btn-run").dataset.prereg = st.primary.prereg_id; setText("run-target", st.primary.prereg_id); }

  fillSelect($("sel-loop"), s.decisions.map(d => ({value: d.id, label: d.id + " (" + d.time + ")"})), "No decisions yet");
  fillSelect($("sel-explain"), s.entries.map(e => ({value: e.id, label: e.id + " (" + e.type + ")"})), "Ledger is empty");
  const blocked = s.stop || run.active;
  for (const b of document.querySelectorAll(".run-btn")) {
    const sel = b.dataset.select ? $(b.dataset.select) : null;
    b.disabled = blocked || (sel !== null && !sel.value);
  }
  for (const id of ["sel-loop", "sel-explain"]) $(id).disabled = blocked;
  setText("next-note", s.stop ? "All agents are stopped, so nothing can be started. Press Resume first."
                     : run.active ? "Agents are working. Only one run at a time is allowed." : "");
  setText("appr-notice", !s.ledger.ok ? "The ledger chain is broken. Approvals are refused until it is repaired."
                       : run.active ? "Agents are working. You can approve after the run has finished." : "");
  for (const f of document.querySelectorAll(".approve-form")) updateApproveButton(f);

  if (run.status === "idle") return;
  let head;
  if (run.active && run.terminating) head = "Stopping: " + run.label;
  else if (run.active) head = "Running: " + run.label;
  else if (run.status === "stopped") head = "Stopped by “Stop all agents”: " + run.label + (run.forced_kill ? " (force-killed)" : "");
  else head = "Finished: " + run.label + " (exit code " + run.exit_code + (run.exit_code === 0 ? ")" : ", check the output)");
  setText("run-status", head + ". Full output: " + run.log_file);
  const tail = $("run-tail");
  const atBottom = tail.scrollHeight - tail.scrollTop - tail.clientHeight < 30;
  tail.textContent = run.tail.length ? run.tail.join("\n") : "(no output yet)";
  if (atBottom) tail.scrollTop = tail.scrollHeight;
}

async function refresh() {
  try {
    const r = await fetch("/api/status", {cache: "no-store"});
    render(await r.json());
  } catch (e) {
    setText("now", "The console is not responding. Is scripts/lab_console.py still running?");
  }
}

$("btn-stop").onclick = async () => {
  if (!confirm("Stop all agents?\n\nEvery action any agent tries will be refused, and the current run and all its child processes are terminated.\n\nResume will not restart it.")) return;
  try { setText("stop-msg", (await post("/api/stop")).message); } catch (e) { setText("stop-msg", e.message); }
  refresh();
};
$("btn-resume").onclick = async () => {
  if (!confirm("Resume?\n\nAgents will be allowed to act again. Nothing is restarted: start a new run yourself if you need one.")) return;
  try { setText("stop-msg", (await post("/api/resume")).message); } catch (e) { setText("stop-msg", e.message); }
  refresh();
};
$("btn-refresh").onclick = () => location.reload();
function openApproval() {
  const sec = $("approval"); sec.hidden = false; sec.scrollIntoView({behavior: "smooth", block: "start"});
  const first = sec.querySelector("input[name=approver]"); if (first) first.focus({preventScroll: true});
}
$("btn-review").onclick = openApproval;
if (location.hash === "#approval") openApproval();
const more = $("read-more");
if (more) more.onclick = () => {
  const p = more.closest("p"), open = more.getAttribute("aria-expanded") === "true";
  p.querySelector(".rest").hidden = open; p.querySelector(".ellipsis").hidden = !open;
  more.setAttribute("aria-expanded", String(!open)); more.textContent = open ? "Read more" : "Show less";
};
for (const c of document.querySelectorAll(".counter")) {
  const ta = $(c.dataset.for);
  ta.addEventListener("input", () => { c.textContent = ta.value.length + " / 600"; });
}

const REAL = "This STARTS THE REAL RESEARCH AGENTS and they WRITE NEW ENTRIES TO THE LEDGER.\nLedger entries are permanent: they cannot be edited or deleted.\n\n";
for (const b of document.querySelectorAll(".run-btn")) {
  b.onclick = async () => {
    const kind = b.dataset.kind, body = {kind};
    let target = "";
    if (kind === "run") { target = b.dataset.prereg || ""; if (!target) return; body.prereg_id = target; }
    if (b.dataset.select) { target = $(b.dataset.select).value; if (!target) return; body[b.dataset.field] = target; }
    const focus = b.dataset.focus ? $(b.dataset.focus).value.trim() : "";
    if (b.dataset.focus) body.focus = focus;
    const focusLine = focus ? "\n\nYour research focus:\n" + focus : "";
    const msg = {
      plan: REAL + "Plan a new experiment?" + focusLine,
      run: REAL + "Run the approved experiment " + target + " now? It can run only once.",
      loop: REAL + "Design the next loop from " + target + "?" + focusLine,
      explain: "Start the agents to explain " + target + "?\n\nThey are instructed to only read the ledger.",
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
      out.textContent = r.message + " Reloading…";
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


PLACEHOLDER_RE = re.compile(r"__(INVESTIGATING|SPEED|FINDING|PENDING|FINGERPRINT|OMNIGENT_UI)__")


def _js_literal(value) -> str:
    return json.dumps(value).replace("<", "\\u003c")


def render_page() -> str:
    entries = ledger_view()["entries"]
    summary = latest_summary()
    parts = {
        "INVESTIGATING": render_investigating(entries),
        "SPEED": render_speed(summary),
        "FINDING": render_finding(entries),
        "PENDING": render_pending(entries),
        "FINGERPRINT": _js_literal(page_fingerprint(entries, summary)),
        "OMNIGENT_UI": esc(OMNIGENT_UI),
    }
    # One pass, so placeholder-like text inside ledger content is never substituted.
    return PLACEHOLDER_RE.sub(lambda m: parts[m.group(1)], PAGE)


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

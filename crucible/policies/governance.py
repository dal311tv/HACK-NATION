"""Governance policies: a tested kill switch and an audit log of every attempted tool call.

The audit log must never block the lab: any error inside it is swallowed.
The kill switch must fail closed: if it cannot check the STOP file, it denies.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from crucible.ledger import REPO_ROOT


def _get(obj, key, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def make_kill_switch_policy(stop_file: str = "STOP"):
    """Deny every agent action while a STOP file exists at the repository root."""
    path = (REPO_ROOT / stop_file).resolve()
    reason = (
        f"Kill switch engaged: a human created {stop_file} in the repository. "
        "All agent actions are stopped until it is removed."
    )

    def evaluate(event):
        try:
            engaged = path.exists()
        except Exception:
            return {"result": "DENY", "reason": "Kill switch state could not be checked; failing closed."}
        if engaged:
            return {"result": "DENY", "reason": reason}
        return None

    return evaluate


def make_audit_log_policy(log_path: str = "logs/tool_audit.jsonl", max_chars: int = 500):
    """Append one line per attempted tool call. Never blocks and never raises."""
    path = (REPO_ROOT / log_path).resolve()

    def evaluate(event):
        try:
            if _get(event, "type") != "tool_call":
                return None
            data = _get(event, "data") or {}
            record = {
                "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "tool": str(_get(data, "name") or _get(event, "target") or ""),
                "arguments": json.dumps(_get(data, "arguments") or {}, default=str)[:max_chars],
                "actor": str(_get(_get(event, "context") or {}, "actor") or ""),
            }
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, default=str) + "\n")
        except Exception:
            pass
        return None

    return evaluate

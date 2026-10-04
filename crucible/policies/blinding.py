"""CRUCIBLE blinding policy for Omnigent.

Rule 1: the oracle tool is DENIED until the ledger contains a preregistration
        entry AND a human approval entry that points to it.
Rule 2: any tool call whose arguments mention the sealed data folder is DENIED.
The policy fails closed: an unreadable or tampered ledger counts as "not approved".
"""
from __future__ import annotations

import json

from crucible.ledger import read_entries, resolve_path, verify_chain


def _has_approved_preregistration(ledger_path) -> bool:
    try:
        ok, _ = verify_chain(ledger_path)
        if not ok:
            return False
        entries = read_entries(ledger_path)
    except Exception:
        return False
    prereg_ids = {e["id"] for e in entries if e.get("type") == "preregistration"}
    return any(
        e.get("type") == "approval"
        and e.get("agent") == "Human"
        and prereg_ids.intersection(e.get("parents", []))
        for e in entries
    )


def make_blinding_policy(
    ledger_path: str = "ledger/ledger.jsonl",
    sealed_marker: str = "sealed_oracle_data",
    oracle_tool: str = "query_oracle",
):
    ledger = resolve_path(ledger_path)
    marker = sealed_marker.lower()

    def evaluate(event):
        if event.get("type") != "tool_call":
            return None
        data = event.get("data") or {}
        name = str(data.get("name") or event.get("target") or "")
        arguments = data.get("arguments") or {}

        if name.endswith(oracle_tool):
            if _has_approved_preregistration(ledger):
                return {"result": "ALLOW"}
            return {
                "result": "DENY",
                "reason": (
                    "Blinding: the oracle is locked until a preregistration is written "
                    "to the ledger and approved by a human."
                ),
            }

        if marker in json.dumps(arguments, default=str).lower():
            return {
                "result": "DENY",
                "reason": "Blinding: direct access to sealed data is forbidden. Use the oracle tool after approval.",
            }
        return None

    return evaluate

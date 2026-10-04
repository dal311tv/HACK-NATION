"""Human approval of preregistrations, shared by scripts/approve.py and the Lab Console.

Only a named human can approve. Nothing in this module approves on its own: the caller
must collect the approver's name and an explicit confirmation before calling
approve_preregistration().
"""
from __future__ import annotations

from pathlib import Path

from crucible.ledger import append_entry, read_entries, verify_chain


class ApprovalError(Exception):
    """Raised when a preregistration cannot be approved. The message is safe to show to the user."""


def is_approved(entries: list[dict], prereg_id: str) -> bool:
    """Same rule as the blinding policy: a Human approval entry whose parents include the preregistration."""
    return any(
        e.get("type") == "approval" and e.get("agent") == "Human" and prereg_id in e.get("parents", [])
        for e in entries
    )


def load_preregistration_for_approval(prereg_id: str, path: str | Path | None = None) -> tuple[dict, str]:
    """Check that prereg_id can be approved and return (preregistration entry, chain status message).

    Verifies the ledger chain, that the preregistration exists, and that it is not already approved.
    """
    ok, msg = verify_chain(path)
    if not ok:
        raise ApprovalError(f"Refusing to approve: the ledger chain is broken ({msg}).")
    entries = read_entries(path)
    prereg = next((e for e in entries if e.get("id") == prereg_id and e.get("type") == "preregistration"), None)
    if prereg is None:
        raise ApprovalError(f"No preregistration with id {prereg_id}.")
    if is_approved(entries, prereg_id) or any(e.get("id") == f"appr-{prereg_id}" for e in entries):
        raise ApprovalError(f"{prereg_id} is already approved.")
    return prereg, msg


def approve_preregistration(prereg_id: str, approver: str, note: str = "", path: str | Path | None = None) -> dict:
    """Append the human approval entry for prereg_id and return it.

    path defaults to the real ledger (ledger/ledger.jsonl). Tests must pass a temporary file.
    """
    approver = (approver or "").strip()
    if not approver:
        raise ApprovalError("Not approved: an accountable human must be named.")
    load_preregistration_for_approval(prereg_id, path)
    return append_entry(
        entry_id=f"appr-{prereg_id}", entry_type="approval", agent="Human", label="INFERENCE",
        text=(f"Human approval of {prereg_id} by {approver} after reviewing the plan, spec and decision rules. " + (note or "")).strip(),
        payload={"approver": approver},
        parents=[prereg_id], path=path,
    )

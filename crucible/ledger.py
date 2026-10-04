"""Append-only, hash-chained research ledger. See docs/LEDGER_SPEC.md."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LEDGER = REPO_ROOT / "ledger" / "ledger.jsonl"
GENESIS = "GENESIS"
LABELS = {"FACT", "EVIDENCE", "INFERENCE", "HYPOTHESIS", "RESULT", "UNCERTAINTY"}
TYPES = {
    "evidence", "hypothesis", "critique", "experiment_design", "preregistration",
    "approval", "run", "result", "decision", "prediction",
}


def resolve_path(path: str | Path | None) -> Path:
    """Resolve a ledger path. Relative paths are relative to the repository root."""
    if path is None:
        return DEFAULT_LEDGER
    p = Path(path).expanduser()
    return p if p.is_absolute() else (REPO_ROOT / p).resolve()


def canonical_json(obj: dict) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def compute_hash(entry: dict) -> str:
    body = {k: v for k, v in entry.items() if k != "hash"}
    return hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()


def read_entries(path: str | Path | None = None) -> list[dict]:
    p = resolve_path(path)
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


def verify_chain(path: str | Path | None = None) -> tuple[bool, str]:
    prev = GENESIS
    for n, entry in enumerate(read_entries(path), start=1):
        if entry.get("prev_hash") != prev:
            return False, f"line {n}: prev_hash does not match previous entry"
        if compute_hash(entry) != entry.get("hash"):
            return False, f"line {n}: hash does not match content (entry was modified)"
        prev = entry["hash"]
    return True, "chain ok"


def append_entry(
    *,
    entry_id: str,
    entry_type: str,
    agent: str,
    label: str,
    text: str,
    citations: list[str] | None = None,
    parents: list[str] | None = None,
    confidence: float | None = None,
    payload: dict | None = None,
    path: str | Path | None = None,
) -> dict:
    if entry_type not in TYPES:
        raise ValueError(f"Unknown entry type: {entry_type}")
    if label not in LABELS:
        raise ValueError(f"Unknown label: {label}")
    citations = list(citations or [])
    if label in {"FACT", "EVIDENCE"} and not citations:
        raise ValueError("FACT and EVIDENCE entries require at least one citation")
    p = resolve_path(path)
    ok, msg = verify_chain(p)
    if not ok:
        raise RuntimeError(f"Ledger integrity check failed: {msg}")
    entries = read_entries(p)
    if any(e.get("id") == entry_id for e in entries):
        raise ValueError(f"Duplicate entry id: {entry_id}")
    entry = {
        "id": entry_id,
        "type": entry_type,
        "agent": agent,
        "label": label,
        "text": text,
        "citations": citations,
        "parents": list(parents or []),
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "prev_hash": entries[-1]["hash"] if entries else GENESIS,
    }
    if confidence is not None:
        entry["confidence"] = confidence
    if payload is not None:
        entry["payload"] = payload
    entry["hash"] = compute_hash(entry)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(canonical_json(entry) + "\n")
    return entry

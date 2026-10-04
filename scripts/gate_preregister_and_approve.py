"""Hour-0 gate helper: write a TEST preregistration and a human approval to the gate ledger."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from crucible.ledger import append_entry, verify_chain  # noqa: E402

LEDGER = "ledger/gate_test_ledger.jsonl"

prereg = append_entry(
    entry_id="prereg-gate-001",
    entry_type="preregistration",
    agent="Designer",
    label="INFERENCE",
    text="GATE TEST ONLY: placeholder preregistration used to test the blinding policy. Not a scientific plan.",
    payload={"gate_test": True},
    path=LEDGER,
)
approval = append_entry(
    entry_id="appr-gate-001",
    entry_type="approval",
    agent="Human",
    label="INFERENCE",
    text="GATE TEST ONLY: human approval of prereg-gate-001.",
    parents=[prereg["id"]],
    path=LEDGER,
)
print("Written:", prereg["id"], approval["id"])
print("Chain check:", verify_chain(LEDGER))

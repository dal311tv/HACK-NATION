"""Human approval gate: review a preregistration and approve it in the ledger."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from crucible.ledger import append_entry, read_entries, verify_chain  # noqa: E402

LEDGER = "ledger/ledger.jsonl"

parser = argparse.ArgumentParser()
parser.add_argument("--prereg", required=True)
args = parser.parse_args()

ok, msg = verify_chain(LEDGER)
print(f"Ledger integrity: {msg}")
if not ok:
    sys.exit("Refusing to approve: the ledger chain is broken.")
entries = read_entries(LEDGER)
prereg = next((e for e in entries if e.get("id") == args.prereg and e.get("type") == "preregistration"), None)
if prereg is None:
    sys.exit(f"No preregistration with id {args.prereg}.")
print("\n=== PREREGISTRATION ===")
print(prereg["text"])
print(json.dumps(prereg.get("payload"), indent=2))
answer = input("\nApprove this preregistration? Type YES to approve: ")
if answer.strip() != "YES":
    sys.exit("Not approved.")
entry = append_entry(
    entry_id=f"appr-{args.prereg}", entry_type="approval", agent="Human", label="INFERENCE",
    text=f"Human approval of {args.prereg} after reviewing the plan, spec and decision rules.",
    parents=[args.prereg], path=LEDGER,
)
print(f"Approved: {entry['id']}")

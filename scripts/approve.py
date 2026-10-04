"""Human approval gate: review a preregistration and approve it in the ledger."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from crucible.approval import ApprovalError, approve_preregistration, load_preregistration_for_approval  # noqa: E402

LEDGER = "ledger/ledger.jsonl"

parser = argparse.ArgumentParser()
parser.add_argument("--prereg", required=True)
parser.add_argument("--note", default="", help="Clarification recorded with the approval")
args = parser.parse_args()

try:
    prereg, msg = load_preregistration_for_approval(args.prereg, LEDGER)
except ApprovalError as exc:
    sys.exit(str(exc))
print(f"Ledger integrity: {msg}")
print("\n=== PREREGISTRATION ===")
print(prereg["text"])
print(json.dumps(prereg.get("payload"), indent=2))
approver = input("\nYour full name (the accountable human owner of this decision): ").strip()
if not approver:
    sys.exit("Not approved: an accountable human must be named.")
answer = input("Approve this preregistration? Type YES to approve: ")
if answer.strip() != "YES":
    sys.exit("Not approved.")
try:
    entry = approve_preregistration(args.prereg, approver, args.note, path=LEDGER)
except ApprovalError as exc:
    sys.exit(str(exc))
print(f"Approved: {entry['id']}")

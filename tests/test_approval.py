"""Tests for crucible/approval.py. Every test uses a temporary ledger, never ledger/ledger.jsonl."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from crucible.approval import ApprovalError, approve_preregistration  # noqa: E402
from crucible.ledger import DEFAULT_LEDGER, append_entry, read_entries, verify_chain  # noqa: E402


class ApprovalTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.ledger = Path(self._tmp.name) / "ledger.jsonl"
        self.assertNotEqual(self.ledger.resolve(), DEFAULT_LEDGER.resolve())
        append_entry(
            entry_id="h-001", entry_type="hypothesis", agent="Hypothesis", label="HYPOTHESIS",
            text="A test hypothesis.", path=self.ledger,
        )
        append_entry(
            entry_id="prereg-001", entry_type="preregistration", agent="Designer", label="INFERENCE",
            text="A test preregistration.", parents=["h-001"],
            payload={"spec": {"acquisition": "ucb"}}, path=self.ledger,
        )

    def tearDown(self):
        self._tmp.cleanup()

    def test_approval_is_appended_with_approver_name(self):
        entry = approve_preregistration("prereg-001", "  Ada Lovelace ", "Checked the margin.", path=self.ledger)
        entries = read_entries(self.ledger)
        self.assertEqual(len(entries), 3)
        self.assertEqual(entries[-1], entry)
        self.assertEqual(entry["id"], "appr-prereg-001")
        self.assertEqual(entry["type"], "approval")
        self.assertEqual(entry["agent"], "Human")
        self.assertEqual(entry["label"], "INFERENCE")
        self.assertEqual(entry["parents"], ["prereg-001"])
        self.assertEqual(entry["payload"], {"approver": "Ada Lovelace"})
        self.assertEqual(
            entry["text"],
            "Human approval of prereg-001 by Ada Lovelace after reviewing the plan, spec and decision rules. "
            "Checked the margin.",
        )
        self.assertEqual(verify_chain(self.ledger), (True, "chain ok"))

    def test_empty_approver_is_rejected(self):
        for name in ("", "   ", None):
            with self.assertRaises(ApprovalError):
                approve_preregistration("prereg-001", name, path=self.ledger)
        self.assertEqual(len(read_entries(self.ledger)), 2)

    def test_missing_preregistration_is_rejected(self):
        with self.assertRaises(ApprovalError):
            approve_preregistration("prereg-999", "Ada Lovelace", path=self.ledger)
        # An existing entry that is not a preregistration cannot be approved either.
        with self.assertRaises(ApprovalError):
            approve_preregistration("h-001", "Ada Lovelace", path=self.ledger)
        self.assertEqual(len(read_entries(self.ledger)), 2)

    def test_double_approval_is_rejected(self):
        approve_preregistration("prereg-001", "Ada Lovelace", path=self.ledger)
        with self.assertRaises(ApprovalError):
            approve_preregistration("prereg-001", "Grace Hopper", path=self.ledger)
        self.assertEqual(len(read_entries(self.ledger)), 3)

    def test_broken_chain_is_rejected(self):
        lines = self.ledger.read_text(encoding="utf-8").splitlines()
        first = json.loads(lines[0])
        first["text"] = "Tampered."
        lines[0] = json.dumps(first)
        self.ledger.write_text("\n".join(lines) + "\n", encoding="utf-8")
        before = self.ledger.read_text(encoding="utf-8")
        with self.assertRaises(ApprovalError):
            approve_preregistration("prereg-001", "Ada Lovelace", path=self.ledger)
        self.assertEqual(self.ledger.read_text(encoding="utf-8"), before)


if __name__ == "__main__":
    unittest.main()

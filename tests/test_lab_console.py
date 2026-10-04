"""Tests for the Lab Console state logic. Every test uses a temporary ledger, never ledger/ledger.jsonl."""
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from crucible.approval import approve_preregistration  # noqa: E402
from crucible.ledger import DEFAULT_LEDGER, append_entry, read_entries  # noqa: E402

_spec = importlib.util.spec_from_file_location("lab_console", REPO_ROOT / "scripts" / "lab_console.py")
lc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lc)

IDLE_RUN = {"status": "idle", "active": False}


class LabStateTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.ledger = Path(self._tmp.name) / "ledger.jsonl"
        self.assertNotEqual(self.ledger.resolve(), DEFAULT_LEDGER.resolve())

    def tearDown(self):
        self._tmp.cleanup()

    def add(self, entry_id, entry_type, agent="Designer", parents=None, payload=None, text="t"):
        append_entry(entry_id=entry_id, entry_type=entry_type, agent=agent, label="INFERENCE",
                     text=text, parents=parents or [], payload=payload, path=self.ledger)

    def state(self, run=IDLE_RUN, ok=True):
        return lc.lab_state(read_entries(self.ledger), ok, run)

    def test_empty_ledger_is_idle_and_offers_plan(self):
        st = self.state()
        self.assertEqual(st["kind"], "idle")
        self.assertEqual(st["now"], "Idle. Last decision: none yet")
        self.assertEqual(st["primary"], {"kind": "plan"})
        self.assertEqual(st["current_step"], 0)

    def test_pending_then_ready_then_idle(self):
        self.add("ev-001", "evidence", agent="Evidence")
        self.add("h-001", "hypothesis", agent="Hypothesis", parents=["ev-001"])
        self.add("prereg-001", "preregistration", parents=["h-001"], payload={"spec": {"acquisition": "ucb"}})
        st = self.state()
        self.assertEqual(st["kind"], "pending")
        self.assertEqual(st["now"], "A plan is waiting for your approval")
        self.assertEqual(st["primary"], {"kind": "review", "prereg_id": "prereg-001"})
        self.assertEqual(st["steps"][3]["name"], "Experiment")
        self.assertEqual(st["current_step"], 3)

        approve_preregistration("prereg-001", "Ada Lovelace", "", path=self.ledger)
        st = self.state()
        self.assertEqual(st["kind"], "ready")
        self.assertEqual(st["now"], "An approved experiment is ready to run")
        self.assertEqual(st["primary"], {"kind": "run", "prereg_id": "prereg-001"})
        # A broken chain fails closed: nothing is offered to run.
        self.assertEqual(self.state(ok=False)["primary"], {"kind": "plan"})

        self.add("run-prereg-001", "run", agent="Runner", parents=["prereg-001", "appr-prereg-001"])
        self.add("result-prereg-001", "result", agent="Runner", parents=["run-prereg-001"])
        self.add("dec-001", "decision", agent="Decision", parents=["result-prereg-001"])
        st = self.state()
        self.assertEqual(st["kind"], "idle")
        self.assertEqual(st["now"], "Idle. Last decision: dec-001")
        self.assertEqual(st["primary"], {"kind": "plan"})
        self.assertEqual(st["current_step"], 5)
        self.assertEqual([s["count"] for s in st["steps"]], [None, 1, 1, 2, 2, 1])

    def test_pending_wins_over_ready(self):
        self.add("prereg-001", "preregistration")
        approve_preregistration("prereg-001", "Ada Lovelace", "", path=self.ledger)
        self.add("prereg-002", "preregistration")
        self.assertEqual(self.state()["primary"], {"kind": "review", "prereg_id": "prereg-002"})

    def test_running_sentence_has_label_and_elapsed(self):
        self.add("prereg-001", "preregistration")
        run = {"status": "running", "active": True, "label": "Plan a new experiment", "elapsed_seconds": 125}
        st = self.state(run=run)
        self.assertEqual(st["kind"], "running")
        self.assertEqual(st["now"], "Agents are working: Plan a new experiment (elapsed 02:05)")
        self.assertEqual(st["primary"]["kind"], "review")  # still decided by the ledger; the page disables it

    def test_current_focus_comes_from_latest_preregistration(self):
        self.add("prereg-001", "preregistration", payload={"human_focus": "old focus"})
        self.add("prereg-002", "preregistration", payload={"spec": {}})
        self.assertIsNone(lc.current_focus(read_entries(self.ledger)))
        self.add("prereg-003", "preregistration", payload={"human_focus": "  budget of 60 "})
        self.assertEqual(lc.current_focus(read_entries(self.ledger)), "budget of 60")


class FocusTests(unittest.TestCase):
    def test_clean_focus_strips_control_characters(self):
        self.assertEqual(lc.clean_focus(None), "")
        self.assertEqual(lc.clean_focus("  a\nb\tc\x00d\x1b[31m‮  "), "a b cd[31m")
        with self.assertRaises(lc.ActionError):
            lc.clean_focus("x" * 601)
        with self.assertRaises(lc.ActionError):
            lc.clean_focus(["not text"])

    def test_prompt_is_one_argument_and_unchanged_without_focus(self):
        started = []
        original = lc.RUNS.start
        lc.RUNS.start = lambda label, prompt, focus=None: started.append((label, prompt, focus))
        try:
            with tempfile.TemporaryDirectory() as tmp:
                ledger = Path(tmp) / "ledger.jsonl"
                append_entry(entry_id="dec-001", entry_type="decision", agent="Decision", label="INFERENCE",
                             text="d", path=ledger)
                saved = lc.LEDGER_PATH
                lc.LEDGER_PATH = ledger
                try:
                    lc.action_run({"kind": "plan", "focus": ""})
                    lc.action_run({"kind": "plan", "focus": "Test budget 60; rm -rf /"})
                    lc.action_run({"kind": "loop", "decision_id": "dec-001"})
                    lc.action_run({"kind": "loop", "decision_id": "dec-001", "focus": "smallest\nbudget"})
                finally:
                    lc.LEDGER_PATH = saved
        finally:
            lc.RUNS.start = original
        self.assertEqual([p for _, p, _ in started], [
            "Phase 1",
            "Phase 1. Human research focus: Test budget 60; rm -rf /",
            "Loop 2 from dec-001",
            "Loop 2 from dec-001. Human research focus: smallest budget",
        ])
        self.assertEqual([f for _, _, f in started], [None, "Test budget 60; rm -rf /", None, "smallest budget"])


class SpeedTests(unittest.TestCase):
    def test_reads_latest_run_and_formats_without_inventing_numbers(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            self.assertIsNone(lc.latest_summary(base))
            self.assertTrue(lc.speed_view(None)["empty"])
            (base / "run-a").mkdir()
            (base / "run-a" / "summary.json").write_text(json.dumps({
                "run_id": "run-a", "caveat": "Retrospective.",
                "speedup_vs_random_calls_to_50pct": {"C_crucible": 7.027777},
                "arms": {"C_crucible": {"median_calls_to_50pct": 90.0}},
                "random_analytic": {"expected_calls_to_50pct": 632.5},
                "C_vs_B_calls_to_50pct_ratio": None,
            }))
            (base / "_scratch").mkdir()
            (base / "_scratch" / "summary.json").write_text("{}")
            v = lc.speed_view(lc.latest_summary(base))
        self.assertEqual(v["run_id"], "run-a")
        self.assertEqual(v["speedup"], "7.0x")
        self.assertEqual(v["agent_calls"], "90")
        self.assertEqual(v["random_calls"], "632.5")
        self.assertEqual(v["vs_pipeline"], "not reached")
        self.assertEqual(v["caveat"], "Retrospective.")


if __name__ == "__main__":
    unittest.main()

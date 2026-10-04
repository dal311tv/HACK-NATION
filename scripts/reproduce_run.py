"""Re-run a completed campaign from its preregistered spec and protocol and check it reproduces exactly."""
import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from crucible import campaign  # noqa: E402
from crucible.ledger import read_entries  # noqa: E402

parser = argparse.ArgumentParser()
parser.add_argument("--prereg", required=True)
args = parser.parse_args()

prereg = next(e for e in read_entries("ledger/ledger.jsonl") if e.get("id") == args.prereg)
original = json.loads((campaign.RESULTS_DIR / f"run-{args.prereg}" / "summary.json").read_text())
rerun_id = f"_repro-{args.prereg}"
rerun = campaign.run_campaign(prereg["payload"]["spec"], rerun_id, prereg["payload"].get("protocol_overrides"))
shutil.rmtree(campaign.RESULTS_DIR / rerun_id)

diffs = []
for arm, data in original["arms"].items():
    for a, b in zip(data["per_seed"], rerun["arms"][arm]["per_seed"]):
        diffs.append(abs(a["final_recall"] - b["final_recall"]))
print(f"Compared {len(diffs)} arm-seed results. Max absolute difference: {max(diffs):.6f}")
print("REPRODUCED EXACTLY" if max(diffs) == 0 else "NOT IDENTICAL")

"""Self-test of run_campaign on a tiny protocol. Prints only field names and deletes its own output."""
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from crucible import campaign  # noqa: E402

campaign.PROTOCOL.update({"n_seeds": 2, "budget": 20})
summary = campaign.run_campaign(
    {"feature_set": "composition", "acquisition": "greedy", "kappa": 0.0, "diversity": "none"}, "_selftest"
)
shutil.rmtree(campaign.RESULTS_DIR / "_selftest")
print("ok. Summary fields:", sorted(summary.keys()))
print("Comparisons:", sorted(summary["comparisons"].keys()))
print("Secondary checks:", sorted(summary["secondary_checks"].keys()))

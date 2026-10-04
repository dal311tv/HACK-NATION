"""Self-test of run_campaign on a tiny protocol. Prints only field names and checks; deletes its output."""
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
print("Pairing verified:", summary["pairing_check"]["verified"])
p = campaign.effective_protocol({"budget": 60, "n_seeds": 20, "seed_offset": 100})
print("Valid override accepted:", {k: p[k] for k in ("budget", "n_seeds", "seed_offset")})
try:
    campaign.effective_protocol({"budget": 7})
    print("ERROR: invalid override was accepted")
except ValueError:
    print("Invalid override rejected: ok")

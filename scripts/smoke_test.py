"""Timing smoke test of the campaign engine. Prints runtime only, never results."""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from crucible import campaign  # noqa: E402

pool = pd.read_csv(campaign.POOL_PATH)
feature_sets = json.loads(campaign.FEATURE_SETS_PATH.read_text())
labels_df = pd.read_csv(campaign.LABELS_PATH)
labels = dict(zip(labels_df["material_id"], labels_df["target"].astype(float)))
X = pool[feature_sets["composition_structure"]].to_numpy(dtype=float)
ids = pool["material_id"].tolist()
families = pool["element_family"].tolist()
oracle = campaign.Oracle(labels)
initial = np.random.default_rng(0).choice(len(ids), size=campaign.PROTOCOL["initial_size"], replace=False)
start = time.time()
campaign._run_arm(campaign.BASELINE_SPEC, X, families, ids, oracle, initial, 0)
elapsed = time.time() - start
print(f"One model-based arm, one seed: {elapsed:.1f} s, {oracle.calls} oracle calls.")
print(f"Estimated full campaign (3 model arms x {campaign.PROTOCOL['n_seeds']} seeds): ~{elapsed * 3 * campaign.PROTOCOL['n_seeds'] / 60:.1f} min")

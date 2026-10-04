"""CRUCIBLE campaign engine: a deterministic, matched-condition active-learning experiment.

Agents never call this module directly. They call the run_campaign tool, which is gated
by Omnigent policy and only executes a preregistered, human-approved spec.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm
from sklearn.ensemble import RandomForestRegressor

REPO_ROOT = Path(__file__).resolve().parents[1]
POOL_PATH = REPO_ROOT / "data" / "pool_features.csv"
FEATURE_SETS_PATH = REPO_ROOT / "data" / "feature_sets.json"
LABELS_PATH = REPO_ROOT / "sealed_oracle_data" / "phonons_labels.csv"
RESULTS_DIR = REPO_ROOT / "results"

# Fixed by protocol so every arm runs under matched conditions. Agents cannot change these.
PROTOCOL = {
    "initial_size": 20,
    "budget": 200,
    "batch_size": 10,
    "n_seeds": 10,
    "top_fraction": 0.05,
    "n_estimators": 100,
}
ALLOWED_SPEC_VALUES = {
    "feature_set": ["composition", "composition_structure"],
    "acquisition": ["greedy", "ucb", "ei"],
    "diversity": ["none", "element_family"],
}
RANDOM_SPEC = {"feature_set": "composition_structure", "acquisition": "random", "kappa": 0.0, "diversity": "none"}
BASELINE_SPEC = {"feature_set": "composition_structure", "acquisition": "ei", "kappa": 0.0, "diversity": "none"}
ABLATION_SPEC = {"feature_set": "composition", "acquisition": "ei", "kappa": 0.0, "diversity": "none"}


def validate_spec(spec: dict) -> dict:
    if not isinstance(spec, dict):
        raise ValueError("spec must be a JSON object")
    clean = {}
    for key, allowed in ALLOWED_SPEC_VALUES.items():
        value = spec.get(key)
        if value not in allowed:
            raise ValueError(f"spec.{key} must be one of {allowed}, got {value!r}")
        clean[key] = value
    kappa = float(spec.get("kappa", 1.0))
    if not 0.0 <= kappa <= 5.0:
        raise ValueError("spec.kappa must be between 0 and 5")
    clean["kappa"] = kappa
    return clean


class Oracle:
    """Reveals hidden labels and counts every reveal (one reveal = one expensive calculation)."""

    def __init__(self, labels: dict[str, float]):
        self._labels = labels
        self.calls = 0

    def reveal(self, material_ids: list[str]) -> list[float]:
        self.calls += len(material_ids)
        return [self._labels[m] for m in material_ids]


def _select_batch(scores, candidates, families, batch_size, diversity):
    order = np.argsort(-scores)
    chosen: list[int] = []
    seen_families: set[str] = set()
    for j in order:
        idx = int(candidates[j])
        if diversity == "element_family":
            if families[idx] in seen_families:
                continue
            seen_families.add(families[idx])
        chosen.append(idx)
        if len(chosen) == batch_size:
            return chosen
    for j in order:  # top up if the diversity rule left the batch short
        idx = int(candidates[j])
        if idx not in chosen:
            chosen.append(idx)
            if len(chosen) == batch_size:
                break
    return chosen


def _run_arm(spec, X, families, ids, oracle, initial_idx, seed):
    rng = np.random.default_rng(10_000 + seed)
    n = len(ids)
    total = PROTOCOL["initial_size"] + PROTOCOL["budget"]
    labeled = [int(i) for i in initial_idx]
    y = oracle.reveal([ids[i] for i in labeled])
    snapshots = [list(labeled)]
    while len(labeled) < total:
        mask = np.ones(n, dtype=bool)
        mask[labeled] = False
        candidates = np.flatnonzero(mask)
        batch_size = min(PROTOCOL["batch_size"], total - len(labeled))
        if spec["acquisition"] == "random":
            batch = [int(i) for i in rng.choice(candidates, size=batch_size, replace=False)]
        else:
            model = RandomForestRegressor(
                n_estimators=PROTOCOL["n_estimators"], min_samples_leaf=2, random_state=seed, n_jobs=-1
            )
            model.fit(X[labeled], np.asarray(y))
            per_tree = np.stack([tree.predict(X[candidates]) for tree in model.estimators_])
            mu = per_tree.mean(axis=0)
            sd = per_tree.std(axis=0) + 1e-9
            if spec["acquisition"] == "greedy":
                scores = mu
            elif spec["acquisition"] == "ucb":
                scores = mu + spec["kappa"] * sd
            else:  # expected improvement
                best = max(y)
                z = (mu - best) / sd
                scores = (mu - best) * norm.cdf(z) + sd * norm.pdf(z)
            batch = _select_batch(scores, candidates, families, batch_size, spec["diversity"])
        y.extend(oracle.reveal([ids[i] for i in batch]))
        labeled.extend(batch)
        snapshots.append(list(labeled))
    return snapshots


def _bootstrap_ci(values, n_boot=5000, seed=0):
    v = np.asarray(values, dtype=float)
    rng = np.random.default_rng(seed)
    means = rng.choice(v, size=(n_boot, len(v)), replace=True).mean(axis=1)
    return [float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))]


def _calls_to(curve, level):
    for calls, recall in curve:
        if recall >= level:
            return calls
    return None


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _plot(curves: pd.DataFrame, summary: dict, path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(8, 5))
    for arm, group in curves.groupby("arm"):
        stats = group.groupby("oracle_calls")["recall"]
        mean, lo, hi = stats.mean(), stats.quantile(0.1), stats.quantile(0.9)
        ax.plot(mean.index, mean.values, label=arm)
        ax.fill_between(mean.index, lo.values, hi.values, alpha=0.15)
    xs = np.linspace(0, curves["oracle_calls"].max(), 50)
    ax.plot(xs, xs / summary["n_candidates"], "k--", linewidth=1, label="random (analytic)")
    ax.set_xlabel("Oracle calls (expensive phonon calculations)")
    ax.set_ylabel(f"Recall of the top {summary['top_set_size']} materials")
    ax.set_title(f"CRUCIBLE matched-budget campaign ({summary['protocol']['n_seeds']} seeds, 10-90% band)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def run_campaign(candidate_spec: dict, run_id: str) -> dict:
    started = time.time()
    candidate = validate_spec(candidate_spec)
    pool = pd.read_csv(POOL_PATH)
    feature_sets = json.loads(FEATURE_SETS_PATH.read_text())
    labels_df = pd.read_csv(LABELS_PATH)
    labels = dict(zip(labels_df["material_id"], labels_df["target"].astype(float)))
    ids = pool["material_id"].tolist()
    families = pool["element_family"].tolist()
    n = len(ids)

    # Ground truth is used ONLY to score recall, never to make selection decisions.
    truth = np.array([labels[m] for m in ids])
    k = max(1, int(round(PROTOCOL["top_fraction"] * n)))
    top_set = set(np.argsort(-truth)[:k].tolist())

    matrices = {name: pool[cols].to_numpy(dtype=float) for name, cols in feature_sets.items()}
    arms = {
        "A_random": RANDOM_SPEC,
        "B_baseline_ei": BASELINE_SPEC,
        "B_ablation_composition_only": ABLATION_SPEC,
        "C_crucible": candidate,
    }
    per_seed = {arm: [] for arm in arms}
    curve_rows = []
    total_calls = 0
    for seed in range(PROTOCOL["n_seeds"]):
        initial = np.random.default_rng(seed).choice(n, size=PROTOCOL["initial_size"], replace=False)
        for arm, spec in arms.items():
            oracle = Oracle(labels)
            snapshots = _run_arm(spec, matrices[spec["feature_set"]], families, ids, oracle, initial, seed)
            curve = [(len(s), len(top_set.intersection(s)) / k) for s in snapshots]
            total_calls += oracle.calls
            per_seed[arm].append({
                "seed": seed,
                "final_recall": curve[-1][1],
                "calls_to_50pct": _calls_to(curve, 0.5),
                "oracle_calls": oracle.calls,
            })
            curve_rows += [{"arm": arm, "seed": seed, "oracle_calls": c, "recall": r} for c, r in curve]

    arm_summary = {}
    for arm, rows in per_seed.items():
        finals = [r["final_recall"] for r in rows]
        reached = [r["calls_to_50pct"] for r in rows if r["calls_to_50pct"] is not None]
        arm_summary[arm] = {
            "spec": arms[arm],
            "mean_final_recall": float(np.mean(finals)),
            "final_recall_95ci": _bootstrap_ci(finals),
            "seeds_reaching_50pct": len(reached),
            "median_calls_to_50pct": float(np.median(reached)) if reached else None,
            "per_seed": rows,
        }

    def paired(a, b):
        diffs = [x["final_recall"] - y["final_recall"] for x, y in zip(per_seed[a], per_seed[b])]
        return {
            "mean_difference": float(np.mean(diffs)),
            "difference_95ci": _bootstrap_ci(diffs),
            "seeds_first_better": int(sum(d > 0 for d in diffs)),
            "n_seeds": len(diffs),
        }

    random_calls_to_50 = 0.5 * n

    def speedup_vs_random(arm):
        m = arm_summary[arm]["median_calls_to_50pct"]
        return None if m is None else float(random_calls_to_50 / m)

    b_med = arm_summary["B_baseline_ei"]["median_calls_to_50pct"]
    c_med = arm_summary["C_crucible"]["median_calls_to_50pct"]
    total_budget = PROTOCOL["initial_size"] + PROTOCOL["budget"]
    summary = {
        "run_id": run_id,
        "dataset": "matbench_phonons (Petretto et al. 2018; Matbench v0.1)",
        "target": "last phonon DOS peak frequency (cm^-1)",
        "n_candidates": n,
        "top_set_size": k,
        "protocol": PROTOCOL,
        "random_analytic": {
            "expected_recall_at_budget": total_budget / n,
            "expected_calls_to_50pct": random_calls_to_50,
        },
        "arms": arm_summary,
        "comparisons": {
            "C_vs_B_baseline": paired("C_crucible", "B_baseline_ei"),
            "C_vs_A_random": paired("C_crucible", "A_random"),
            "B_full_vs_B_composition_only": paired("B_baseline_ei", "B_ablation_composition_only"),
        },
        "speedup_vs_random_calls_to_50pct": {a: speedup_vs_random(a) for a in arms if a != "A_random"},
        "C_vs_B_calls_to_50pct_ratio": (b_med / c_med) if (b_med and c_med) else None,
        "total_oracle_calls_simulated": total_calls,
        "data_hashes": {"pool_features.csv": _sha256(POOL_PATH), "phonons_labels.csv": _sha256(LABELS_PATH)},
        "runtime_seconds": round(time.time() - started, 1),
        "caveat": "Retrospective benchmark: labels were precomputed by DFPT and revealed by a simulated oracle. Not a prospective discovery.",
    }
    out = RESULTS_DIR / run_id
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(json.dumps(summary, indent=2))
    curves = pd.DataFrame(curve_rows)
    curves.to_csv(out / "curves.csv", index=False)
    _plot(curves, summary, out / "recall_curves.png")
    return summary

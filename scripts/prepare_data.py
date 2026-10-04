"""Prepare the CRUCIBLE pool: download matbench_phonons, featurize it, and seal the labels.

Run once:  uv run --python 3.12 --with matminer --with pandas scripts/prepare_data.py
Outputs:
  data/pool_features.csv                 candidates + descriptors, NO target values
  data/feature_sets.json                 descriptor columns per feature set
  data/manifest.json                     provenance and SHA-256 hashes
  sealed_oracle_data/phonons_labels.csv  hidden targets (gitignored, read only by the oracle)
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
DATA = REPO / "data"
SEALED = REPO / "sealed_oracle_data"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def clean_numeric(df: pd.DataFrame, cols: list[str]):
    block = df[cols].apply(pd.to_numeric, errors="coerce").replace([np.inf, -np.inf], np.nan)
    keep = [c for c in cols if block[c].notna().mean() > 0.9 and block[c].nunique(dropna=True) > 1]
    block = block[keep].fillna(block[keep].median())
    return block, keep


def main() -> None:
    from matminer.datasets import load_dataset
    from matminer.featurizers.composition import ElementProperty
    from matminer.featurizers.structure import DensityFeatures

    DATA.mkdir(exist_ok=True)
    SEALED.mkdir(exist_ok=True)
    df = load_dataset("matbench_phonons").reset_index(drop=True)
    target_col = "last phdos peak" if "last phdos peak" in df.columns else [c for c in df.columns if c != "structure"][0]
    print(f"Loaded {len(df)} rows. Target column: {target_col!r}")

    df["material_id"] = [f"mbph-{i:04d}" for i in range(len(df))]
    df["composition"] = df["structure"].apply(lambda s: s.composition)
    df["formula"] = df["composition"].apply(lambda c: c.reduced_formula)
    df["element_family"] = df["composition"].apply(lambda c: "-".join(sorted(el.symbol for el in c.elements)))
    df["n_sites"] = df["structure"].apply(len)

    ep = ElementProperty.from_preset("magpie")
    ep.set_n_jobs(1)
    df = ep.featurize_dataframe(df, "composition", ignore_errors=True)
    dens = DensityFeatures()
    dens.set_n_jobs(1)
    df = dens.featurize_dataframe(df, "structure", ignore_errors=True)

    comp_block, comp_cols = clean_numeric(df, list(ep.feature_labels()))
    struct_block, struct_cols = clean_numeric(df, list(dens.feature_labels()) + ["n_sites"])
    pool = pd.concat([df[["material_id", "formula", "element_family"]], comp_block, struct_block], axis=1)
    pool.to_csv(DATA / "pool_features.csv", index=False)
    (DATA / "feature_sets.json").write_text(json.dumps(
        {"composition": comp_cols, "composition_structure": comp_cols + struct_cols}, indent=2))

    labels = pd.DataFrame({
        "material_id": df["material_id"],
        "target": df[target_col].astype(float),
        "source": "matbench_phonons (Petretto et al. 2018, DFPT via ABINIT)",
    })
    labels.to_csv(SEALED / "phonons_labels.csv", index=False)

    manifest = {
        "dataset": "matbench_phonons via matminer.datasets.load_dataset",
        "data_reference": "Petretto et al., Scientific Data 5, 180065 (2018). doi:10.1038/sdata.2018.65",
        "benchmark_reference": "Dunn et al., npj Computational Materials 6, 138 (2020). doi:10.1038/s41524-020-00406-3",
        "target": f"{target_col} (cm^-1), sealed",
        "n_candidates": int(len(pool)),
        "n_composition_features": len(comp_cols),
        "n_structure_features": len(struct_cols),
        "sha256": {
            "data/pool_features.csv": sha256(DATA / "pool_features.csv"),
            "sealed_oracle_data/phonons_labels.csv": sha256(SEALED / "phonons_labels.csv"),
        },
    }
    (DATA / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"Pool written: {len(pool)} candidates, {len(comp_cols)} composition + {len(struct_cols)} structure features.")
    print("Labels sealed. No target statistics are printed on purpose.")


if __name__ == "__main__":
    main()

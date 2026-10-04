"""Sealed oracle: reveals one hidden label per call. Access is gated by the blinding policy."""
from __future__ import annotations

import csv
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SEALED_PATH = REPO_ROOT / "sealed_oracle_data" / "labels.csv"


def query_oracle(material_id: str) -> dict:
    """Return the sealed target value for one material ID."""
    if not SEALED_PATH.exists():
        return {"error": "Sealed data file not found."}
    with SEALED_PATH.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["material_id"] == material_id:
                return {
                    "material_id": material_id,
                    "target": float(row["target"]),
                    "source": row.get("source", ""),
                }
    return {"error": f"Unknown material_id: {material_id}"}

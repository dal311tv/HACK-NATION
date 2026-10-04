"""Omnigent function tools for the CRUCIBLE lab.

Every lab capability is an Omnigent tool, so Omnigent policies govern it.
"""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request

from crucible import campaign
from crucible.ledger import append_entry, read_entries, verify_chain

LEDGER = "ledger/ledger.jsonl"
AGENT_FORBIDDEN_TYPES = {"approval", "run", "result"}


def _abstract(inverted):
    if not inverted:
        return None
    positions = {}
    for word, idxs in inverted.items():
        for i in idxs:
            positions[i] = word
    return " ".join(positions[i] for i in sorted(positions)[:150])


def search_literature(query: str, max_results: int = 5) -> dict:
    """Search OpenAlex for scholarly works. Returns titles, DOIs, years and abstract excerpts."""
    params = {
        "search": query,
        "per_page": max(1, min(int(max_results), 10)),
        "select": "id,doi,display_name,publication_year,cited_by_count,abstract_inverted_index",
    }
    key = os.environ.get("OPENALEX_API_KEY")
    if key:
        params["api_key"] = key
    url = "https://api.openalex.org/works?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers={"User-Agent": "crucible-lab hackathon prototype"})
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            data = json.load(response)
    except Exception as exc:
        return {"error": f"OpenAlex request failed: {exc}"}
    results = [
        {
            "title": w.get("display_name"),
            "year": w.get("publication_year"),
            "doi": w.get("doi"),
            "openalex_id": w.get("id"),
            "cited_by": w.get("cited_by_count"),
            "abstract_excerpt": _abstract(w.get("abstract_inverted_index")),
        }
        for w in data.get("results", [])
    ]
    return {"query": query, "source": "OpenAlex", "results": results}


def pool_summary() -> dict:
    """Describe the candidate pool and the allowed experiment settings. Never reveals target values."""
    import pandas as pd

    pool = pd.read_csv(campaign.POOL_PATH)
    feature_sets = json.loads(campaign.FEATURE_SETS_PATH.read_text())
    structure_cols = [c for c in feature_sets["composition_structure"] if c not in feature_sets["composition"]]
    return {
        "n_candidates": int(len(pool)),
        "target": "Frequency of the last (highest-frequency) phonon DOS peak, cm^-1. Hidden; revealed only inside an approved campaign.",
        "feature_sets": {name: len(cols) for name, cols in feature_sets.items()},
        "structure_features": structure_cols,
        "composition_feature_examples": feature_sets["composition"][:10],
        "n_element_families": int(pool["element_family"].nunique()),
        "largest_element_families": pool["element_family"].value_counts().head(8).to_dict(),
        "protocol_fixed_for_all_arms": campaign.PROTOCOL,
        "allowed_spec_values": campaign.ALLOWED_SPEC_VALUES,
        "kappa_range": [0.0, 5.0],
        "arms_run_automatically": {
            "A_random": campaign.RANDOM_SPEC,
            "B_baseline_ei": campaign.BASELINE_SPEC,
            "B_ablation_composition_only": campaign.ABLATION_SPEC,
        },
    }


def read_ledger(last_n: int = 40) -> dict:
    """Read the most recent ledger entries and the integrity status of the hash chain."""
    ok, msg = verify_chain(LEDGER)
    keys = ("id", "type", "agent", "label", "text", "citations", "parents", "confidence", "payload", "timestamp")
    entries = [{k: e[k] for k in keys if k in e} for e in read_entries(LEDGER)]
    return {
        "chain": msg if ok else f"BROKEN: {msg}",
        "total_entries": len(entries),
        "entries": entries[-max(1, int(last_n)):],
    }


def write_ledger_entry(
    entry_id: str,
    entry_type: str,
    agent: str,
    label: str,
    text: str,
    citations: list[str] | None = None,
    parents: list[str] | None = None,
    confidence: float | None = None,
    payload_json: str | None = None,
) -> dict:
    """Append one entry to the research ledger. Agents cannot write approvals, runs or results."""
    if entry_type in AGENT_FORBIDDEN_TYPES:
        return {"error": f"Agents cannot write '{entry_type}' entries. Approvals come from humans; runs and results come from the Runner code."}
    if agent.strip().lower() == "human":
        return {"error": "Agents cannot write entries on behalf of a human."}
    existing = {e.get("id") for e in read_entries(LEDGER)}
    missing = [p for p in (parents or []) if p not in existing]
    if missing:
        return {"error": f"Unknown parent ids: {missing}"}
    try:
        payload = json.loads(payload_json) if payload_json else None
        if entry_type == "preregistration":
            if not isinstance(payload, dict) or "spec" not in payload:
                return {"error": "A preregistration payload must be a JSON object with a 'spec' key."}
            payload["spec"] = campaign.validate_spec(payload["spec"])
            payload["protocol"] = campaign.PROTOCOL
        entry = append_entry(
            entry_id=entry_id, entry_type=entry_type, agent=agent, label=label, text=text,
            citations=citations, parents=parents, confidence=confidence, payload=payload, path=LEDGER,
        )
    except (ValueError, RuntimeError) as exc:
        return {"error": str(exc)}
    return {"written": entry["id"], "hash": entry["hash"]}


def _compact(summary: dict) -> dict:
    s = json.loads(json.dumps(summary))
    for arm in s["arms"].values():
        arm.pop("per_seed", None)
    return s


def run_campaign(prereg_id: str) -> dict:
    """Execute a human-approved preregistered campaign exactly once and record run and result entries."""
    entries = read_entries(LEDGER)
    prereg = next((e for e in entries if e.get("id") == prereg_id and e.get("type") == "preregistration"), None)
    if prereg is None:
        return {"error": f"No preregistration with id {prereg_id}."}
    approval = next(
        (e for e in entries if e.get("type") == "approval" and e.get("agent") == "Human" and prereg_id in e.get("parents", [])),
        None,
    )
    if approval is None:
        return {"error": f"{prereg_id} has not been approved by a human."}
    run_id = f"run-{prereg_id}"
    if any(e.get("id") == run_id for e in entries):
        return {"error": f"{prereg_id} was already executed. A preregistered experiment runs once."}

    summary = campaign.run_campaign(prereg["payload"]["spec"], run_id)
    compact = _compact(summary)
    append_entry(
        entry_id=run_id, entry_type="run", agent="Runner", label="RESULT",
        text=(f"Executed preregistered campaign {prereg_id}: 4 arms x {summary['protocol']['n_seeds']} seeds, "
              f"{summary['total_oracle_calls_simulated']} simulated oracle calls, {summary['runtime_seconds']} s."),
        citations=[f"results/{run_id}/summary.json"], parents=[prereg_id, approval["id"]],
        payload={"data_hashes": summary["data_hashes"], "protocol": summary["protocol"]}, path=LEDGER,
    )
    arms = summary["arms"]
    cb = summary["comparisons"]["C_vs_B_baseline"]
    total = summary["protocol"]["initial_size"] + summary["protocol"]["budget"]
    text = (
        f"Mean recall of the top {summary['top_set_size']} materials after {total} oracle calls: "
        + ", ".join(f"{name} {v['mean_final_recall']:.3f}" for name, v in arms.items())
        + f". Random analytic expectation {summary['random_analytic']['expected_recall_at_budget']:.3f}. "
        + f"C minus B: {cb['mean_difference']:+.3f} (95% CI {cb['difference_95ci'][0]:+.3f} to {cb['difference_95ci'][1]:+.3f}), "
        + f"C better in {cb['seeds_first_better']}/{cb['n_seeds']} seeds."
    )
    append_entry(
        entry_id=f"result-{prereg_id}", entry_type="result", agent="Runner", label="RESULT", text=text,
        citations=[f"results/{run_id}/summary.json"], parents=[run_id], payload=compact, path=LEDGER,
    )
    return compact


def get_results(run_id: str) -> dict:
    """Read the stored summary of a completed run."""
    path = campaign.RESULTS_DIR / run_id / "summary.json"
    if not path.exists():
        return {"error": f"No results for {run_id}."}
    return _compact(json.loads(path.read_text()))

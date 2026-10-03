# Ledger Specification

The ledger is the shared research record of CRUCIBLE. Every scientific decision is written here and can be reconstructed from it.

## File
- Path: `ledger/ledger.jsonl`
- Format: one JSON object per line (JSON Lines).
- Append-only: lines are never edited or deleted.

## Fields
| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string | yes | Unique ID, prefixed by type (e.g. `ev-001`, `h-002`). |
| `type` | string | yes | One of: `evidence`, `hypothesis`, `critique`, `experiment_design`, `preregistration`, `approval`, `run`, `result`, `decision`, `prediction`. |
| `agent` | string | yes | Agent that wrote the entry (`PI`, `Evidence`, `Data`, `Hypothesis`, `Critic`, `Designer`, `Runner`, `Decision`, `Human`). |
| `label` | string | yes | Epistemic status: `FACT`, `EVIDENCE`, `INFERENCE`, `HYPOTHESIS`, `RESULT`, `UNCERTAINTY`. |
| `text` | string | yes | Plain-language content of the entry. |
| `citations` | array of strings | yes | DOIs or URLs. Empty array allowed only for non-FACT/EVIDENCE labels. |
| `parents` | array of strings | yes | IDs of the entries this one depends on. Empty for root entries. |
| `confidence` | number 0-1 | no | Used for hypotheses and decisions. |
| `payload` | object | no | Structured data (experiment spec, metrics, run parameters). |
| `example` | boolean | no | `true` for placeholder data. The UI must show an EXAMPLE banner. |
| `timestamp` | string | yes | ISO 8601, UTC. |
| `prev_hash` | string | yes | `hash` of the previous line. First line uses `"GENESIS"`. |
| `hash` | string | yes | SHA-256 of the entry serialized as canonical JSON (sorted keys, no whitespace), excluding the `hash` field itself. |

## Rules
1. Entries labeled `FACT` or `EVIDENCE` must have at least one citation.
2. Agent-generated hypotheses are always labeled `HYPOTHESIS`, never `FACT`.
3. A `preregistration` entry must exist and be approved before any `run` entry.
4. Any change to an approved plan is a new `decision` entry marked as a protocol amendment, linked to the original via `parents`.
5. No real result may be shown in the demo unless it comes from a `run` or `result` entry produced by the Runner.

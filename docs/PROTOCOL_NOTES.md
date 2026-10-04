# Protocol notes for prereg-001

## Pre-run analysis tooling update

Made after `prereg-001` was written and before it was approved or executed. No campaign result existed at this point.

The preregistration specifies analyses the campaign engine did not yet compute. The engine was extended to compute them; the experimental design (spec, protocol, arms, seeds, budget) was not changed.

| Preregistered item | Implementation |
|---|---|
| Ties excluded and reported | `ties` and `seeds_second_better` added to every paired comparison |
| Pairing check | `pairing_check`: one initial labeled set per seed, reused by every arm, with a hash per seed |
| Equivalence (TOST) | `difference_90ci` added to every paired comparison |
| Recall-curve AUC, C vs B and B vs ablation | `auc_normalized` per seed and paired AUC comparisons |
| Primary delta stratified by top-5% hits in the initial 20 | `secondary_checks.primary_delta_by_initial_top_hits` |
| Distinct anion / light-element groups among top-5% hits | **Deviation:** measured as distinct element families among top-5% hits (proxy) |

The full analysis path was verified with `scripts/selftest_campaign.py`, which runs a reduced protocol, prints only field names, and deletes its output.

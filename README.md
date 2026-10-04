# CRUCIBLE

**A governed AI lab for expensive experiments.** Specialist agents read the literature, propose competing hypotheses, critique them and design experiments. Omnigent enforces the scientific method as policy: blinding, preregistration, human approval and least privilege. Every decision is written to a tamper-evident ledger, so any conclusion can be traced back to its evidence.

Built for the 7th Global AI Hackathon (Hack-Nation), Challenge 03: Agentic Scientific Discovery, with [Omnigent](https://github.com/omnigent-ai/omnigent).

---

## Results at a glance

**Question.** Under a fixed, preregistered budget of expensive phonon calculations, does an evidence-informed, agent-designed screening campaign recover more of the top 5% materials (by highest phonon DOS peak frequency) than random screening and than a standard Bayesian-optimization pipeline, under matched conditions? Secondary: does crystal structure add signal beyond composition?

**Two complete discovery loops**, each preregistered by the agents, approved by humans, executed once under Omnigent policy, and interpreted against preregistered decision rules. The first loop exposed a flaw in its own protocol; the second loop was designed from that finding.

| | Loop 1 (`prereg-001`) | Loop 2 (`prereg-002`) |
|---|---|---|
| Protocol | 10 seeds (0-9), 20 initial + 200 oracle calls | 30 fresh seeds (100-129), 20 initial + 100 oracle calls |
| A: random screening, final recall | 0.176 | 0.091 |
| B: standard pipeline (RF + expected improvement), final recall | 0.956 | 0.691 |
| B without structure features, final recall | 0.944 | 0.675 |
| **C: agent-designed (RF + UCB, kappa = 2), final recall** | **0.987** | **0.721** |
| C minus B, final recall (95% CI) | +0.032 (+0.024 to +0.040), C better in 10/10 seeds | +0.030 (-0.004 to +0.061), 17 better / 9 worse / 4 ties |
| C minus B, recall-curve AUC (95% CI) | +0.033 (+0.019 to +0.046) | +0.005 (-0.012 to +0.021) |
| Median oracle calls to recover 50% of the top 5%: random (analytic) / B / C | 632.5 / 100 / 90 | 632.5 / 90 / 90 |
| Structure vs composition only, final recall (95% CI) | +0.011 (-0.003 to +0.022) | +0.016 (-0.021 to +0.056) |
| Preregistered rule that fired | Positive but below the +0.05 margin; **ceiling rule fired** (B > 0.85) | **Inconclusive** (95% CI includes 0; equivalence missed: 90% CI upper bound 0.056 vs margin 0.05) |
| Decision | `dec-001`: measure where the baseline has headroom, with more and fresh seeds | `dec-002`: inconclusive; next experiment proposed |
| Reproduced from the ledger | Exactly (40 arm-seed results, max difference 0.000000) | Exactly (120 arm-seed results, max difference 0.000000) |

### What we can honestly claim

- **About 7x fewer expensive calculations than random screening** to recover half of the top 5% materials (90 vs an expected 632.5), replicated in both loops.
- **That speed-up comes from ML-guided screening itself**, not from the agents' design choice: the standard pipeline reached the same 90 calls in Loop 2 (100 in Loop 1).
- **The agent-designed acquisition added about +0.03 recall late in the campaign**, a consistent size in both loops, but it is **not statistically robust** with fresh seeds and headroom, and it **did not speed up** reaching 50% recall.
- **Crystal-structure descriptors added no detectable signal** in either loop.
- The lab **lowered its own confidence** that the agent design beats the baseline (0.35 to 0.25) instead of over-claiming.

### Speed of the research process (from ledger timestamps, UTC)

| Step | Time |
|---|---|
| Loop 1, first evidence entry to preregistration (8 cited evidence entries, 3 hypotheses, 3 critiques, 2 scored designs, 1 preregistration) | 5 min 31 s |
| Loop 1, result to rule-based decision | 1 min 40 s |
| Loop 2, first design entry to preregistration | 59 s |
| Loop 2, first design entry to decision, including human review and approval | 7 min 16 s |

No human baseline was timed, so no process speed-up ratio is claimed.

---

## A governed agent: the seven questions

| Question | CRUCIBLE's answer | Evidence |
|---|---|---|
| **Who is the human owner?** | Jair de Jesus Martinez Pineda is accountable for the project. Every approval records the name of the person who signed it (`payload.approver`). | `scripts/approve.py`, `crucible/approval.py`, approval entries in the ledger |
| **Where does a human decide?** | Before any expensive calculation: each preregistration must be approved by a named human, and only that preregistration is unlocked. Humans also set the limits within which agents may change the protocol. | Tests 1, 3, 5 and 6 |
| **What can it touch?** | Each agent has only its own tools, with no file or shell access. Sealed data is never exposed. Credentials never appear in prompts: the Claude login is handled by Omnigent setup, and API keys live only in environment variables or hidden input. Personal account connectors were found by a test and removed. | Tests 2 and 4 |
| **Can it be stopped?** | Yes, tested: a `STOP` file makes Omnigent deny every agent action, in the PI and in every sub-agent; deleting it resumes the lab. The Lab Console's "Stop all agents" button creates `STOP` and terminates the active run and its child processes. | Test 7, `scripts/lab_console.py` |
| **How is it evaluated?** | The process, not only the result: adversarial access tests, preregistered decision rules, verified pairing, floor and ceiling controls, and exact reproduction of both runs from the ledger. | `docs/HOUR0_GATE.md`, `docs/PROTOCOL_NOTES.md`, `tests/` |
| **What value does it create?** | A scientist with a budget of 120 expensive calculations finds about 45 of the 63 best materials, instead of about 6 with random screening: roughly 8x more useful candidates for the same spend (Loop 2). Most of that gain comes from ML-guided screening; what CRUCIBLE adds is a result the scientist can defend: who approved it, on what evidence, and under which rules. | Loop 2 results |
| **What did it record?** | A hash-chained ledger of every decision, an audit log of every attempted tool call, a log of every console action, run records with data hashes, and Omnigent session transcripts. | `ledger/ledger.jsonl`, `logs/tool_audit.jsonl`, `logs/console_actions.jsonl`, `results/` |

---

## What makes it different: the scientific method enforced as policy

Most agent systems ask the model to behave. CRUCIBLE makes the rules structural. Every control below was tested adversarially; see [`docs/HOUR0_GATE.md`](docs/HOUR0_GATE.md).

| Control | How it is enforced | Evidence |
|---|---|---|
| **Blinding** | Omnigent policy denies the oracle and the campaign runner until the ledger holds a preregistration approved by a human | Tests 1 and 3 |
| **Per-preregistration approval** | The policy checks the specific `prereg_id`, not just that some approval exists | Test 6 |
| **Blinding inside sub-agents** | Each sub-agent declares its own tools and policies; the runner was denied by policy | Test 5 |
| **No direct access to sealed data** | Reasoning agents have no file or shell tools | Test 2 |
| **Agents cannot forge approvals or results** | The ledger tool rejects `approval`, `run` and `result` entries from agents; results are written by code | `crucible/tools/lab_tools.py` |
| **Run once** | A preregistered experiment can be executed exactly once | `run_campaign` |
| **No citation, no fact** | `FACT` and `EVIDENCE` entries without a citation are rejected | `crucible/ledger.py` |
| **Tamper evidence** | Hash-chained ledger; policies fail closed if the chain breaks | `verify_chain` |
| **Least privilege** | Personal account connectors blocked; see the security finding below | Test 4 |
| **Human-set limits** | Agents may change the protocol only inside limits set by humans | `PROTOCOL_OVERRIDE_LIMITS` |

### Security finding

Omnigent policies govern tools routed through Omnigent. Tools that a harness provides natively (here, personal Claude account connectors such as Gmail and Drive) were **not** intercepted by Omnigent policies, and a test agent was able to read personal account data. The fix was to remove those connectors at the account level. Lesson applied in the design: every capability the lab relies on is exposed as an Omnigent tool, and access-control claims are made only after an adversarial test confirms them.

---

## Architecture

~~~text
Human scientist -- sets the question and the protocol limits; approves preregistrations
      |
      v
PI (Omnigent supervisor) -- delegates with sys_session_send, collects with sys_read_inbox
  |- evidence_agent     search_literature (OpenAlex), write_ledger_entry
  |- hypothesis_agent   pool_summary, write_ledger_entry
  |- critic_agent       search_literature, write_ledger_entry
  |- designer_agent     pool_summary, write_ledger_entry  -> preregistration
  |        -- HUMAN APPROVAL (scripts/approve.py, outside the session) --
  |- runner_agent       run_campaign (policy-gated)        -> run + result written by code
  |- decision_agent     get_results, write_ledger_entry    -> decision + next experiment
      |
      v
Hash-chained ledger (ledger/ledger.jsonl) -- read-only Mission Control dashboard (ui/)
~~~

| Agent | Scientific decision it owns |
|---|---|
| Evidence | What is known, and from which source |
| Hypothesis | Which competing, testable hypotheses the lab holds |
| Critic | What would falsify each hypothesis, and what could fool the lab |
| Designer | Which experiment to commit the budget to, under which rules |
| Runner | None: executes the approved preregistration once |
| Decision | What the lab now believes, and what to test next |

Each sub-agent has only the tools it needs and carries the same policies (least privilege, blinding, tool-call cap).

---

## The experiment

- **Data:** `matbench_phonons`, 1,265 inorganic crystals with DFPT-computed phonon spectra ([Petretto et al., 2018](https://doi.org/10.1038/sdata.2018.65)), from the Matbench benchmark ([Dunn et al., 2020](https://doi.org/10.1038/s41524-020-00406-3)). Target: frequency of the last phonon DOS peak (cm^-1). Labels are sealed and revealed only by a counting oracle.
- **Descriptors:** 123 composition features (Magpie) and 4 structure features, built by `scripts/prepare_data.py`.
- **Arms (matched conditions):** A random; B random forest + expected improvement; B without structure features; C the agent-designed spec. All arms in a seed share the same initial labeled set, verified by hash.
- **Primary metric:** mean paired difference in final top-5% recall, C minus B, with 95% bootstrap CI. Secondary metrics, ties, pairing checks, floor and ceiling rules were all preregistered.
- **Counting convention:** every oracle-call count includes the 20 initial labels.

All protocol notes and deviations are in [`docs/PROTOCOL_NOTES.md`](docs/PROTOCOL_NOTES.md).

---

## What the lab learned, and what comes next

1. The Loop 1 protocol was too generous: the baseline reached 0.956 recall, so the preregistered margin was unreachable. The lab detected this through its own ceiling rule.
2. With headroom and 30 fresh seeds, the agent design's advantage stayed the same size (+0.03) but became statistically inconclusive.
3. **Next experiment:** the lab proposed pooling 30 additional fresh seeds with Loop 2. Human review flagged that adding data until a result becomes significant inflates false positives; the correct next step is a sequential design with an alpha-spending correction, or a single preregistered, adequately powered replication sized from the observed between-seed variance.

## Limitations and validation needed before real-world use

- **Retrospective benchmark:** labels were precomputed by DFPT and revealed by a simulated oracle. This evaluates screening strategy, not a prospective discovery.
- **Cleaned pool:** 1,265 of 1,521 compounds; results may not transfer to an uncurated screening campaign.
- **Coarse resolution:** oracle calls happen in batches of 10, so 90 vs 100 calls is one batch.
- **Proxy:** the preregistered anion / light-element diversity check was measured as distinct element families (declared deviation).
- **Not available in this harness:** a shuffled-structure control and varying random-forest feature sampling.
- **Real-world use** would require a prospective campaign with real DFPT calculations on unlabeled structures, and calibration across phonon codes.

---

## Reproduce

~~~bash
# 1. Data (downloads matbench_phonons, featurizes it, seals the labels)
uv run --python 3.12 --with matminer --with pandas scripts/prepare_data.py

# 2. Engine checks (no results are shown)
uv run --python 3.12 --with pandas --with scikit-learn --with matplotlib scripts/selftest_campaign.py

# 3. Re-run a completed preregistered campaign and verify it reproduces exactly
uv run --python 3.12 --with pandas --with scikit-learn --with matplotlib scripts/reproduce_run.py --prereg prereg-001
uv run --python 3.12 --with pandas --with scikit-learn --with matplotlib scripts/reproduce_run.py --prereg prereg-002

# 4. Run the lab with Omnigent
export PYTHONPATH="$(pwd)"
omnigent
omnigent run agents/crucible_lab.yaml -p "Phase 1"
uv run --python 3.12 scripts/approve.py --prereg prereg-001
omnigent run agents/crucible_lab.yaml -p "Phase 2 prereg-001"
omnigent run agents/crucible_lab.yaml -p "Loop 2 from dec-001"
~~~

## Repository map

| Path | Contents |
|---|---|
| `agents/crucible_lab.yaml` | PI and six specialist sub-agents, with tools and policies |
| `agents/gate_test.yaml` | Access-control test agent |
| `crucible/campaign.py` | Deterministic, matched-condition campaign engine |
| `crucible/tools/lab_tools.py` | Omnigent function tools used by the agents |
| `crucible/policies/` | Blinding and least-privilege policies |
| `crucible/ledger.py` | Hash-chained, append-only ledger |
| `ledger/ledger.jsonl` | The complete research record of both loops |
| `results/` | Summaries, curves and plots of each run |
| `docs/` | Ledger spec, access-control tests, protocol notes |
| `ui/` | Read-only Mission Control dashboard (PHP) |

## Team setup

- **Mac, core lab:** Omnigent, Python 3.12, agents, policies, data and experiments.
- **Windows, Mission Control UI:** PHP dashboard that reads the ledger and results, read-only.
- **Sync:** shared GitHub repository. API keys live only in environment variables and are never committed.

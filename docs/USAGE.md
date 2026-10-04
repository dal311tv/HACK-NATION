# Using CRUCIBLE

## Lab Console

The Lab Console is a local web page for running the lab without the terminal. It uses only the Python standard library and runs on your own computer only.

### Start it

From the repository root, in a terminal where `omnigent` works and your API keys are already set in the environment:

~~~bash
omnigent                                         # the Omnigent server, if it is not already running
uv run --python 3.12 scripts/lab_console.py      # in a second terminal
~~~

Open http://127.0.0.1:8765. Press Ctrl+C in that terminal to stop the console.

The console listens on 127.0.0.1 only. Every action is a POST from the console page. Requests that come from any other origin (another website, another port) are refused.

### What the page shows

One centred column, read from top to bottom. Technical details sit behind small "Details" disclosures.

**Header.** "CRUCIBLE", a status dot ("Agents active" while a run started from the console is in progress, "Stopped" otherwise) and a red "Stop all agents" text button. Stop first creates the `STOP` file at the repository root, so the kill-switch policy denies every action any agent tries, then terminates the console's run and all its child processes (5 seconds after a polite stop signal, anything still running is force-killed). While `STOP` exists the header is replaced by a red bar, "All agents are stopped", with a "Resume" button. Resume only deletes `STOP`; it never restarts a run. Both ask for confirmation, and both are logged in `logs/console_actions.jsonl`. Ctrl+C on the console also ends any active run.

**Investigating.** The fixed research question in plain words, the human focus recorded in the latest preregistration ("none set" if it has none), and a reminder that the question and dataset are fixed in this prototype.

**Now.** One sentence: "Agents are working: <action> (elapsed mm:ss)" with a "Watch live" link to the Omnigent session; "A plan is waiting for your approval"; "An approved experiment is ready to run"; or "Idle. Last decision: <id>". Under it, six steps (Question, Evidence, Hypotheses, Experiment, Result, Decision) with the number of ledger entries of each kind, and the step of the latest ledger entry highlighted. Hover a step to see the count per entry type. A warning appears here if the ledger hash chain is broken.

**Speed.** Read from the most recent `results/run-*/summary.json` (folders starting with `_` are ignored). The large number is `speedup_vs_random_calls_to_50pct.C_crucible`, then the calls behind it (`arms.C_crucible.median_calls_to_50pct` vs `random_analytic.expected_calls_to_50pct`) and the agent strategy vs the standard pipeline (`C_vs_B_calls_to_50pct_ratio`). Values are shown as stored, with at most one decimal; `null` shows as "not reached". "Details" shows the run's caveat and run id.

**Latest finding.** The first 280 characters of the latest decision entry, with "Read more" and its id.

**What to do next.** One primary button, chosen from the ledger:

| State | Button | What it does |
|---|---|---|
| A preregistration has no human approval | Review the plan | Opens the approval panel (no agents start) |
| An approved preregistration has not run | Run the approved experiment | `omnigent run agents/crucible_lab.yaml -p "Phase 2 <prereg_id>"` |
| Otherwise | Plan a new experiment | `omnigent run agents/crucible_lab.yaml -p "Phase 1"` |

"More actions" holds "Next loop from a decision" (`-p "Loop 2 from <decision_id>"`) and "Explain a decision" (`-p "Do not run any phase. Using only read_ledger, explain ..."`).

**Human research focus.** "Plan a new experiment" and "Next loop" have an optional box, "What should the lab investigate?" (at most 600 characters). Left empty, the commands are exactly the ones above. Filled in, the prompt becomes `Phase 1. Human research focus: <text>` or `Loop 2 from <decision_id>. Human research focus: <text>`. Control characters and line breaks are removed first, and the prompt is passed as a single argument to the process (never through a shell). The focus is recorded in `logs/console_actions.jsonl`. The PI passes the focus verbatim to every specialist, and the designer quotes it as `human_focus` in the preregistration and explains in `why` how the design addresses it. The focus steers the work only inside the fixed question, dataset, oracle and protocol limits: if it asks for something the lab cannot test (another property, another dataset, wet-lab work), the PI says so and plans the closest experiment the lab can run.

Rules that still apply: every button that starts real agents asks for confirmation and says it writes to the ledger; only one run at a time; all run buttons are disabled while `STOP` exists; the full output of each run is saved in `logs/console_runs/<timestamp>.log`.

**Approval panel.** Opened by "Review the plan" (or by opening http://127.0.0.1:8765/#approval). For each unapproved preregistration it shows what will be tested, the budget, the seeds, the success criterion and the human focus. "Details" shows the agents' full description, the decision rules, the declared limitations and the complete payload. To approve, enter your full name, an optional note, and type `YES` exactly. The approval is written through `crucible/approval.py`, the same code `scripts/approve.py` uses; it is permanent and names you as the accountable approver. The console never approves anything itself, and approvals are refused while a console run is active.

**Agent output.** Hidden behind "Show agent output": the status of the last run and its last 40 lines of output.

### Approving from the terminal

`scripts/approve.py` still works as before:

~~~bash
uv run --python 3.12 scripts/approve.py --prereg prereg-003 --note "optional clarification"
~~~

### Tests

~~~bash
uv run --python 3.12 -m unittest discover -s tests -v
~~~

The tests use a temporary ledger file and never touch `ledger/ledger.jsonl`.

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

### What each section does

**Status bar.** Shows whether the ledger hash chain is intact, how many entries it has, and the id and time of the last entry. The large banner shows the kill switch: green when agents may act, red when the STOP file exists and every agent action is denied.

**Emergency stop.** "Stop all agents" first creates the `STOP` file at the repository root, so the kill-switch policy denies every action any agent tries. It then terminates the run started from the console, together with all its child processes. They get up to 5 seconds to exit after a polite stop signal; anything still running after that is force-killed. The page then shows the run as "STOPPED" and says whether a force-kill was needed. "Resume" only deletes the `STOP` file: it never restarts the stopped run, so start a new run yourself when you are ready. Both buttons ask for confirmation first. Each stop, resume and termination is logged with a timestamp in `logs/console_actions.jsonl`. Stopping the console itself with Ctrl+C also ends any active run.

**Run the lab.** Each button runs one Omnigent command from the repository root with `PYTHONPATH` set to the repository root:

| Button | Command |
|---|---|
| Plan a new experiment | `omnigent run agents/crucible_lab.yaml -p "Phase 1"` |
| Run approved preregistration | `omnigent run agents/crucible_lab.yaml -p "Phase 2 <prereg_id>"` |
| Next loop from a decision | `omnigent run agents/crucible_lab.yaml -p "Loop 2 from <decision_id>"` |
| Explain a decision | `omnigent run agents/crucible_lab.yaml -p "Do not run any phase. Using only read_ledger, explain ..."` |

- "Plan", "Run" and "Next loop" start the real agents, which write to the ledger. Each asks for confirmation first.
- "Run approved preregistration" lists only preregistrations that a human approved and that have not run yet.
- Only one run can be active at a time. All run buttons are disabled while the kill switch is on.
- While a run is active, the page shows its status, the "Omnigent session" link to watch the agents live, and the last 40 lines of output. It refreshes every 3 seconds.
- The full output of every run is saved in `logs/console_runs/<timestamp>.log`.

**Approve a preregistration.** Lists every preregistration that no human has approved yet. For each one it shows the agents' text and, in readable form, the spec, protocol overrides, protocol, success criterion, decision rules and declared limitations. The complete payload is available as JSON underneath.

To approve, enter your full name, an optional note, and type `YES` exactly. The approval is written to the ledger through `crucible/approval.py`, which is the same code `scripts/approve.py` uses. It is permanent, and it records your name as the accountable approver. The console never approves anything on its own. Approvals are refused while a console run is active, so a human approval is never written to the ledger at the same time as an agent's entry.

**How to use.** A short reminder of the loop on the page itself (plan, approve, run, next loop, explain), plus a link to the Omnigent web UI at http://127.0.0.1:6767.

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

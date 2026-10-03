
## Team Setup

- **Mac - Core Lab:** Omnigent, Python 3.12, agents, policies, data and experiment. The only machine that writes `ledger/ledger.jsonl` and `results/`.
- **Windows - Mission Control UI:** PHP dashboard that reads the ledger. Read-only. Shows an EXAMPLE banner for entries with `"example": true`.
- **Sync:** shared GitHub repository. The Mac pushes ledger and results; the Windows machine pulls them.
- **Secrets:** API keys live only in environment variables on each machine. Keys are never committed.
- **Demo:** runs from a single machine (the Mac) or from a recorded session. No live dependency between the two machines.

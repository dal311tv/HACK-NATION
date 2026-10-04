"""Fallback: run an approved campaign from the command line with the same gates and ledger writes."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from crucible.tools.lab_tools import run_campaign  # noqa: E402

parser = argparse.ArgumentParser()
parser.add_argument("--prereg", required=True)
print(json.dumps(run_campaign(parser.parse_args().prereg), indent=2))

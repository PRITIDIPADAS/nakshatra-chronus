"""Pool the citizen lab study answers of several participants.

Each participant downloads their answers from the citizen lab (Study mode, Download my answers). Put the files in one
folder and run:  python scripts/analyse_citizen_study.py answers/*.json
Prints Fleiss kappa between participants, test retest consistency on the repeated cases, how often the crowd majority
and the engine match the practice truth, and how often the crowd and the engine agree.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

import study  # noqa: E402


def main(paths):
    S = json.load(open(os.path.join(ROOT, "data", "study.json")))
    ex = [json.load(open(p)) for p in paths]
    ex = [e for e in ex if e.get("protocol") == S["protocol"]]
    res = study.analyse(S, ex)
    print(json.dumps({k: v for k, v in res.items() if k != "table"}, indent=1))
    return res


if __name__ == "__main__":
    main(sys.argv[1:])

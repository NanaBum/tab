"""Diagnose fingering failures with exact binary constraints; no note changes.

This is an offline audit, not the normal beam-search inference path. Feasibility
is relative to the declared string/timing/span assumptions, not all guitar technique.
"""

import argparse
import json
from pathlib import Path

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import coo_matrix

from tabber.models import STANDARD_TUNING, Note


def exact_feasibility(notes, span=5, time_limit=10):
    if not notes:
        return {"max_span": span, "status": 0, "message": "Empty performance is feasible"}
    if span < 0 or time_limit <= 0:
        raise ValueError("Use nonnegative span and positive time limit")
    notes = sorted(notes, key=lambda n: n.start)
    choices, groups = [], []
    for note in notes:
        group = []
        for string, pitch in enumerate(STANDARD_TUNING):
            if 0 <= note.pitch - pitch <= 24:
                group.append(len(choices))
                choices.append((string, note.pitch - pitch))
        if not group:
            return {
                "max_span": span,
                "status": 2,
                "message": "A note is outside the instrument range",
            }
        groups.append(group)
    rows, cols, values, lower, upper = [], [], [], [], []
    for group in groups:
        for column in group:
            rows.append(len(lower))
            cols.append(column)
            values.append(1)
        lower.append(1)
        upper.append(1)
    for i, note in enumerate(notes):
        for j in range(i + 1, len(notes)):
            if notes[j].start >= note.end - 1e-6:
                break
            for first in groups[i]:
                for second in groups[j]:
                    s1, f1 = choices[first]
                    s2, f2 = choices[second]
                    if s1 == s2 or (f1 and f2 and abs(f1 - f2) > span):
                        rows.extend((len(lower), len(lower)))
                        cols.extend((first, second))
                        values.extend((1, 1))
                        lower.append(-np.inf)
                        upper.append(1)
    matrix = coo_matrix((values, (rows, cols)), shape=(len(lower), len(choices))).tocsc()
    result = milp(
        np.zeros(len(choices)),
        integrality=np.ones(len(choices)),
        bounds=Bounds(0, 1),
        constraints=LinearConstraint(matrix, lower, upper),
        options={"time_limit": time_limit},
    )
    return {"max_span": span, "status": int(result.status), "message": result.message}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("predictions", type=Path)
    parser.add_argument("--output", type=Path, default=Path("runs/fretting-constraint-audit.json"))
    args = parser.parse_args()
    data = json.loads(args.predictions.read_text(encoding="utf-8"))
    rows = []
    for track in data["tracks"]:
        if track["fretting_status"].startswith("assigned"):
            continue
        notes = [Note(**n) for n in track["predictions"]]
        row = {
            "track": track["track"],
            "conditions": [exact_feasibility(notes, span) for span in (5, 7)],
        }
        rows.append(row)
        print(row, flush=True)
    report = {
        "purpose": "Exact feasibility under standard tuning, 24 frets, fixed detected timings and span limits",
        "constraints": "One position per note; simultaneous notes cannot share strings; non-open frets obey span",
        "status_meaning": {
            "0": "feasible/optimal",
            "2": "proved infeasible",
            "1": "limit, not a proof",
        },
        "results": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

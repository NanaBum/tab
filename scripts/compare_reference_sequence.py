"""Compare a supplied string/fret sequence with an exported notes.json, offline."""

import argparse
import itertools
import json
from pathlib import Path

from tabber.models import Note
from tabber.sequence import compare_sequences


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "reference", type=Path, help="JSON list of string/fret objects, string 0 high E"
    )
    parser.add_argument(
        "predicted", type=Path, help="Tabber output notes.json, including fingering"
    )
    parser.add_argument("--output", type=Path, default=Path("runs/sequence-comparison.json"))
    args = parser.parse_args()
    try:
        reference = json.loads(args.reference.read_text(encoding="utf-8-sig"))
        payload = json.loads(args.predicted.read_text(encoding="utf-8-sig"))
        fretted = payload["notes"]
        timed = [(Note(**n["note"]), n) for n in fretted]
        timed.sort(key=lambda item: (item[0].start, -item[0].pitch, item[1]["string"]))
        predicted = [
            {"string": n["string"], "fret": n["fret"], "pitch": note.pitch} for note, n in timed
        ]
        report = compare_sequences(reference, predicted)
        report["overlapping_adjacent_prediction_pairs"] = sum(
            b[0].start < a[0].end - 1e-6 for a, b in itertools.pairwise(timed)
        )
        report["simultaneous_adjacent_attacks"] = sum(
            abs(b[0].start - a[0].start) <= 1e-6 for a, b in itertools.pairwise(timed)
        )
        report["prediction_order"] = (
            "Onset time, then descending pitch, then string; no reference-based reordering"
        )
    except (ValueError, TypeError, KeyError, OSError) as error:
        parser.exit(1, f"Could not compare sequence: {error}\n")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "alignment"}, indent=2))


if __name__ == "__main__":
    main()

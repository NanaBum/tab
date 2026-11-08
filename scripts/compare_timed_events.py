"""Compare local timed note files with raw and one-global-shift metrics."""

import argparse
import hashlib
import json
from pathlib import Path

from tabber.alignment import compare_with_global_shift
from tabber.note_files import read_notes


def file_hash(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference", type=Path)
    parser.add_argument("predicted", type=Path)
    parser.add_argument("--output", type=Path, default=Path("runs/timed-comparison.json"))
    parser.add_argument("--max-shift", type=float, default=5.0)
    parser.add_argument("--step", type=float, default=0.01)
    parser.add_argument("--onset-tolerance", type=float, default=0.05)
    args = parser.parse_args()
    try:
        if args.output.resolve() in (args.reference.resolve(), args.predicted.resolve()):
            raise ValueError("The output report must not overwrite an input file")
        report = compare_with_global_shift(
            read_notes(args.reference),
            read_notes(args.predicted),
            max_shift=args.max_shift,
            step=args.step,
            onset_tolerance=args.onset_tolerance,
        )
        report["inputs"] = {
            label: {"path": str(path.resolve()), "sha256": file_hash(path)}
            for label, path in (("reference", args.reference), ("predicted", args.predicted))
        }
        if args.reference.suffix.lower() == ".json":
            source_metadata = json.loads(args.reference.read_text(encoding="utf-8-sig")).get(
                "metadata", {}
            )
            if isinstance(source_metadata, dict) and "reference_status" in source_metadata:
                report["inputs"]["reference"]["reference_metadata"] = {
                    key: source_metadata[key]
                    for key in (
                        "reference_status",
                        "data_permission",
                        "approximate_techniques",
                        "technique_flags",
                        "timing",
                        "repeat_unfolding_requested",
                        "playback_measure_count",
                    )
                    if key in source_metadata
                }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    except (OSError, ValueError, TypeError, KeyError) as error:
        parser.exit(1, f"Could not compare timed events: {error}\n")
    print(f"Raw pitch/onset F1: {report['raw']['onsets']['f1']:.3f}")
    print(f"Global prediction shift: {report['prediction_shift_seconds']:+.3f}s")
    print(
        f"Shifted pitch/onset F1: {report['shifted']['onsets']['f1']:.3f} (reference-assisted diagnostic)"
    )
    if report["ambiguous_shift"]:
        print("Alignment note: More than one separated shift fits equally well.")
    if report["at_search_boundary"]:
        print("Alignment note: The selected shift is at the search boundary.")
    print(f"Report: {args.output.resolve()}")
    if "reference_metadata" in report["inputs"]["reference"]:
        print(
            "Reference note: Imported score is a candidate reference; inspect its timing, technique and permission metadata."
        )


if __name__ == "__main__":
    main()

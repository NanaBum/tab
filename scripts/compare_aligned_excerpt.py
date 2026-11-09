"""Compare detectors on the same recording excerpt using a fixed score clock."""

import argparse
import json
import math
from dataclasses import asdict
from pathlib import Path

from tabber.alignment import excerpt_target
from tabber.evaluation import score_notes
from tabber.events import load_events
from tabber.media import sha256_file


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", action="append", required=True, type=Path)
    parser.add_argument(
        "--prediction", nargs=2, action="append", required=True, metavar=("NAME", "FILE")
    )
    parser.add_argument(
        "--score-shift", type=float, required=True, help="Add after scaling score time"
    )
    parser.add_argument(
        "--score-scale", type=float, default=1, help="Multiply score times before shifting"
    )
    parser.add_argument("--recording-start", type=float, default=0)
    parser.add_argument("--duration", type=float, required=True)
    parser.add_argument("--onset-tolerance", type=float, default=0.075)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    try:
        if not math.isfinite(args.onset_tolerance) or args.onset_tolerance <= 0:
            raise ValueError("Use a positive finite onset tolerance")
        references = []
        track_events = []
        pair_hashes = set()
        for path in args.reference:
            metadata = json.loads(path.read_text(encoding="utf-8-sig"))["metadata"]
            pair_hash = metadata["source_pair_sha256"]
            pair_hashes.add(pair_hash)
            references.append(
                {
                    "path": str(path.resolve()),
                    "sha256": sha256_file(path),
                    "source_pair_sha256": pair_hash,
                    "source_pair": metadata.get("source_pair"),
                    "score_track": metadata.get("score_track"),
                    "approximate_techniques": metadata.get("approximate_techniques", []),
                }
            )
            track_events.append(load_events(path))
        if len(pair_hashes) != 1:
            raise ValueError("Reference tracks must come from one source pair")
        target = excerpt_target(
            track_events,
            score_shift=args.score_shift,
            recording_start=args.recording_start,
            duration=args.duration,
            score_scale=args.score_scale,
        )
        if not target:
            raise ValueError("No reference attacks in the selected excerpt")
        report = {
            "purpose": "Fixed score-clock candidate onset comparison",
            "score_shift_seconds": args.score_shift,
            "score_scale": args.score_scale,
            "recording_start_seconds": args.recording_start,
            "excerpt_duration_seconds": args.duration,
            "onset_tolerance_seconds": args.onset_tolerance,
            "references": references,
            "conditions": {},
            "limits": "Score alignment is supplied externally. Coincident equal pitches count once. Only pitch and attack times are scored.",
        }
        for name, filename in args.prediction:
            if name in report["conditions"]:
                raise ValueError("Prediction names must be unique")
            path = Path(filename)
            prediction = load_events(path)
            if any(note.start >= args.duration for note in prediction):
                raise ValueError(f"Prediction {name} contains an attack beyond the excerpt")
            report["conditions"][name] = {
                "path": str(path.resolve()),
                "sha256": sha256_file(path),
                "onsets": asdict(
                    score_notes(target, prediction, onset_tolerance=args.onset_tolerance)
                ),
            }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, indent=2)
            stream.write("\n")
    except (OSError, KeyError, TypeError, ValueError) as error:
        parser.exit(1, f"Could not compare excerpt: {error}\n")
    print(f"Saved {len(report['conditions'])} conditions against {len(target)} candidate attacks")


if __name__ == "__main__":
    main()

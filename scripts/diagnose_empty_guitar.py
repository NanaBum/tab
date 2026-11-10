"""Compare frozen GAPS activations on aligned mixes and their verified stems."""

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from evaluate_onset_excerpts import load_partition, reuse_inputs

from tabber.evaluation import score_notes
from tabber.events import save_events
from tabber.guitar_gaps import CHECKPOINT_SHA256, decode_gaps, gaps_activations
from tabber.media import sha256_file

CONDITIONS = (("stem", 1.0), ("stem_half_gain", 0.5), ("mix", 1.0))
THRESHOLDS = (0.3, 0.12, 0.05)


def diagnose(manifest, split, stem_results, destination):
    excerpts = load_partition(manifest, split)
    digest = sha256_file(manifest)
    stems = reuse_inputs(stem_results, digest, split, excerpts)
    destination.mkdir(parents=True, exist_ok=False)
    report = {
        "manifest_sha256": digest,
        "split": split,
        "stem_report_sha256": sha256_file(stem_results / "report.json"),
        "checkpoint_sha256": CHECKPOINT_SHA256,
        "onset_tolerance_seconds": 0.075,
        "limits": "Weak score labels. Conditions and cutoffs are exploratory. No model fitting.",
        "excerpts": [],
    }
    for i, ((row, mix, reference), stem) in enumerate(zip(excerpts, stems, strict=True), 1):
        results = {}
        for name, gain in CONDITIONS:
            source = mix if name == "mix" else stem
            activation, duration = gaps_activations(source, input_gain=gain)
            onset = activation["reg_onset_output"]
            frame = activation["frame_output"]
            result = {
                "input_sha256": sha256_file(source),
                "gain": gain,
                "maximum_onset": float(onset.max()),
                "maximum_frame": float(frame.max()),
                "thresholds": {},
            }
            for threshold in THRESHOLDS:
                notes = decode_gaps(activation, duration, onset_threshold=threshold)
                filename = f"excerpt-{i:03d}-{name}-{threshold:g}.json"
                save_events(
                    notes,
                    destination / filename,
                    {
                        "input_sha256": result["input_sha256"],
                        "gain": gain,
                        "onset_threshold": threshold,
                        "backend": "guitar-gaps",
                    },
                )
                result["thresholds"][str(threshold)] = {
                    **asdict(score_notes(reference, notes, onset_tolerance=0.075)),
                    "events": filename,
                    "events_sha256": sha256_file(destination / filename),
                }
            results[name] = result
            print(f"{row['song_id']} {name}: maximum onset {onset.max():.3f}", flush=True)
        report["excerpts"].append(
            {
                "song_id": row["song_id"],
                "labels_sha256": row["labels_sha256"],
                "conditions": results,
            }
        )
    with (destination / "report.json").open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--split", choices=("validation", "test"), required=True)
    parser.add_argument("--stem-results", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        diagnose(args.manifest, args.split, args.stem_results, args.output)
    except (OSError, KeyError, TypeError, ValueError, RuntimeError) as error:
        parser.exit(1, f"Could not diagnose empty guitar results: {error}\n")


if __name__ == "__main__":
    main()

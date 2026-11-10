"""Compare agreement, union and an empty-result fallback on shared benchmark audio."""

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from evaluate_onset_excerpts import load_partition, verified_asset

from tabber.evaluation import score_notes
from tabber.events import load_events, save_events
from tabber.fusion import complementary_notes
from tabber.media import sha256_file


def read_results(folder, manifest_hash, split, excerpts):
    path = folder / "report.json"
    report = json.loads(path.read_text(encoding="utf-8"))
    if (
        report["manifest_sha256"] != manifest_hash
        or report["split"] != split
        or len(report["excerpts"]) != len(excerpts)
    ):
        raise ValueError("Detector results do not describe this benchmark partition")
    for index, (record, (row, _, _)) in enumerate(
        zip(report["excerpts"], excerpts, strict=True), 1
    ):
        if any(record[key] != row[key] for key in ("song_id", "audio_sha256", "labels_sha256")):
            raise ValueError("Detector results do not match the benchmark excerpt")
        result = verified_asset(
            folder, f"excerpt-{index:03d}/detected-notes.json", record["prediction_sha256"]
        )
        yield report["backend"], record, load_events(result)


def compare(manifest, split, first, second, destination):
    excerpts = load_partition(manifest, split)
    manifest_hash = sha256_file(manifest)
    primary = read_results(first, manifest_hash, split, excerpts)
    secondary = read_results(second, manifest_hash, split, excerpts)
    rows, combined = [], []
    for (row, _, reference), (a_name, a, a_notes), (b_name, b, b_notes) in zip(
        excerpts, primary, secondary, strict=True
    ):
        if a_name == b_name or a["detector_input_sha256"] != b["detector_input_sha256"]:
            raise ValueError("Compare different detectors that used byte-identical inputs")
        entries = complementary_notes(a_notes, b_notes)
        agreement = [note for note, p, q in entries if p is not None and q is not None]
        union = [note for note, _, _ in entries]
        scores = {
            name: asdict(score_notes(reference, notes, onset_tolerance=0.075))
            for name, notes in (
                ("primary", a_notes),
                ("secondary", b_notes),
                ("agreement", agreement),
                ("union", union),
                ("empty_primary_fallback", a_notes or b_notes),
            )
        }
        record = {
            "song_id": row["song_id"],
            "primary_backend": a_name,
            "secondary_backend": b_name,
            "detector_input_sha256": a["detector_input_sha256"],
            "labels_sha256": row["labels_sha256"],
            "primary_events_sha256": a["prediction_sha256"],
            "secondary_events_sha256": b["prediction_sha256"],
            "fallback_used_secondary": not a_notes,
            "scores": scores,
        }
        rows.append(record)
        combined.append(
            (
                union,
                {
                    **record,
                    "source_indices": [{"primary": p, "secondary": q} for _, p, q in entries],
                },
            )
        )
    destination.mkdir(parents=True, exist_ok=False)
    for i, (notes, metadata) in enumerate(combined, 1):
        save_events(notes, destination / f"excerpt-{i:03d}-union.json", metadata)
    report = {
        "purpose": "Diagnostic comparison of detector agreement, union and empty-result fallback",
        "manifest_sha256": manifest_hash,
        "split": split,
        "agreement_tolerance_seconds": 0.05,
        "scoring_tolerance_seconds": 0.075,
        "limits": "Nearby same-pitch detections are paired one-to-one. Primary timing and release are retained. Close repetitions can be merged; unmatched detections are relative to weak score labels.",
        "excerpts": rows,
    }
    (destination / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--split", choices=("validation", "test"), required=True)
    parser.add_argument("--primary", type=Path, required=True)
    parser.add_argument("--secondary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        compare(args.manifest, args.split, args.primary, args.secondary, args.output)
    except (OSError, KeyError, TypeError, ValueError) as error:
        parser.exit(1, f"Could not compare detector events: {error}\n")


if __name__ == "__main__":
    main()

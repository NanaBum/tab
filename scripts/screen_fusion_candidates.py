"""Select a fixed screen for added detector events on validation, then score test."""

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from compare_detector_fusion import read_results
from evaluate_onset_excerpts import load_partition, reuse_inputs

from tabber.evaluation import score_notes
from tabber.fusion import complementary_notes
from tabber.guitar_gaps import CHECKPOINT_SHA256, gaps_activations
from tabber.media import sha256_file

THRESHOLDS = (0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0)


def onset_support(note, activations):
    pitch = note.pitch - 21
    center = round(note.start * 100)
    window = activations[max(0, center - 5) : center + 6]
    if not len(window) or not 0 <= pitch < activations.shape[1]:
        return 0.0
    return float(window[:, pitch].max())


def load_candidates(manifest, split, excerpts, gaps, basic):
    digest = sha256_file(manifest)
    stems = reuse_inputs(basic, digest, split, excerpts)
    rows = []
    for (row, _, reference), stem, primary, secondary in zip(
        excerpts,
        stems,
        read_results(gaps, digest, split, excerpts),
        read_results(basic, digest, split, excerpts),
        strict=True,
    ):
        a_name, a, a_notes = primary
        b_name, b, b_notes = secondary
        if (a_name, b_name) != ("guitar-gaps", "basic-pitch") or (
            a["detector_input_sha256"] != b["detector_input_sha256"]
        ):
            raise ValueError("Expected GAPS and Basic Pitch results on the same stem")
        activation, _ = gaps_activations(stem)
        extras = [
            (note, onset_support(note, activation["reg_onset_output"]))
            for note, p, _ in complementary_notes(a_notes, b_notes)
            if p is None
        ]
        rows.append((reference, a_notes, extras))
        print(f"{split} {row['song_id']}: {len(extras)} added candidates", flush=True)
    return rows


def score(rows, keep):
    clips = [
        asdict(
            score_notes(
                reference,
                primary + [n for n, support in extras if keep(n, support)],
                onset_tolerance=0.075,
            )
        )
        for reference, primary, extras in rows
    ]
    totals = {
        key: sum(clip[key] for clip in clips)
        for key in ("reference_notes", "predicted_notes", "matched_notes")
    }
    totals["unmatched_notes"] = totals["predicted_notes"] - totals["matched_notes"]
    denominator = totals["reference_notes"] + totals["predicted_notes"]
    totals["f1"] = 2 * totals["matched_notes"] / denominator if denominator else 0.0
    return {**totals, "excerpts": clips}


def choose(rows, value):
    results = [
        (cutoff, score(rows, lambda note, support, cutoff=cutoff: value(note, support) >= cutoff))
        for cutoff in THRESHOLDS
    ]
    return max(results, key=lambda result: (result[1]["f1"], -result[1]["unmatched_notes"]))


def run(args):
    validation_excerpts = load_partition(args.validation_manifest, "validation")
    test_excerpts = load_partition(args.test_manifest, "test")
    for key in ("song_id", "original_recording_sha256", "decoded_audio_sha256"):
        if {row[key] for row, _, _ in validation_excerpts} & {
            row[key] for row, _, _ in test_excerpts
        }:
            raise ValueError("Validation and test must use distinct songs and recordings")
    validation = load_candidates(
        args.validation_manifest, "validation", validation_excerpts, *args.validation_results
    )
    rules = {"gaps_onset": lambda n, s: s, "basic_confidence": lambda n, s: n.confidence}
    selected = {name: choose(validation, value) for name, value in rules.items()}
    for name, (cutoff, _) in selected.items():
        print(f"Selected validation cutoff for {name}: {cutoff}", flush=True)
    test = load_candidates(args.test_manifest, "test", test_excerpts, *args.test_results)
    report = {
        "gaps_checkpoint_sha256": CHECKPOINT_SHA256,
        "validation_manifest_sha256": sha256_file(args.validation_manifest),
        "test_manifest_sha256": sha256_file(args.test_manifest),
        "threshold_grid": THRESHOLDS,
        "policy": "Keep all GAPS notes. Screen Basic Pitch additions by frozen scores. Choose cutoff by validation micro F1, then fewer unmatched detections. Apply unchanged to test.",
        "validation": {
            "gaps": score(validation, lambda n, s: False),
            "union": score(validation, lambda n, s: True),
        },
        "test": {"gaps": score(test, lambda n, s: False), "union": score(test, lambda n, s: True)},
    }
    for name, (cutoff, measured) in selected.items():
        value = rules[name]
        report["validation"][name] = {"cutoff": cutoff, **measured}
        measured_test = score(test, lambda n, s, value=value, cutoff=cutoff: value(n, s) >= cutoff)
        report["test"][name] = {"cutoff": cutoff, **measured_test}
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validation-manifest", type=Path, required=True)
    parser.add_argument(
        "--validation-results", type=Path, nargs=2, required=True, metavar=("GAPS", "BASIC")
    )
    parser.add_argument("--test-manifest", type=Path, required=True)
    parser.add_argument(
        "--test-results", type=Path, nargs=2, required=True, metavar=("GAPS", "BASIC")
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        run(args)
    except (OSError, KeyError, TypeError, ValueError, RuntimeError) as error:
        parser.exit(1, f"Could not screen detector candidates: {error}\n")


if __name__ == "__main__":
    main()

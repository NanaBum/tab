"""Evaluate a saved onset ranker on verified, held-out guitar stems."""

import argparse
import json
from dataclasses import asdict
from pathlib import Path

import numpy as np
from evaluate_onset_excerpts import load_partition, reuse_inputs, verified_asset
from train_stem_onset_ranker import candidates, score_budget

from tabber.evaluation import score_notes
from tabber.guitar_gaps import CHECKPOINT_SHA256, decode_gaps, gaps_activations
from tabber.media import sha256_file


def evaluate(training_manifest, cache, weights_dir, stem_manifest, stem_results, destination):
    training_hash = sha256_file(training_manifest)
    cached = cache / "cache.json"
    fitted = json.loads((weights_dir / "report.json").read_text(encoding="utf-8"))
    prepared = json.loads(cached.read_text(encoding="utf-8"))
    if (
        prepared["manifest_sha256"] != training_hash
        or prepared["checkpoint_sha256"] != CHECKPOINT_SHA256
        or fitted["cache_sha256"] != sha256_file(cached)
        or any(row["split"] not in {"train", "validation"} for row in prepared["clips"])
    ):
        raise ValueError("Checkpoint and cache do not describe the supplied training split")
    weights_path = verified_asset(weights_dir, "weights.npz", fitted["weights_sha256"])
    with np.load(weights_path, allow_pickle=False) as state:
        weights = state["weights"]
    if weights.shape != (9,) or not np.isfinite(weights).all():
        raise ValueError("Invalid onset-ranker weights")

    held_out = load_partition(training_manifest, "test")
    from_stem_manifest = load_partition(stem_manifest, "test")
    if [row for row, _, _ in held_out] != [row for row, _, _ in from_stem_manifest]:
        raise ValueError("The stem dataset's test rows differ from the held-out partition")
    stems = reuse_inputs(stem_results, sha256_file(stem_manifest), "test", from_stem_manifest)
    report = {
        "purpose": "Evaluate frozen onset rankings against the fixed test partition",
        "training_manifest_sha256": training_hash,
        "weights_sha256": sha256_file(weights_path),
        "stem_report_sha256": sha256_file(stem_results / "report.json"),
        "limits": "Score-derived onset labels. Each ranker uses the original decoder's count, so an empty baseline stays empty. No fitting or duration scoring.",
        "excerpts": [],
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("x", encoding="utf-8") as stream:
        for (row, _, reference), stem in zip(held_out, stems, strict=True):
            output, duration = gaps_activations(stem)
            baseline = decode_gaps(output, duration)
            events, features = candidates(output, duration)
            budget = len(baseline)
            if len(events) < budget:
                raise ValueError("Candidate pool cannot match the baseline detection budget")
            report["excerpts"].append(
                {
                    "song_id": row["song_id"],
                    "stem_sha256": sha256_file(stem),
                    "labels_sha256": row["labels_sha256"],
                    "baseline": asdict(score_notes(reference, baseline, onset_tolerance=0.075)),
                    "raw_onset_rank": score_budget(reference, events, features[:, 0], budget),
                    "learned_rank": score_budget(reference, events, features @ weights, budget),
                    "candidate_ceiling": asdict(
                        score_notes(reference, events, onset_tolerance=0.075)
                    ),
                }
            )
            print(f"{row['song_id']}: {budget} detections per condition", flush=True)
        json.dump(report, stream, indent=2)
        stream.write("\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("training_manifest", type=Path)
    parser.add_argument("--cache", required=True, type=Path)
    parser.add_argument("--weights-dir", required=True, type=Path)
    parser.add_argument("--stem-manifest", required=True, type=Path)
    parser.add_argument("--stem-results", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        evaluate(
            args.training_manifest,
            args.cache,
            args.weights_dir,
            args.stem_manifest,
            args.stem_results,
            args.output,
        )
    except (OSError, KeyError, TypeError, ValueError, RuntimeError) as error:
        parser.exit(1, f"Could not evaluate onset ranker: {error}\n")


if __name__ == "__main__":
    main()

"""Small local ranking experiment on frozen guitar stems, with score labels."""

import argparse
import json
import tempfile
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path

import numpy as np
from evaluate_onset_excerpts import load_partition, verified_asset
from scipy.signal import find_peaks
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from tabber.evaluation import match_notes, score_notes
from tabber.guitar_gaps import CHECKPOINT_SHA256, decode_gaps
from tabber.media import sha256_file
from tabber.models import Note

SEED = 33


def candidates(output, duration):
    onset, frame = output["reg_onset_output"], output["frame_output"]
    events, features = [], []
    for pitch in range(36, 89):
        j = pitch - 21
        on, sustained = onset[:, j], frame[:, j]
        rise = np.maximum(0, sustained - np.pad(sustained, (4, 0), mode="edge")[: len(sustained)])
        combined = np.maximum(on, 0.5 * rise)
        for i in find_peaks(combined, height=0.035, distance=5)[0]:
            t = i / 100
            if t >= duration:
                continue
            pre, post = sustained[max(0, i - 5) : i], sustained[i : i + 8]
            octave = frame[i, j - 12] if j >= 12 else 0
            above = frame[i, j + 12] if j + 12 < frame.shape[1] else 0
            nearby = onset[max(0, i - 2) : i + 3, max(0, j - 1) : j + 2].max()
            events.append(Note(t, min(t + 0.01, duration), pitch, float(np.clip(on[i], 0, 1))))
            features.append(
                [
                    on[i],
                    sustained[i],
                    rise[i],
                    post.mean(),
                    post.max(),
                    post.mean() - (pre.mean() if len(pre) else 0),
                    sustained[i] - octave,
                    sustained[i] - above,
                    on[i] - nearby,
                ]
            )
    return events, np.asarray(features).reshape(-1, 9)


def pair_examples(events, features, reference, rng):
    positives = {pred for _, pred in match_notes(reference, events, onset_tolerance=0.075)}
    reference_times, negatives = defaultdict(list), defaultdict(list)
    for note in reference:
        reference_times[note.pitch].append(note.start)
    for i, note in enumerate(events):
        if i not in positives and all(
            abs(note.start - t) > 0.15 for t in reference_times[note.pitch]
        ):
            negatives[note.pitch].append(i)
    diffs = []
    for i in sorted(positives):
        pool = negatives[events[i].pitch]
        if pool:
            for k in rng.choice(pool, size=min(4, len(pool)), replace=False):
                diffs.append(features[i] - features[k])
    return diffs


def load_cached_scores(manifest, cache):
    cache_info = json.loads((cache / "cache.json").read_text(encoding="utf-8"))
    if (
        cache_info.get("format") != "tabber-guitar-training-cache"
        or cache_info.get("schema_version") != 1
        or cache_info.get("manifest_sha256") != sha256_file(manifest)
        or cache_info.get("checkpoint_sha256") != CHECKPOINT_SHA256
    ):
        raise ValueError("Cache does not match this dataset and pinned checkpoint")
    expected = {}
    for split in ("train", "validation"):
        for i, (row, _, reference) in enumerate(load_partition(manifest, split), 1):
            expected[f"{split}-{i:03d}"] = (row, reference)
    for record in cache_info["clips"]:
        clip = record["clip"]
        row, reference = expected.pop(clip)
        for key in ("audio_sha256", "labels_sha256", "split", "song_id"):
            if record[key] != row[key]:
                raise ValueError(f"Cache identity mismatch for {clip}")
        archive = verified_asset(cache, f"{clip}/activations.npz", record["activations_sha256"])
        with np.load(archive, allow_pickle=False) as saved:
            duration = float(saved["duration_seconds"])
            output = {key: saved[key] for key in saved.files if key != "duration_seconds"}
        yield record, reference, output, duration
    if expected:
        raise ValueError("Cache is missing training or validation entries")


def score_budget(reference, events, ranking, count):
    top = np.argsort(-ranking, kind="stable")[:count]
    return asdict(score_notes(reference, [events[i] for i in top], onset_tolerance=0.075))


def train(manifest, cache, destination):
    if destination.exists():
        raise FileExistsError("Choose a fresh checkpoint directory")
    rng = np.random.default_rng(SEED)
    examples, validation = defaultdict(list), []
    clips_with_pairs = 0
    for record, reference, output, duration in load_cached_scores(manifest, cache):
        events, features = candidates(output, duration)
        if record["split"] == "train":
            pairs = pair_examples(events, features, reference, rng)
            if pairs:
                examples[record["song_id"]].extend(pairs)
                clips_with_pairs += 1
        else:
            validation.append((record, reference, events, features, decode_gaps(output, duration)))
    if not examples:
        raise ValueError("No same-pitch training pairs")
    matrix = np.concatenate(list(examples.values()))
    pair_weights = np.concatenate(
        [np.full(len(pairs), 1 / len(pairs)) for pairs in examples.values()]
    )
    pair_weights /= pair_weights.mean()
    comparison = np.r_[matrix, -matrix]
    targets = np.r_[np.ones(len(matrix)), np.zeros(len(matrix))]
    scaler = StandardScaler(with_mean=False)
    model = LogisticRegression(C=0.5, fit_intercept=False, max_iter=300, random_state=SEED)
    balanced_weights = np.r_[pair_weights, pair_weights]
    scaler.fit(comparison, sample_weight=balanced_weights)
    model.fit(scaler.transform(comparison), targets, sample_weight=balanced_weights)
    weights = model.coef_[0] / scaler.scale_

    reports = []
    for record, refs, events, features, base in validation:
        count = len(base)
        if len(events) < count:
            raise ValueError("Candidate pool cannot match the baseline detection budget")
        reports.append(
            {
                "clip": record["clip"],
                "song_id": record["song_id"],
                "baseline": asdict(score_notes(refs, base, onset_tolerance=0.075)),
                "raw_onset_rank": score_budget(refs, events, features[:, 0], count),
                "learned_rank": score_budget(refs, events, features @ weights, count),
                "candidate_ceiling": asdict(score_notes(refs, events, onset_tolerance=0.075)),
            }
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".ranker-stage-", dir=destination.parent) as directory:
        stage = Path(directory) / "checkpoint"
        stage.mkdir()
        np.savez(stage / "weights.npz", weights=weights, seed=SEED)
        report = {
            "cache_sha256": sha256_file(cache / "cache.json"),
            "weights_sha256": sha256_file(stage / "weights.npz"),
            "train_preference_pairs": len(matrix),
            "train_clips_with_pairs": clips_with_pairs,
            "train_pairs_by_song": {song: len(pairs) for song, pairs in examples.items()},
            "validation": reports,
            "limits": "Weak score labels and equal detection counts. Attacks only. The test partition was not loaded.",
        }
        (stage / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        if destination.exists():
            raise FileExistsError("Choose a fresh checkpoint directory")
        stage.rename(destination)
    print(json.dumps(report, indent=2), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        train(args.manifest, args.cache, args.output.resolve())
    except (OSError, KeyError, TypeError, ValueError, RuntimeError) as error:
        parser.exit(1, f"Could not train onset ranker: {error}\n")


if __name__ == "__main__":
    main()

"""Test a small learned filter on guitar-model candidates, grouped by phrase."""

import argparse
import json
import tempfile
from dataclasses import asdict
from pathlib import Path

import numpy as np
from sweep_guitar_onsets import SELECTION

from tabber.evaluation import idmt_recording, match_notes, score_notes
from tabber.guitar_gaps import CHECKPOINT_SHA256, decode_gaps, gaps_activations
from tabber.media import sha256_file

FEATURES = (
    "onset_activation",
    "mean_pitch_activation_first_80ms",
    "peak_pitch_activation_first_80ms",
    "pitch_activation_change_at_attack",
    "relative_octave_activation",
    "duration_seconds",
)


def pitch_features(output, notes):
    frames = output["frame_output"]
    data = []
    for note in notes:
        frame = min(round(note.start * 100), len(frames) - 1)
        pitch = note.pitch - 21
        after = frames[frame : frame + 8, pitch]
        before = frames[max(0, frame - 5) : frame, pitch]
        octaves = [index for index in (pitch - 12, pitch + 12) if 0 <= index < frames.shape[1]]
        competing = frames[frame : frame + 8, octaves].max() if octaves else 0
        after_mean = after.mean()
        data.append(
            (
                note.confidence,
                after_mean,
                after.max(),
                after_mean - (before.mean() if before.size else 0),
                after.max() - competing,
                min(note.end - note.start, 1),
            )
        )
    return np.asarray(data, dtype=float).reshape(-1, len(FEATURES))


def phrase_group(name):
    if name.startswith("AR_Lick"):
        return name.rsplit("_", 1)[0]
    if name.startswith("pathetique_"):
        return "pathetique"
    return name


def load_clips(data, cache):
    clips = []
    cache.mkdir(parents=True, exist_ok=True)
    for group, names in SELECTION.items():
        for name in names:
            wav = data / group / "audio" / f"{name}.wav"
            xml = data / group / "annotation" / f"{name}.xml"
            audio_hash = sha256_file(wav)
            cache_file = cache / f"{audio_hash}-{CHECKPOINT_SHA256}.npz"
            if cache_file.exists():
                with np.load(cache_file, allow_pickle=False) as saved:
                    output = {key: saved[key] for key in saved.files if key != "duration_seconds"}
                    duration = float(saved["duration_seconds"])
            else:
                output, duration = gaps_activations(wav)
                with tempfile.TemporaryDirectory(dir=cache) as staging:
                    staged = Path(staging) / "activations.npz"
                    np.savez_compressed(staged, duration_seconds=duration, **output)
                    staged.replace(cache_file)
            reference = idmt_recording(xml.read_text(encoding="utf-8-sig")).notes
            conditions = {
                f"threshold_{threshold:.2f}": decode_gaps(
                    output, duration, onset_threshold=threshold
                )
                for threshold in (0.12, 0.18, 0.30, 0.42)
            }
            candidates = conditions["threshold_0.12"]
            positive = {index for _, index in match_notes(reference, candidates)}
            clips.append(
                {
                    "clip": name,
                    "phrase_group": phrase_group(name),
                    "audio_sha256": audio_hash,
                    "reference_sha256": sha256_file(xml),
                    "reference": reference,
                    "conditions": conditions,
                    "candidates": candidates,
                    "features": pitch_features(output, candidates),
                    "targets": np.array([index in positive for index in range(len(candidates))]),
                }
            )
            print(f"Prepared {name}: {len(candidates)} candidates", flush=True)
    return clips


def results(clips):
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    rows = []
    for group in sorted({clip["phrase_group"] for clip in clips}):
        train = [clip for clip in clips if clip["phrase_group"] != group]
        features = np.concatenate([clip["features"] for clip in train])
        target = np.concatenate([clip["targets"] for clip in train])
        model = make_pipeline(StandardScaler(), LogisticRegression(C=0.2, max_iter=300))
        model.fit(features, target)
        for clip in (row for row in clips if row["phrase_group"] == group):
            probabilities = (
                model.predict_proba(clip["features"])[:, 1] if clip["candidates"] else []
            )
            retained = [
                note
                for note, probability in zip(clip["candidates"], probabilities, strict=True)
                if probability >= 0.5
            ]
            conditions = {**clip["conditions"], "learned_filter": retained}
            row = {
                key: clip[key]
                for key in ("clip", "phrase_group", "audio_sha256", "reference_sha256")
            }
            row["scores"] = {}
            for name, notes in conditions.items():
                onset = score_notes(clip["reference"], notes)
                row["scores"][name] = {
                    "onsets": asdict(onset),
                    "onsets_and_releases": asdict(
                        score_notes(clip["reference"], notes, offsets=True)
                    ),
                    "missed": onset.reference_notes - onset.matched_notes,
                    "extra": onset.predicted_notes - onset.matched_notes,
                }
            rows.append(row)
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("data/idmt"))
    parser.add_argument("--cache", type=Path, default=Path("runs/gaps-activation-cache"))
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Choose a fresh report")
    rows = results(load_clips(args.data, args.cache))
    report = {
        "purpose": "Compare a learned candidate filter with fixed thresholds in grouped development folds",
        "features": FEATURES,
        "acceptance_probability": 0.5,
        "checkpoint_sha256": CHECKPOINT_SHA256,
        "limits": "Tiny development set. The learned filter holds out each phrase group in turn. Pretraining overlap is unresolved.",
        "tracks": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")


if __name__ == "__main__":
    main()

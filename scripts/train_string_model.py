"""Experimental CPU-only string classifier; requires the separate ML environment.

The fixed split is performers 01-04 train, 05 validation, 00 test. Evaluation uses
oracle pitch/timing and isolated single-note windows, not end-to-end transcription.
"""

import argparse
import io
import json
import time
import zipfile
from pathlib import Path

import numpy as np
import soundfile as sf
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, balanced_accuracy_score, confusion_matrix
from sklearn.preprocessing import StandardScaler

from tabber.evaluation import guitarset_notes
from tabber.models import STANDARD_TUNING
from tabber.string_model import FEATURE_VERSION, audio_features, isolated_features, pitch_features


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("data/guitarset"))
    parser.add_argument("--models", type=Path, default=Path("models"))
    parser.add_argument("--report", type=Path, default=Path("runs/string-model-evaluation.json"))
    args = parser.parse_args()
    args.models.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    cache = args.models / "string-training-features-v1.npz"
    start = time.perf_counter()
    if cache.exists():
        with np.load(cache, allow_pickle=False) as source:
            if int(source["feature_version"]) != FEATURE_VERSION:
                raise ValueError("Feature cache version mismatch")
            features, labels, players, pitches = [
                source[k] for k in ("features", "labels", "players", "pitches")
            ]
    else:
        features, labels, players, pitches = [], [], [], []
        with (
            zipfile.ZipFile(args.data / "annotation.zip") as annotations,
            zipfile.ZipFile(args.data / "audio_mono-mic.zip") as audio,
        ):
            names = sorted(n for n in annotations.namelist() if n.endswith("_solo.jams"))
            for index, name in enumerate(names):
                if index % 10 == 0:
                    print(
                        f"Extracting clip {index}/{len(names)}; accepted notes {len(labels)}",
                        flush=True,
                    )
                reference = guitarset_notes(json.loads(annotations.read(name)))
                notes = [n.note for n in reference]
                waveform, rate = sf.read(io.BytesIO(audio.read(Path(name).stem + "_mic.wav")))
                waveform, mfcc = audio_features(waveform, rate)
                rows = isolated_features(waveform, mfcc, notes)
                for note, row in zip(reference, rows):
                    if row is None or not 0 <= note.fret <= 24:
                        continue
                    features.append(row)
                    labels.append(note.string)
                    players.append(name[:2])
                    pitches.append(note.note.pitch)
        features, labels, players, pitches = map(np.asarray, (features, labels, players, pitches))
        np.savez_compressed(
            cache,
            feature_version=FEATURE_VERSION,
            features=features,
            labels=labels,
            players=players,
            pitches=pitches,
        )
    train = np.isin(players, ("01", "02", "03", "04"))
    splits = {"validation": players == "05", "test": players == "00"}
    report = {
        "protocol": "Oracle pitch/onset/duration, isolated solo-note windows; same dataset/guitar domain",
        "split": {"train": ["01", "02", "03", "04"], "validation": ["05"], "test": ["00"]},
        "samples": {"train": int(train.sum()), **{k: int(m.sum()) for k, m in splits.items()}},
        "hyperparameters": "LogisticRegression C=1, max_iter=2000, random_state=0; no test tuning",
        "results": {},
        "source": "GuitarSet v1.1.0, Zenodo 3371780, CC BY 4.0; cite Xi et al. ISMIR 2018",
    }
    one_hot = pitch_features(pitches)
    for label, x in (
        ("pitch_only", one_hot),
        ("pitch_plus_timbre", np.column_stack((one_hot, features))),
    ):
        scaler = StandardScaler().fit(x[train])
        model = LogisticRegression(C=1, max_iter=2000, random_state=0).fit(
            scaler.transform(x[train]), labels[train]
        )
        results = {}
        for name, mask in splits.items():
            probabilities = model.predict_proba(scaler.transform(x[mask]))
            valid = np.array(
                [
                    [0 <= pitch - STANDARD_TUNING[int(s)] <= 24 for s in model.classes_]
                    for pitch in pitches[mask]
                ]
            )
            probabilities *= valid
            predicted = model.classes_[np.argmax(probabilities, axis=1)]
            results[name] = {
                "accuracy": accuracy_score(labels[mask], predicted),
                "balanced_accuracy": balanced_accuracy_score(labels[mask], predicted),
                "confusion": confusion_matrix(
                    labels[mask], predicted, labels=list(range(6))
                ).tolist(),
            }
        report["results"][label] = results
        if label == "pitch_plus_timbre":
            np.savez_compressed(
                args.models / "string-timbre-v1.npz",
                feature_version=FEATURE_VERSION,
                mean=scaler.mean_,
                scale=scaler.scale_,
                coefficients=model.coef_,
                intercept=model.intercept_,
                classes=model.classes_,
            )
    report["elapsed_seconds"] = time.perf_counter() - start
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()

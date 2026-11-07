"""Exploratory rotating-performer audit of fixed string-model features/parameters.

Run train_string_model.py first to create the ignored numeric feature cache.
This script does not change or overwrite the optional inference model.
"""

import argparse
import json
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, balanced_accuracy_score, precision_recall_fscore_support
from sklearn.preprocessing import StandardScaler

from tabber.models import STANDARD_TUNING
from tabber.string_model import FEATURE_VERSION, pitch_features


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--features", type=Path, default=Path("models/string-training-features-v1.npz")
    )
    parser.add_argument("--output", type=Path, default=Path("runs/string-cross-validation.json"))
    args = parser.parse_args()
    with np.load(args.features, allow_pickle=False) as cache:
        if int(cache["feature_version"]) != FEATURE_VERSION:
            raise ValueError("Feature-cache version mismatch")
        features, labels, players, pitches = [
            cache[k] for k in ("features", "labels", "players", "pitches")
        ]
    one_hot = pitch_features(pitches)
    report = {
        "purpose": "Exploratory fixed-parameter rotating performer checks; oracle isolated-note windows",
        "protocol": "Each performer tests once; preceding performer validates; remaining four train",
        "parameters": "LogisticRegression C=1, max_iter=2000; scaling fits train only; no test tuning",
        "source": "GuitarSet v1.1.0, CC BY 4.0, Xi et al., ISMIR 2018; same recording domain",
        "feature_version": FEATURE_VERSION,
        "folds": [],
        "summary": {},
    }
    for held in range(6):
        player, validation = f"{held:02}", f"{(held - 1) % 6:02}"
        train = (players != player) & (players != validation)
        test = players == player
        row = {
            "test_performer": player,
            "validation_performer": validation,
            "train_notes": int(train.sum()),
            "test_notes": int(test.sum()),
            "models": {},
        }
        valid = np.array(
            [[0 <= pitch - tuning <= 24 for tuning in STANDARD_TUNING] for pitch in pitches[test]]
        )
        for name, x in (
            ("pitch_only", one_hot),
            ("pitch_plus_timbre", np.column_stack((one_hot, features))),
        ):
            scaler = StandardScaler().fit(x[train])
            model = LogisticRegression(C=1, max_iter=2000, random_state=0).fit(
                scaler.transform(x[train]), labels[train]
            )
            prediction = model.classes_[
                np.argmax(model.predict_proba(scaler.transform(x[test])) * valid, axis=1)
            ]
            result = {
                "accuracy": accuracy_score(labels[test], prediction),
                "balanced_accuracy": balanced_accuracy_score(labels[test], prediction),
                "correct": int(np.sum(labels[test] == prediction)),
            }
            # Only ambiguous open pitches; exclude low E, whose string is forced.
            subset = np.isin(pitches[test], STANDARD_TUNING[:-1])
            actual_open = pitches[test][subset] == np.array(STANDARD_TUNING)[labels[test][subset]]
            predicted_open = pitches[test][subset] == np.array(STANDARD_TUNING)[prediction[subset]]
            precision, recall, f1, _ = precision_recall_fscore_support(
                actual_open, predicted_open, average="binary", zero_division=0
            )
            result["ambiguous_open_pitch_subset"] = {
                "notes": int(subset.sum()),
                "reference_open": int(actual_open.sum()),
                "open_precision": precision,
                "open_recall": recall,
                "open_f1": f1,
            }
            row["models"][name] = result
        report["folds"].append(row)
        print(
            f"Held-out performer {player}: "
            + str({k: round(v["accuracy"], 4) for k, v in row["models"].items()}),
            flush=True,
        )
    for name in ("pitch_only", "pitch_plus_timbre"):
        scores = [r["models"][name]["accuracy"] for r in report["folds"]]
        report["summary"][name] = {
            "mean_performer_accuracy": float(np.mean(scores)),
            "min_performer_accuracy": float(np.min(scores)),
            "max_performer_accuracy": float(np.max(scores)),
            "pooled_accuracy": sum(r["models"][name]["correct"] for r in report["folds"])
            / len(labels),
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], indent=2))


if __name__ == "__main__":
    main()

"""Fit fixed electric string priors, or score frozen checkpoints on held-out notes."""

import argparse
import json
from pathlib import Path

import numpy as np

from tabber.media import sha256_file
from tabber.models import STANDARD_TUNING
from tabber.string_model import FEATURE_VERSION, StringModel, pitch_features

MODELS = ("electric-pitch-only", "electric-pitch-timbre")
KEYS = ("features", "pitch", "string", "player", "take", "channel", "midi_start")


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_features(folder, split, expected_players):
    report = read_json(folder / "report.json")
    path = folder / "features.npz"
    digest = sha256_file(path)
    if report["features_sha256"] != digest or report["split"] != split:
        raise ValueError("Cache and report must identify the requested split")
    with np.load(path, allow_pickle=False) as data:
        if str(data["split"]) != split or int(data["feature_version"]) != FEATURE_VERSION:
            raise ValueError("Cache feature version or split differs")
        arrays = {key: data[key] for key in KEYS}
    count = len(arrays["pitch"])
    if (
        arrays["features"].shape != (count, 39)
        or not np.isfinite(arrays["features"]).all()
        or any(arrays[k].shape != (count,) for k in KEYS[1:])
        or set(arrays["player"]) != expected_players
        or arrays["pitch"].dtype.kind not in "iu"
        or arrays["string"].dtype.kind not in "iu"
        or np.any((arrays["string"] < 0) | (arrays["string"] >= 6))
    ):
        raise ValueError("Cache has invalid feature rows or player identities")
    open_pitch = np.asarray(STANDARD_TUNING)[arrays["string"]]
    if np.any((arrays["pitch"] < open_pitch) | (arrays["pitch"] > open_pitch + 24)):
        raise ValueError("Cache contains an impossible string for its pitch")
    return arrays, digest


def save_report(path, report):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")


def fit(development, output):
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler

    data, digest = load_features(development, "development", {"P1", "P2"})
    if set(data["string"]) != set(range(6)):
        raise ValueError("Development features must cover all six strings")
    output.mkdir(parents=True, exist_ok=False)
    models = {}
    pitches = pitch_features(data["pitch"])
    for name, features in zip(
        MODELS, (np.zeros_like(data["features"]), data["features"]), strict=True
    ):
        x = np.column_stack((pitches, features))
        scaler = StandardScaler().fit(x)
        model = LogisticRegression(C=1, max_iter=2000, random_state=0).fit(
            scaler.transform(x), data["string"]
        )
        if np.any(model.n_iter_ >= 2000):
            raise ValueError("String model did not converge within its fixed budget")
        target = output / f"{name}.npz"
        np.savez_compressed(
            target,
            feature_version=FEATURE_VERSION,
            mean=scaler.mean_,
            scale=scaler.scale_,
            coefficients=model.coef_,
            intercept=model.intercept_,
            classes=model.classes_,
        )
        StringModel(target)
        models[name] = sha256_file(target)
    save_report(
        output / "report.json",
        {
            "development_features_sha256": digest,
            "players": ["P1", "P2"],
            "training_rows": len(data["pitch"]),
            "models_sha256": models,
            "policy": "StandardScaler and fixed logistic regression C=1. P1/P2 only. Both controls use the same note windows.",
        },
    )


def evaluate(test, weights, original, output):
    data, digest = load_features(test, "test", {"P3"})
    fitted = read_json(weights / "report.json")
    if fitted["players"] != ["P1", "P2"] or fitted["development_features_sha256"] == digest:
        raise ValueError("Checkpoints do not identify independent development players")
    paths = {name: weights / f"{name}.npz" for name in MODELS}
    for name, path in paths.items():
        if sha256_file(path) != fitted["models_sha256"][name]:
            raise ValueError(f"Checkpoint checksum failed: {name}")
    paths["guitarset-timbre"] = original
    pitch, target = data["pitch"], data["string"]
    allowed = pitch[:, None] - np.asarray(STANDARD_TUNING)
    ambiguous = np.sum((allowed >= 0) & (allowed <= 24), axis=1) > 1
    slices = {"all_ambiguous": ambiguous}
    for channel in sorted(set(data["channel"])):
        matching_channel = data["channel"] == channel
        slices[channel] = ambiguous & matching_channel
        for take in sorted(set(data["take"])):
            mask = ambiguous & matching_channel & (data["take"] == take)
            if mask.any():
                slices[f"{channel}/{take}"] = mask
    scores = {}
    for name, path in paths.items():
        features = np.zeros_like(data["features"]) if name == MODELS[0] else data["features"]
        predicted = StringModel(path).predict(pitch, features).argmax(axis=1)
        scores[name] = {
            "weights_sha256": sha256_file(path),
            "counts": {
                label: {
                    "correct": int((predicted[mask] == target[mask]).sum()),
                    "total": int(mask.sum()),
                }
                for label, mask in slices.items()
            },
        }
    save_report(
        output,
        {
            "test_features_sha256": digest,
            "fit_report_sha256": sha256_file(weights / "report.json"),
            "scores": scores,
            "limits": "One held-out guitarist. Audio views share performances. Oracle MIDI pitch and timing. Classification only, without a fingering solver or note detector.",
        },
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    train = commands.add_parser("fit")
    train.add_argument("development", type=Path)
    train.add_argument("--output", type=Path, required=True)
    score = commands.add_parser("evaluate")
    score.add_argument("test", type=Path)
    score.add_argument("--weights", type=Path, required=True)
    score.add_argument("--original", type=Path, required=True)
    score.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "fit":
            fit(args.development, args.output)
        else:
            evaluate(args.test, args.weights, args.original, args.output)
    except (OSError, KeyError, TypeError, ValueError, RuntimeError) as error:
        parser.exit(1, f"Could not run Guitar-TECHS timbre pilot: {error}\n")


if __name__ == "__main__":
    main()

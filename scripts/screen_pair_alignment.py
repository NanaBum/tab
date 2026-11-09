"""Screen a batch of collected pairs for start offsets and tempo drift."""

import argparse
import json
import subprocess
from pathlib import Path

import mido
import numpy as np
from scipy.ndimage import gaussian_filter1d

from tabber.media import find_ffmpeg, sha256_file

RATE = 22050
HOP = 1024
STEP = HOP / RATE
MAX_DURATION = 900


def score_features(midi):
    if midi.type not in (0, 1) or midi.ticks_per_beat <= 0 or not 0 < midi.length <= MAX_DURATION:
        raise ValueError("Use a synchronous score of up to 15 minutes")
    changes = np.zeros((int(np.ceil(midi.length / STEP)) + 1, 12))
    time = 0.0
    for message in midi:
        time += message.time
        if message.type in ("note_on", "note_off") and message.channel != 9:
            attack = message.type == "note_on" and message.velocity > 0
            changes[round(time / STEP), message.note % 12] += 1 if attack else -1
    chroma = changes.cumsum(axis=0)
    if np.any(chroma < 0) or np.any(chroma[-1]):
        raise ValueError("MIDI note attack/release counts do not balance")
    return chroma


def unit_chroma(chroma):
    features = gaussian_filter1d(np.sqrt(chroma), 1, axis=0)
    features -= features.mean(axis=1, keepdims=True)
    return features / np.maximum(np.linalg.norm(features, axis=1, keepdims=True), 1e-8)


def scan_windows(score, audio):
    radius = round(6 / STEP)
    length = round(24 / STEP)
    lags = np.arange(-radius, radius + 1)
    right = min(len(score), len(audio)) - radius
    curves, rows = [], []
    for start in range(radius, right, length):
        end = min(start + length, right)
        if end - start < round(12 / STEP):
            continue
        indices = np.arange(start, end)
        indices = indices[np.linalg.norm(score[indices], axis=1) > 0.9]
        if len(indices) < round(6 / STEP):
            continue
        curve = np.array(
            [np.mean(np.sum(audio[indices + lag] * score[indices], axis=1)) for lag in lags]
        )
        best = int(np.argmax(curve))
        separated = np.abs(lags - lags[best]) >= round(0.4 / STEP)
        curves.append(curve)
        rows.append(
            {
                "score_start_seconds": round(start * STEP, 3),
                "score_end_seconds": round(end * STEP, 3),
                "best_shift_seconds": round(lags[best] * STEP, 3),
                "peak_similarity": round(float(curve[best]), 4),
                "peak_margin_at_least_0_4_seconds": round(
                    float(curve[best] - max(curve[separated])), 4
                ),
                "peak_at_search_boundary": best in (0, len(lags) - 1),
            }
        )
    if not curves:
        raise ValueError("No overlapping windows with enough sounding score frames")
    average = np.mean(curves, axis=0)
    best = int(np.argmax(average))
    for row, curve in zip(rows, curves, strict=True):
        row["similarity_at_global_shift"] = round(float(curve[best]), 4)
    result = {
        "global_shift_seconds": round(lags[best] * STEP, 3),
        "global_mean_similarity": round(float(average[best]), 4),
        "windows": rows,
    }
    if len(rows) >= 4:
        centers = np.array(
            [(row["score_start_seconds"] + row["score_end_seconds"]) / 2 for row in rows]
        )
        shifts = np.array([row["best_shift_seconds"] for row in rows])
        middle = len(rows) // 2
        slope, intercept = np.polyfit(centers[:middle], shifts[:middle], 1)
        residual = shifts[middle:] - (slope * centers[middle:] + intercept)
        result["early_fit"] = {
            "score_scale": round(float(1 + slope), 6),
            "score_shift_seconds": round(float(intercept), 4),
            "fit_windows": middle,
            "later_shift_residuals_seconds": np.round(residual, 4).tolist(),
        }
    return result


def pair_asset(path, pair, role):
    relative = pair["roles"][role]
    asset = (path.parent / relative).resolve()
    if not asset.is_relative_to(path.parent.resolve()):
        raise ValueError("Pair asset is outside its bundle")
    rows = [row for row in pair["assets"] if row["path"] == relative]
    if (
        len(rows) != 1
        or rows[0]["bytes"] != asset.stat().st_size
        or rows[0]["sha256"] != sha256_file(asset)
    ):
        raise ValueError(f"Pair asset failed integrity checks: {role}")
    return asset


def screen(path, ffmpeg):
    import librosa

    pair = json.loads(path.read_text(encoding="utf-8-sig"))
    if pair.get("format") != "tabber-training-pair" or pair.get("schema_version") != 1:
        raise ValueError("Use a version 1 source pair manifest")
    audio_path = pair_asset(path, pair, "audio_original")
    midi_path = pair_asset(path, pair, "score_midi")
    midi = mido.MidiFile(midi_path)
    score = unit_chroma(score_features(midi))
    raw = subprocess.check_output(
        [
            str(ffmpeg),
            "-nostdin",
            "-v",
            "error",
            "-i",
            str(audio_path),
            "-map",
            "0:a:0",
            "-t",
            str(MAX_DURATION + 1),
            "-ac",
            "1",
            "-ar",
            str(RATE),
            "-f",
            "f32le",
            "pipe:1",
        ]
    )
    audio = np.frombuffer(raw, dtype="<f4")
    if not 0 < len(audio) <= MAX_DURATION * RATE or not np.isfinite(audio).all():
        raise ValueError("Use finite audio of up to 15 minutes")
    features = unit_chroma(librosa.feature.chroma_cqt(y=audio, sr=RATE, hop_length=HOP).T)
    return {
        "song_id": pair["song_id"],
        "source_pair_sha256": sha256_file(path),
        "score_seconds": round(midi.length, 3),
        "recording_seconds": round(len(audio) / RATE, 3),
        **scan_windows(score, features),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pairs", type=Path, nargs="+")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ffmpeg", type=Path)
    args = parser.parse_args()
    try:
        ffmpeg = find_ffmpeg(args.ffmpeg)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as stream:
            pairs, errors = [], []
            for path in args.pairs:
                try:
                    row = screen(path, ffmpeg)
                    pairs.append(row)
                    print(f"{row['song_id']}: {row['global_shift_seconds']:+.3f}s", flush=True)
                except (
                    OSError,
                    ValueError,
                    TypeError,
                    KeyError,
                    EOFError,
                    subprocess.CalledProcessError,
                ) as error:
                    errors.append({"pair": str(path), "error": str(error)})
                    print(f"{path}: {error}", flush=True)
            report = {
                "purpose": "Coarse pitch-class screen; all labels remain candidates",
                "hop_seconds": STEP,
                "search_seconds": 6,
                "pairs": pairs,
                "errors": errors,
            }
            json.dump(report, stream, indent=2)
            stream.write("\n")
    except (ImportError, OSError, ValueError) as error:
        parser.exit(1, f"Could not screen pairs: {error}\n")
    if errors:
        parser.exit(1, "Some pairs failed; see the report.\n")


if __name__ == "__main__":
    main()

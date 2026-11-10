"""Cache verified training and validation stems and frozen guitar-model outputs."""

import argparse
import json
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf
from evaluate_onset_excerpts import load_partition

from tabber.guitar_gaps import CHECKPOINT_SHA256, gaps_activations
from tabber.media import sha256_file
from tabber.separate import separate_guitar

STEM_PATH = Path("stems/htdemucs_6s/audio/guitar.wav")


def prepare_clip(audio, destination, identity):
    record_path = destination / "entry.json"
    if destination.exists():
        record = json.loads(record_path.read_text(encoding="utf-8"))
        if (
            any(record[key] != value for key, value in identity.items())
            or sha256_file(destination / STEM_PATH) != record["stem_sha256"]
            or sha256_file(destination / "activations.npz") != record["activations_sha256"]
        ):
            raise ValueError(f"Cached files do not match {destination.name}")
        return {
            **identity,
            "stem_sha256": record["stem_sha256"],
            "activations_sha256": record["activations_sha256"],
        }

    with tempfile.TemporaryDirectory(prefix=".stem-stage-", dir=destination.parent) as directory:
        stage = Path(directory) / "clip"
        stem = separate_guitar(audio, stage / "stems")
        if stem != stage.resolve() / STEM_PATH:
            raise ValueError("Unexpected guitar stem path")
        if abs(sf.info(stem).duration - identity["duration_seconds"]) > 0.001:
            raise ValueError("Separated guitar has a different duration from its input")
        activations, duration = gaps_activations(stem)
        cache = stage / "activations.npz"
        np.savez_compressed(cache, duration_seconds=duration, **activations)
        record = {
            **identity,
            "stem_sha256": sha256_file(stem),
            "activations_sha256": sha256_file(cache),
        }
        (stage / "entry.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        stage.rename(destination)
    return record


def prepare(manifest, output):
    partitions = {split: load_partition(manifest, split) for split in ("train", "validation")}
    manifest_hash = sha256_file(manifest)
    output.mkdir(parents=True, exist_ok=True)
    records = []
    for split, excerpts in partitions.items():
        for index, (row, audio, _) in enumerate(excerpts, 1):
            clip = f"{split}-{index:03d}"
            record = prepare_clip(
                audio,
                output / clip,
                {
                    "split": split,
                    "song_id": row["song_id"],
                    "audio_sha256": row["audio_sha256"],
                    "labels_sha256": row["labels_sha256"],
                    "checkpoint_sha256": CHECKPOINT_SHA256,
                    "duration_seconds": row["frames"] / row["sample_rate"],
                },
            )
            records.append({"clip": clip, **record})
            print(f"{clip}: {row['song_id']} verified", flush=True)
    payload = {
        "format": "tabber-guitar-training-cache",
        "schema_version": 1,
        "manifest_sha256": manifest_hash,
        "checkpoint_sha256": CHECKPOINT_SHA256,
        "clips": records,
    }
    with tempfile.TemporaryDirectory(prefix=".manifest-stage-", dir=output) as directory:
        path = Path(directory) / "cache.json"
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        path.replace(output / "cache.json")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        prepare(args.manifest, args.output.resolve())
    except (OSError, KeyError, ValueError, RuntimeError) as error:
        parser.exit(1, f"Could not prepare training cache: {error}\n")


if __name__ == "__main__":
    main()

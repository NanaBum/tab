"""Check whether a detected pitch is stronger in the guitar stem than its residual."""

import argparse
import json
from dataclasses import asdict
from pathlib import Path

import numpy as np
import soundfile as sf
from compare_detector_fusion import read_results
from evaluate_onset_excerpts import load_partition, reuse_inputs

from tabber.evaluation import score_notes
from tabber.events import save_events
from tabber.media import sha256_file


def contrast(notes, stem, residual):
    guitar, rate = sf.read(stem, always_2d=True)
    backing, backing_rate = sf.read(residual, always_2d=True)
    if rate != backing_rate or guitar.shape != backing.shape:
        raise ValueError("Stem and residual must have identical audio shapes and sample rates")
    if not np.isfinite(guitar).all() or not np.isfinite(backing).all():
        raise ValueError("Stem and residual must contain finite samples")
    values = []
    for note in notes:
        lo = round((note.start + 0.02) * rate)
        hi = min(len(guitar), round(min(note.end, note.start + 0.12) * rate))
        if hi - lo < 0.04 * rate:
            values.append(None)
            continue
        fundamental = 440 * 2 ** ((note.pitch - 69) / 12)
        harmonics = np.arange(1, 5)
        harmonics = harmonics[fundamental * harmonics < rate / 2]
        if not len(harmonics):
            values.append(None)
            continue
        time = np.arange(hi - lo) / rate
        basis = np.exp(-2j * np.pi * fundamental * harmonics[:, None] * time)
        basis *= np.hanning(len(time)) / len(time)
        energies = [
            float(np.sum(np.mean(np.abs(basis @ samples[lo:hi]) ** 2, axis=1) / harmonics))
            for samples in (guitar, backing)
        ]
        values.append(
            None
            if max(energies) <= 1e-12
            else float(10 * np.log10(max(energies[0], 1e-12) / max(energies[1], 1e-12)))
        )
    return values


def check(manifest, split, stems_from, predictions, output):
    excerpts = load_partition(manifest, split)
    digest = sha256_file(manifest)
    stems = reuse_inputs(stems_from, digest, split, excerpts)
    results = read_results(predictions, digest, split, excerpts)
    output.mkdir(parents=True, exist_ok=False)
    records = []
    for index, ((row, _, reference), stem, (backend, result, notes)) in enumerate(
        zip(excerpts, stems, results, strict=True), 1
    ):
        if result["detector_input_sha256"] != sha256_file(stem):
            raise ValueError("Detector events did not use the supplied guitar stem")
        residual = stem.with_name("no_guitar.wav")
        values = contrast(notes, stem, residual)
        accepted = [n for n, db in zip(notes, values, strict=True) if db is None or db >= 0]
        metadata = {
            "song_id": row["song_id"],
            "backend": backend,
            "source_events_sha256": result["prediction_sha256"],
            "stem_sha256": result["detector_input_sha256"],
            "residual_sha256": sha256_file(residual),
            "labels_sha256": row["labels_sha256"],
            "contrast_db_by_source_event": values,
            "scores": {
                name: asdict(score_notes(reference, events, onset_tolerance=0.075))
                for name, events in (("all", notes), ("accepted", accepted))
            },
        }
        path = output / f"excerpt-{index:03d}-accepted.json"
        save_events(accepted, path, metadata)
        records.append({**metadata, "accepted_events_sha256": sha256_file(path)})
        print(f"{row['song_id']}: kept {len(accepted)}/{len(notes)}", flush=True)
    report = {
        "manifest_sha256": digest,
        "split": split,
        "policy": "Keep events when the guitar harmonic energy is at least the residual energy or evidence is unavailable. Uses first four harmonics and the note window from 20 to 120 ms after onset, clipped to release.",
        "limits": "Demucs residual is an estimate. Different stem gains, pitched accompaniment and imperfect score timing can affect the comparison. No model fitting.",
        "excerpts": records,
    }
    with (output / "report.json").open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--split", choices=("validation", "test"), required=True)
    parser.add_argument("--stems-from", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        check(args.manifest, args.split, args.stems_from, args.predictions, args.output)
    except (OSError, KeyError, TypeError, ValueError, RuntimeError) as error:
        parser.exit(1, f"Could not compare note contrast: {error}\n")


if __name__ == "__main__":
    main()

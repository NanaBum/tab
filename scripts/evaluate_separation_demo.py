"""Reproduce one controlled mixture check, not a real full-band benchmark."""

import argparse
import io
import json
import zipfile
from dataclasses import asdict
from pathlib import Path

import numpy as np
import soundfile as sf
from make_mixture_demo import make_mixture

from tabber.evaluation import guitarset_notes, score_notes
from tabber.separate import separate_guitar
from tabber.transcribe import transcribe

TRACK = "03_BN1-129-Eb_solo"


def si_sdr(reference, estimate):
    if estimate.ndim > 1:
        estimate = estimate.mean(axis=1)
    count = min(len(reference), len(estimate))
    reference = reference[:count] - reference[:count].mean()
    estimate = estimate[:count] - estimate[:count].mean()
    target = reference * (np.dot(estimate, reference) / max(np.dot(reference, reference), 1e-12))
    return float(
        10 * np.log10((np.sum(target**2) + 1e-12) / (np.sum((estimate - target) ** 2) + 1e-12))
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("data/guitarset"))
    parser.add_argument("--output", type=Path, default=Path("runs/separation-evaluation"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    with (
        zipfile.ZipFile(args.data / "annotation.zip") as annotations,
        zipfile.ZipFile(args.data / "audio_mono-mic.zip") as archive,
    ):
        reference = [
            n.note for n in guitarset_notes(json.loads(annotations.read(TRACK + ".jams")), end=10)
        ]
        audio, rate = sf.read(io.BytesIO(archive.read(TRACK + "_mic.wav")))
    source = args.output / "source-excerpt.wav"
    sf.write(source, audio[: 10 * rate], rate)
    make_mixture(source, args.output)
    separated = separate_guitar((args.output / "mixture.wav").resolve(), args.output / "stems")
    clean, rate = sf.read(args.output / "guitar.wav")
    report = {
        "purpose": "Single controlled mixture smoke test, not a real full-band benchmark",
        "guitar_source": f"First 10s of GuitarSet {TRACK}; CC BY 4.0, Xi et al. ISMIR 2018",
        "mixture": "Generated bass and drums, 0.5s pulse, fixed random seed 0; no other recordings",
        "separator": "Demucs 4.0.1 htdemucs_6s, CPU, shifts=0, segment=7s",
        "pitch_detector": "Basic Pitch 0.4.0, event confidence >= 0.5",
        "conditions": {},
    }
    for name, path in (
        ("clean", args.output / "guitar.wav"),
        ("mixture", args.output / "mixture.wav"),
        ("separated", separated),
    ):
        audio, sample_rate = sf.read(path)
        if sample_rate != rate:
            raise ValueError("Sample rates must agree for this comparison")
        prediction = transcribe(path, "basic-pitch")
        report["conditions"][name] = {
            "onsets": asdict(score_notes(reference, prediction)),
            "onsets_offsets": asdict(score_notes(reference, prediction, offsets=True)),
            "si_sdr_db": None if name == "clean" else si_sdr(clean, audio),
        }
    (args.output / "evaluation.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

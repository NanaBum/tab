"""Measure GAPS on annotated electric guitar at fixed accompaniment levels."""

import argparse
import json
from dataclasses import asdict, replace
from pathlib import Path

import numpy as np
import soundfile as sf
from evaluate_separation_demo import si_sdr
from make_mixture_demo import generated_backing

from tabber.evaluation import idmt_recording, score_notes
from tabber.events import save_events
from tabber.guitar_gaps import CHECKPOINT_SHA256, decode_gaps, gaps_activations
from tabber.media import sha256_file
from tabber.separate import separate_guitar

TRACKS = (("dataset2", "AR_Lick1_KN"), ("dataset3", "pathetique_poly"))
GUITAR_TO_BACKING_DB = (6, 0, -6)


def rms(samples):
    return float(np.sqrt(np.mean(samples**2)))


def make_inputs(guitar, rate):
    bass, drums = generated_backing(len(guitar), rate)
    backing = bass + drums
    matched_backing = backing * (rms(guitar) / rms(backing))
    mixes = {
        f"mix-{ratio:+d}db": guitar + matched_backing * 10 ** (-ratio / 20)
        for ratio in GUITAR_TO_BACKING_DB
    }
    inputs = {"clean": guitar, "backing-only": matched_backing, **mixes}
    peak = max(float(np.max(np.abs(samples))) for samples in inputs.values())
    common_gain = min(1.0, 0.9 / peak)
    return {name: samples * common_gain for name, samples in inputs.items()}, common_gain


def evaluate_track(data, group, name, destination):
    wav = data / group / "audio" / f"{name}.wav"
    annotation = data / group / "annotation" / f"{name}.xml"
    notes = idmt_recording(annotation.read_text(encoding="utf-8-sig")).notes
    audio, rate = sf.read(wav, frames=12 * sf.info(wav).samplerate, always_2d=True)
    guitar = audio.mean(axis=1)
    if not len(guitar) or not np.isfinite(guitar).all() or rms(guitar) == 0:
        raise ValueError("Expected audible, finite electric-guitar audio")
    duration = len(guitar) / rate
    reference = [replace(n, end=min(n.end, duration)) for n in notes if n.start < duration]
    if not reference:
        raise ValueError("Expected annotated guitar attacks in the excerpt")
    inputs, common_gain = make_inputs(guitar, rate)
    destination.mkdir()
    paths = {}
    for condition, samples in inputs.items():
        path = destination / f"{condition}.wav"
        sf.write(path, samples, rate, subtype="FLOAT")
        paths[condition] = path
    for mix in ("mix-+0db", "mix--6db"):
        paths[f"separated-{mix}"] = separate_guitar(paths[mix], destination / mix)
    results = {}
    for condition, path in paths.items():
        estimate, estimate_rate = sf.read(path)
        if estimate_rate != rate or len(estimate) != len(guitar):
            raise ValueError("Expected identical sample rates and lengths across conditions")
        output, length = gaps_activations(path)
        detected = decode_gaps(output, length)
        events = destination / f"{condition}.json"
        save_events(detected, events, {"condition": condition, "backend": "guitar-gaps"})
        results[condition] = {
            "input_sha256": sha256_file(path),
            "events_sha256": sha256_file(events),
            "maximum_onset": float(output["reg_onset_output"].max()),
            "si_sdr_db": si_sdr(inputs["clean"], estimate) if "mix-" in condition else None,
            "onsets": asdict(
                score_notes([] if condition == "backing-only" else reference, detected)
            ),
        }
        print(f"{name} {condition}: {len(detected)} detections", flush=True)
    return {
        "group": group,
        "track": name,
        "source_sha256": sha256_file(wav),
        "annotation_sha256": sha256_file(annotation),
        "seconds": duration,
        "common_gain": common_gain,
        "conditions": results,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("data/idmt"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        args.output.mkdir(parents=True, exist_ok=False)
        report = {
            "checkpoint_sha256": CHECKPOINT_SHA256,
            "guitar_to_backing_rms_db": GUITAR_TO_BACKING_DB,
            "onset_tolerance_seconds": 0.05,
            "limits": "Two IDMT electric guitar excerpts with generated bass and drums. No timing fitting or model training. Published checkpoint training overlap is unresolved.",
            "tracks": [
                evaluate_track(args.data, group, name, args.output / name) for group, name in TRACKS
            ],
        }
        with (args.output / "report.json").open("x", encoding="utf-8") as stream:
            json.dump(report, stream, indent=2)
            stream.write("\n")
    except (OSError, ValueError, RuntimeError) as error:
        parser.exit(1, f"Could not evaluate controlled mixes: {error}\n")


if __name__ == "__main__":
    main()

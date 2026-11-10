"""Run Basic Pitch on the exact waveforms in the controlled GAPS benchmark."""

import argparse
import json
from dataclasses import asdict, replace
from pathlib import Path

from evaluate_guitar_mix_levels import GUITAR_TO_BACKING_DB, TRACKS
from evaluate_onset_excerpts import verified_asset

from tabber.evaluation import idmt_recording, score_notes
from tabber.events import load_events, save_events
from tabber.fusion import complementary_notes
from tabber.media import sha256_file
from tabber.transcribe import transcribe


def compare(data, gaps_run, output):
    saved_report = gaps_run / "report.json"
    baseline = json.loads(saved_report.read_text(encoding="utf-8"))
    if [(row["group"], row["track"]) for row in baseline["tracks"]] != list(TRACKS):
        raise ValueError("Use results from the fixed controlled-mixture benchmark")
    mix_names = tuple(f"mix-{ratio:+d}db" for ratio in GUITAR_TO_BACKING_DB)
    source_paths = {name: f"{name}.wav" for name in ("clean", "backing-only", *mix_names)}
    source_paths.update(
        {f"separated-{name}": f"{name}/htdemucs_6s/{name}/guitar.wav" for name in mix_names[1:]}
    )
    tolerance = baseline["onset_tolerance_seconds"]
    if tolerance != 0.05 or baseline["guitar_to_backing_rms_db"] != list(GUITAR_TO_BACKING_DB):
        raise ValueError("The benchmark ratios or onset tolerance differ")
    output.mkdir(parents=True, exist_ok=False)
    rows = []
    for track in baseline["tracks"]:
        group, name = track["group"], track["track"]
        annotation = verified_asset(
            data, f"{group}/annotation/{name}.xml", track["annotation_sha256"]
        )
        verified_asset(data, f"{group}/audio/{name}.wav", track["source_sha256"])
        duration = track["seconds"]
        reference = [
            replace(n, end=min(n.end, duration))
            for n in idmt_recording(annotation.read_text(encoding="utf-8-sig")).notes
            if n.start < duration
        ]
        if set(source_paths) != set(track["conditions"]):
            raise ValueError("The saved track does not contain every benchmark condition")
        (output / name).mkdir()
        results = {}
        for condition, relative in source_paths.items():
            existing = track["conditions"][condition]
            path = verified_asset(gaps_run, f"{name}/{relative}", existing["input_sha256"])
            events = verified_asset(gaps_run, f"{name}/{condition}.json", existing["events_sha256"])
            gaps = load_events(events)
            target = [] if condition == "backing-only" else reference
            gaps_score = asdict(score_notes(target, gaps, onset_tolerance=tolerance))
            if gaps_score != existing["onsets"]:
                raise ValueError("Saved GAPS events do not reproduce the original score")
            basic = transcribe(path, "basic-pitch")
            prediction = output / name / f"{condition}.json"
            save_events(basic, prediction, {"backend": "basic-pitch", "condition": condition})
            combined = complementary_notes(gaps, basic, tolerance=tolerance)
            scores = {"gaps": gaps_score}
            for key, notes in (
                ("basic_pitch", basic),
                ("agreement", [n for n, a, b in combined if a is not None and b is not None]),
                ("union", [n for n, _, _ in combined]),
            ):
                scores[key] = asdict(score_notes(target, notes, onset_tolerance=tolerance))
            results[condition] = {
                "input_sha256": existing["input_sha256"],
                "basic_pitch_events_sha256": sha256_file(prediction),
                "scores": scores,
            }
            print(f"{name} {condition}: {len(basic)} Basic Pitch detections", flush=True)
        rows.append({"track": name, "conditions": results})
    report = {
        "gaps_report_sha256": sha256_file(saved_report),
        "onset_tolerance_seconds": tolerance,
        "limits": "Two electric-guitar recordings with synthetic backing. Agreement retains GAPS timing. Both detectors are frozen.",
        "tracks": rows,
    }
    with (output / "report.json").open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("gaps_run", type=Path)
    parser.add_argument("--data", type=Path, default=Path("data/idmt"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        compare(args.data, args.gaps_run, args.output)
    except (OSError, KeyError, TypeError, ValueError, RuntimeError) as error:
        parser.exit(1, f"Could not compare controlled mix detectors: {error}\n")


if __name__ == "__main__":
    main()

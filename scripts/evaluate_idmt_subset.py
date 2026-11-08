"""Evaluate a fixed IDMT electric-guitar selection locally, without training."""

import argparse
import hashlib
import json
import time
from dataclasses import asdict
from pathlib import Path

from tabber.evaluation import idmt_recording, match_notes, score_notes
from tabber.events import save_events
from tabber.export import write_outputs
from tabber.fretting import assign_polyphonic_frets
from tabber.guitar_gaps import CHECKPOINT_SHA256
from tabber.transcribe import transcribe


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection", choices=("pieces", "licks", "muted"), default="pieces")
    parser.add_argument("--data", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--backend", choices=("baseline", "basic-pitch", "guitar-gaps"), default="guitar-gaps"
    )
    args = parser.parse_args()
    names = {
        "pieces": (
            "nocturneNr2",
            "pathetique_mono",
            "pathetique_poly",
            "promenade_mono",
            "quintfall",
        ),
        "licks": ("AR_Lick1_KN", "AR_Lick6_KN", "AR_Lick12_KN"),
        "muted": ("AR_Lick1_MN", "AR_Lick6_MN", "AR_Lick12_MN"),
    }[args.selection]
    args.data = (
        args.data
        or Path("data/idmt")
        / {"pieces": "dataset3", "licks": "dataset2", "muted": "muted"}[args.selection]
    )
    args.output = args.output or Path("runs") / f"idmt-{args.selection}-{args.backend}"
    report = {
        "purpose": "Fixed electric-guitar development check; checkpoint training overlap unresolved",
        "selection": args.selection,
        "source": "https://zenodo.org/records/7544110",
        "backend": args.backend,
        "settings": {
            "min_confidence": None if args.backend == "guitar-gaps" else 0.5,
            "onset_threshold": 0.3 if args.backend == "guitar-gaps" else None,
            "checkpoint_sha256": CHECKPOINT_SHA256 if args.backend == "guitar-gaps" else None,
        },
        "metrics": "Exact pitch, 50 ms attack tolerance; optional release tolerance max(50 ms, 20% reference duration)",
        "export_settings": "Provisional 120 BPM, 1/32 grid; format validation only, not reference rhythm accuracy",
        "tracks": [],
    }
    args.output.mkdir(parents=True, exist_ok=True)
    for name in names:
        source = args.data / "audio" / f"{name}.wav"
        annotation = args.data / "annotation" / f"{name}.xml"
        reference = idmt_recording(annotation.read_text(encoding="utf-8-sig"))
        row = {
            "track": name,
            "audio_sha256": digest(source),
            "annotation_sha256": digest(annotation),
            "instrument": reference.metadata.get("instrumentModel"),
            "reference_notes": len(reference.notes),
            "inconsistent_reference_positions": reference.inconsistent_position_indices,
            "position_audit": "Inconsistent positions excluded only from position scoring; supplied pitches unchanged",
        }
        print(f"Evaluating {name}: {len(reference.notes)} reference events", flush=True)
        folder = args.output / name
        start = time.perf_counter()
        try:
            predicted = transcribe(source, args.backend)
            row["runtime_seconds"] = round(time.perf_counter() - start, 3)
            save_events(
                predicted,
                folder / "detected-notes.json",
                {"backend": args.backend, "input": str(source), "settings": report["settings"]},
            )
            row["onsets"] = asdict(score_notes(reference.notes, predicted))
            row["onsets_offsets"] = asdict(score_notes(reference.notes, predicted, offsets=True))
            matched = match_notes(reference.notes, predicted)
            matched_reference = {i for i, _ in matched}
            matched_predictions = {j for _, j in matched}
            row["unmatched_reference"] = [
                {
                    "index": i,
                    "note": asdict(note),
                    "consistent_position": reference.positions[i] is not None,
                }
                for i, note in enumerate(reference.notes)
                if i not in matched_reference
            ]
            row["unmatched_predictions"] = [
                {"index": j, "note": asdict(note)}
                for j, note in enumerate(predicted)
                if j not in matched_predictions
            ]
            assigned = assign_polyphonic_frets(predicted)
            positions = {id(note.note): (note.string, note.fret) for note in assigned}
            eligible = [(i, j) for i, j in matched if reference.positions[i] is not None]
            correct = sum(
                reference.positions[i] == positions[id(predicted[j])] for i, j in eligible
            )
            row["conditional_fingering"] = {
                "correct": correct,
                "eligible_pitch_matches": len(eligible),
                "all_pitch_matches": len(matched),
            }
            row["score_timing"] = write_outputs(assigned, folder, 120, 32)
            row["export_status"] = (
                f"Exported all {len(assigned)} detections; GP5 reopened and verified"
            )
        except (ValueError, OSError, RuntimeError) as error:
            row["error"] = str(error)
            print(f"Explicit failure for {name}: {error}", flush=True)
        report["tracks"].append(row)
        (args.output / "report.json").write_text(
            json.dumps(report, indent=2) + "\n", encoding="utf-8"
        )
    for metric in ("onsets", "onsets_offsets"):
        rows = [row[metric] for row in report["tracks"] if metric in row]
        refs = sum(row["reference_notes"] for row in rows)
        predictions = sum(row["predicted_notes"] for row in rows)
        matches = sum(row["matched_notes"] for row in rows)
        report[metric + "_micro"] = {
            "reference_notes": refs,
            "predicted_notes": predictions,
            "matched_notes": matches,
            "evaluated_recordings": len(rows),
            "f1": 2 * matches / (refs + predictions) if refs + predictions else 0,
        }
    (args.output / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {key: value for key, value in report.items() if key.endswith("_micro")}, indent=2
        )
    )


if __name__ == "__main__":
    main()

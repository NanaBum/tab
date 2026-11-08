"""Measure saved GP5 timing against source detections and GuitarSet references.

Uses cached predictions, standard fingering, and nominal annotated BPM. No ML,
parameter tuning, audio download, beat alignment or note correction is performed.
"""

import argparse
import io
import json
import zipfile
from dataclasses import asdict
from pathlib import Path

import numpy as np

from tabber.evaluation import guitarset_notes, score_notes
from tabber.fretting import assign_polyphonic_frets
from tabber.gp5 import build_song, read_gp5, score_events, verify_export, write_gp5
from tabber.models import STANDARD_TUNING, Note
from tabber.rhythm import quantize


def decoded_notes(song):
    """Convert actual score ticks to seconds using the saved integer tempo."""
    tick_seconds = 60 / (song.tempo * 960)
    return [
        Note(
            (start - 960) * tick_seconds,
            (end - 960) * tick_seconds,
            STANDARD_TUNING[string - 1] + fret,
        )
        for start, end, string, fret in score_events(song)
    ]


def micro(scores):
    reference = sum(s["reference_notes"] for s in scores)
    predicted = sum(s["predicted_notes"] for s in scores)
    matched = sum(s["matched_notes"] for s in scores)
    return {
        "reference_notes": reference,
        "predicted_notes": predicted,
        "matched_notes": matched,
        "f1": 2 * matched / (reference + predicted) if reference + predicted else 0,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("predictions", type=Path)
    parser.add_argument("--data", type=Path, default=Path("data/guitarset"))
    parser.add_argument("--output", type=Path, default=Path("runs/score-timing-audit.json"))
    args = parser.parse_args()
    data = json.loads(args.predictions.read_text(encoding="utf-8"))
    report = {
        "purpose": "Saved-score timing development audit; not held-out transcription accuracy",
        "policy": "Fixed detections and nominal annotated BPM rounded to integer; grid origin zero; no beat alignment",
        "seconds": data["seconds"],
        "grids": {},
        "fingering_failures": [],
    }
    rows = {str(grid): [] for grid in (16, 32, 64)}
    shifts = {str(grid): {"onset": [], "end": []} for grid in (16, 32, 64)}
    with zipfile.ZipFile(args.data / "annotation.zip") as annotations:
        for index, row in enumerate(data["tracks"]):
            if index % 30 == 0:
                print(f"Score timing {index}/{len(data['tracks'])}", flush=True)
            predicted = [Note(**n) for n in row["predictions"]]
            try:
                assigned = assign_polyphonic_frets(predicted)
            except ValueError as error:
                report["fingering_failures"].append({"track": row["track"], "error": str(error)})
                continue
            jams = json.loads(annotations.read(row["track"] + ".jams"))
            reference = [n.note for n in guitarset_notes(jams, end=data["seconds"])]
            bpm = float(
                next(
                    a["data"][0]["value"] for a in jams["annotations"] if a["namespace"] == "tempo"
                )
            )
            for grid in (16, 32, 64):
                result = {"track": row["track"]}
                try:
                    song = build_song(assigned, bpm, grid)
                    stream = io.BytesIO()
                    write_gp5(song, stream)
                    stream.seek(0)
                    saved = read_gp5(stream)
                    verify_export(saved, assigned, bpm, grid)
                except ValueError as error:
                    result["error"] = str(error)
                    rows[str(grid)].append(result)
                    continue
                decoded = decoded_notes(saved)
                for name, notes in (("raw", predicted), ("score", decoded)):
                    result[name] = {
                        "onsets": asdict(score_notes(reference, notes)),
                        "onsets_offsets": asdict(score_notes(reference, notes, offsets=True)),
                    }
                result["score_beats"] = sum(
                    len(m.voices[0].beats) for m in saved.tracks[0].measures
                )
                for note in predicted:
                    start = quantize(note.start, saved.tempo, grid // 4)
                    end = max(start + 1, quantize(note.end, saved.tempo, grid // 4))
                    cell = 240 / (saved.tempo * grid)
                    shifts[str(grid)]["onset"].append(abs(start * cell - note.start))
                    shifts[str(grid)]["end"].append(abs(end * cell - note.end))
                rows[str(grid)].append(result)
    for grid, tracks in rows.items():
        successful = [r for r in tracks if "error" not in r]
        summary = {
            "successful_clips": len(successful),
            "export_failures": len(tracks) - len(successful),
            "score_beats": sum(r["score_beats"] for r in successful),
            "cohort": "Raw and score metrics use exactly the same successful clips for this grid",
        }
        for name in ("raw", "score"):
            summary[name] = {
                metric: micro([r[name][metric] for r in successful])
                for metric in ("onsets", "onsets_offsets")
            }
        summary["absolute_shift_from_detections_ms"] = {
            kind: {
                "median": float(np.median(values) * 1000),
                "p95": float(np.percentile(values, 95) * 1000),
                "max": float(max(values) * 1000),
            }
            if values
            else {}
            for kind, values in shifts[grid].items()
        }
        report["grids"][grid] = {"summary": summary, "tracks": tracks}
    common = set.intersection(
        *[{r["track"] for r in tracks if "error" not in r} for tracks in rows.values()]
    )
    report["common_successful_cohort"] = {
        "clips": len(common),
        "grids": {
            grid: {
                **{
                    name: {
                        metric: micro([r[name][metric] for r in tracks if r["track"] in common])
                        for metric in ("onsets", "onsets_offsets")
                    }
                    for name in ("raw", "score")
                },
                "score_beats": sum(r["score_beats"] for r in tracks if r["track"] in common),
            }
            for grid, tracks in rows.items()
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({g: r["summary"] for g, r in report["grids"].items()}, indent=2))


if __name__ == "__main__":
    main()

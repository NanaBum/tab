"""Evaluate downloaded GuitarSet archives locally; never downloads or trains."""

import argparse
import io
import json
import tempfile
import time
import zipfile
from dataclasses import asdict
from pathlib import Path

import soundfile as sf

from tabber.evaluation import guitarset_notes, match_notes, score_notes
from tabber.export import write_outputs
from tabber.fretting import assign_polyphonic_frets
from tabber.transcribe import transcribe


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("data/guitarset"))
    parser.add_argument("--output", type=Path, default=Path("runs/evaluation.json"))
    parser.add_argument("--backend", choices=("baseline", "basic-pitch"), default="baseline")
    parser.add_argument("--mode", choices=("solo", "comp", "all"), default="solo")
    parser.add_argument("--limit", type=int, default=6)
    parser.add_argument("--seconds", type=float, default=10)
    parser.add_argument("--min-confidence", type=float, default=0.5)
    parser.add_argument("--export-tabs", action="store_true")
    parser.add_argument("--grid", type=int, choices=(16, 32, 64), default=16)
    args = parser.parse_args()
    if args.limit < 1 or not 0 < args.seconds <= 600:
        parser.error("Use a positive limit and duration up to 600 seconds")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    results = {
        "backend": args.backend,
        "mode": args.mode,
        "seconds": args.seconds,
        "min_confidence": args.min_confidence,
        "dataset": "GuitarSet v1.1.0 (Zenodo 3371780)",
        "purpose": "development smoke test, not a held-out benchmark",
        "metrics": "exact pitch; 50ms onset; offsets within max(50ms,20% duration)",
        "tracks": [],
    }
    with (
        zipfile.ZipFile(args.data / "annotation.zip") as annotations,
        zipfile.ZipFile(args.data / "audio_mono-mic.zip") as audio,
    ):
        names = sorted(
            n
            for n in annotations.namelist()
            if n.endswith(".jams") and (args.mode == "all" or n.endswith(f"_{args.mode}.jams"))
        )
        # Round-robin performers rather than choosing only performer 00.
        groups = {n[:2]: [] for n in names}
        for name in names:
            groups[name[:2]].append(name)
        names = [
            group[index]
            for index in range(max(map(len, groups.values()), default=0))
            for group in groups.values()
            if index < len(group)
        ][: args.limit]
        audio_names = {Path(n).name: n for n in audio.namelist()}
        for name in names:
            track_id = Path(name).stem
            print(f"Evaluating {track_id} ({args.backend})", flush=True)
            jams = json.loads(annotations.read(name))
            reference = guitarset_notes(jams, end=args.seconds)
            key = track_id + "_mic.wav"
            if key not in audio_names:
                raise ValueError(f"Missing audio archive member {key}")
            waveform, rate = sf.read(io.BytesIO(audio.read(audio_names[key])))
            waveform = waveform[: int(rate * args.seconds)]
            start = time.perf_counter()
            with tempfile.TemporaryDirectory(dir=args.output.parent) as directory:
                path = Path(directory) / "excerpt.wav"
                sf.write(path, waveform, rate, subtype="FLOAT")
                predicted = transcribe(path, args.backend, args.min_confidence)
            elapsed = time.perf_counter() - start
            refs = [n.note for n in reference]
            row = {
                "track": track_id,
                "runtime_seconds": round(elapsed, 3),
                "onsets": asdict(score_notes(refs, predicted)),
                "onsets_offsets": asdict(score_notes(refs, predicted, offsets=True)),
                "predictions": [asdict(n) for n in predicted],
            }
            try:
                assigned = assign_polyphonic_frets(predicted)
                row["fretting_status"] = f"assigned {len(assigned)} notes"
                positions = {id(n.note): n for n in assigned}
                matches = match_notes(refs, predicted)
                correct = sum(
                    (reference[i].string, reference[i].fret)
                    == (positions[id(predicted[j])].string, positions[id(predicted[j])].fret)
                    for i, j in matches
                )
                row["fingering_matches"] = {
                    "correct": correct,
                    "matched_onsets": len(matches),
                    "accuracy": correct / len(matches) if matches else 0,
                }
                if args.export_tabs:
                    tempos = [
                        a["data"][0]["value"]
                        for a in jams["annotations"]
                        if a["namespace"] == "tempo"
                    ]
                    tempo = float(tempos[0]) if tempos else 120.0
                    folder = args.output.parent / (args.output.stem + "-tabs") / track_id
                    try:
                        write_outputs(assigned, folder, tempo, grid=args.grid)
                        row["export_status"] = f"GP5/MIDI/JSON/text written on 1/{args.grid} grid"
                    except ValueError as error:
                        row["export_status"] = str(error)
            except ValueError as error:
                row["fretting_status"] = str(error)
            results["tracks"].append(row)
            args.output.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    if not results["tracks"]:
        raise ValueError("No matching annotated tracks were found")
    for metric in ("onsets", "onsets_offsets"):
        rows = [r[metric] for r in results["tracks"]]
        matched = sum(r["matched_notes"] for r in rows)
        refs = sum(r["reference_notes"] for r in rows)
        preds = sum(r["predicted_notes"] for r in rows)
        results[metric + "_micro"] = {
            "precision": matched / preds if preds else 0,
            "recall": matched / refs if refs else 0,
            "f1": 2 * matched / (refs + preds) if refs + preds else 0,
            "reference_notes": refs,
            "predicted_notes": preds,
            "matched_notes": matched,
        }
    args.output.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in results.items() if k.endswith("_micro")}, indent=2))


if __name__ == "__main__":
    main()

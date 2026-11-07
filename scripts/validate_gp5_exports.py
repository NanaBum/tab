"""Validate GP5 serialization from cached GuitarSet predictions without rerunning ML."""

import argparse
import io
import json
import zipfile
from pathlib import Path

from tabber.fretting import assign_polyphonic_frets
from tabber.gp5 import build_song, read_gp5, verify_export, write_gp5
from tabber.models import Note


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("predictions", type=Path)
    parser.add_argument("--data", type=Path, default=Path("data/guitarset"))
    parser.add_argument("--output", type=Path, default=Path("runs/gp5-validation.json"))
    args = parser.parse_args()
    data = json.loads(args.predictions.read_text(encoding="utf-8"))
    report = {
        "purpose": "Serialization correctness, not transcription accuracy",
        "passed": [],
        "fingering_failures": [],
        "export_failures": [],
        "mismatches": [],
    }
    with zipfile.ZipFile(args.data / "annotation.zip") as annotations:
        for index, row in enumerate(data["tracks"]):
            if index % 30 == 0:
                print(f"Round-trip check {index}/{len(data['tracks'])}", flush=True)
            try:
                notes = assign_polyphonic_frets([Note(**n) for n in row["predictions"]])
            except ValueError as error:
                report["fingering_failures"].append({"track": row["track"], "error": str(error)})
                continue
            jams = json.loads(annotations.read(row["track"] + ".jams"))
            bpm = float(
                next(
                    a["data"][0]["value"] for a in jams["annotations"] if a["namespace"] == "tempo"
                )
            )
            error_message = None
            for grid in (16, 32, 64):
                try:
                    song = build_song(notes, bpm, grid)
                    break
                except ValueError as error:
                    error_message = str(error)
            else:
                report["export_failures"].append({"track": row["track"], "error": error_message})
                continue
            stream = io.BytesIO()
            write_gp5(song, stream)
            stream.seek(0)
            try:
                verify_export(read_gp5(stream), notes, bpm, grid)
            except ValueError as error:
                report["mismatches"].append({"track": row["track"], "error": str(error)})
            else:
                report["passed"].append({"track": row["track"], "grid": grid, "notes": len(notes)})
    report["summary"] = {
        "attempted": len(data["tracks"]),
        **{
            name: len(report[name])
            for name in ("passed", "fingering_failures", "export_failures", "mismatches")
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], indent=2))


if __name__ == "__main__":
    main()

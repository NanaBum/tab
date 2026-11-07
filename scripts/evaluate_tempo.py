"""Compare local tempo estimates with GuitarSet's nominal tempo annotations."""

import argparse
import io
import json
import tempfile
import zipfile
from dataclasses import asdict
from pathlib import Path

import soundfile as sf

from tabber.tempo import estimate_tempo


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("data/guitarset"))
    parser.add_argument("--output", type=Path, default=Path("runs/tempo-evaluation.json"))
    parser.add_argument("--limit", type=int, default=360)
    parser.add_argument("--seconds", type=float, default=10)
    args = parser.parse_args()
    if args.limit < 1 or not 2 <= args.seconds <= 60:
        parser.error("Use a positive limit and 2-60 seconds of audio per excerpt")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "method": "librosa 0.11 beat_track, hop_length=256, default start_bpm=120",
        "seconds": args.seconds,
        "purpose": "Nominal tempo development check; not downbeat alignment",
        "source": "GuitarSet v1.1.0 microphone audio; CC BY 4.0, Xi et al., ISMIR 2018",
        "tracks": [],
    }
    with (
        zipfile.ZipFile(args.data / "annotation.zip") as annotations,
        zipfile.ZipFile(args.data / "audio_mono-mic.zip") as audio,
    ):
        names = sorted(n for n in annotations.namelist() if n.endswith(".jams"))[: args.limit]
        for index, name in enumerate(names):
            if index % 30 == 0:
                print(f"Tempo evaluation {index}/{len(names)}", flush=True)
            jams = json.loads(annotations.read(name))
            reference = float(
                next(
                    a["data"][0]["value"] for a in jams["annotations"] if a["namespace"] == "tempo"
                )
            )
            waveform, rate = sf.read(io.BytesIO(audio.read(Path(name).stem + "_mic.wav")))
            with tempfile.TemporaryDirectory(dir=args.output.parent) as directory:
                path = Path(directory) / "excerpt.wav"
                sf.write(path, waveform[: int(args.seconds * rate)], rate, subtype="FLOAT")
                try:
                    estimate = estimate_tempo(path)
                    row = {"track": Path(name).stem, "reference_bpm": reference, **asdict(estimate)}
                    row["within_5_percent"] = abs(estimate.bpm / reference - 1) <= 0.05
                    row["half_double_within_5_percent"] = (
                        min(abs(factor * estimate.bpm / reference - 1) for factor in (0.5, 1, 2))
                        <= 0.05
                    )
                except ValueError as error:
                    row = {
                        "track": Path(name).stem,
                        "reference_bpm": reference,
                        "error": str(error),
                        "within_5_percent": False,
                        "half_double_within_5_percent": False,
                    }
            report["tracks"].append(row)
    count = len(report["tracks"])
    report["summary"] = {
        "excerpts": count,
        "estimated": sum("bpm" in t for t in report["tracks"]),
        "within_5_percent": sum(t["within_5_percent"] for t in report["tracks"]),
        "half_double_within_5_percent": sum(
            t["half_double_within_5_percent"] for t in report["tracks"]
        ),
    }
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], indent=2))


if __name__ == "__main__":
    main()

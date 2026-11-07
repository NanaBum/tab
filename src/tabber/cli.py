import argparse
import subprocess
from pathlib import Path

from .export import write_outputs
from .fretting import assign_frets
from .rhythm import quantize
from .separate import separate_guitar
from .transcribe import transcribe


def main():
    parser = argparse.ArgumentParser(description="Experimental audio-to-guitar-tab converter")
    parser.add_argument("audio", type=Path)
    parser.add_argument("--output", type=Path, default=Path("runs/latest"))
    parser.add_argument("--bpm", type=float, default=120)
    parser.add_argument("--backend", choices=("baseline", "basic-pitch"), default="baseline")
    parser.add_argument(
        "--separate", action="store_true", help="Run optional Demucs guitar separation"
    )
    args = parser.parse_args()
    try:
        quantize(0, args.bpm)
        path = args.audio.resolve()
        if not path.is_file():
            raise ValueError(f"Audio file does not exist: {path}")
        if args.separate:
            path = separate_guitar(path, args.output / "stems")
        notes = assign_frets(transcribe(path, args.backend))
        if not notes:
            raise ValueError("No notes detected. Try a louder, clean single-note recording.")
        write_outputs(notes, args.output, args.bpm)
    except (ValueError, OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"Could not transcribe: {exc}\n")
    print(f"Wrote {len(notes)} notes to {args.output.resolve()}")

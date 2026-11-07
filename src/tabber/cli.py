import argparse
import subprocess
from pathlib import Path

from .export import write_outputs
from .fretting import assign_frets, assign_polyphonic_frets
from .rhythm import quantize
from .separate import separate_guitar
from .transcribe import transcribe


def main():
    parser = argparse.ArgumentParser(description="Experimental audio-to-guitar-tab converter")
    parser.add_argument("audio", type=Path)
    parser.add_argument("--output", type=Path, default=Path("runs/latest"))
    parser.add_argument("--bpm", type=float, default=120)
    parser.add_argument(
        "--grid",
        type=int,
        choices=(16, 32, 64),
        default=16,
        help="Score divisions per whole note; finer grids preserve faster notes",
    )
    parser.add_argument("--backend", choices=("baseline", "basic-pitch"), default="baseline")
    parser.add_argument(
        "--fretting",
        choices=("melodic", "polyphonic"),
        default="polyphonic",
        help="Polyphonic search preserves overlapping notes (default)",
    )
    parser.add_argument(
        "--min-confidence",
        type=float,
        default=0.5,
        help="Discard detections below this confidence (0-1, default: 0.5)",
    )
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
        detected = transcribe(path, args.backend, args.min_confidence)
        assign = assign_frets if args.fretting == "melodic" else assign_polyphonic_frets
        notes = assign(detected)
        if not notes:
            raise ValueError("No notes detected. Try a louder, clean single-note recording.")
        write_outputs(notes, args.output, args.bpm, args.grid)
    except (ValueError, OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"Could not transcribe: {exc}\n")
    print(f"Wrote {len(notes)} notes to {args.output.resolve()}")

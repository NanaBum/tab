import argparse
import subprocess
from datetime import datetime
from pathlib import Path

from .export import write_outputs
from .fretting import assign_frets, assign_polyphonic_frets
from .rhythm import quantize
from .separate import separate_guitar
from .transcribe import transcribe


def main():
    parser = argparse.ArgumentParser(description="Experimental audio-to-guitar-tab converter")
    parser.add_argument("audio", type=Path, nargs="?")
    parser.add_argument("--events", type=Path, help="Rebuild a tab from saved detected-notes.json")
    parser.add_argument(
        "--string-model",
        type=Path,
        help="Experimental local string-timbre NPZ model (audio input, polyphonic mode)",
    )
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
    if (args.audio is None) == (args.events is None):
        parser.error("Provide either an audio file or --events, not both")
    if args.events and args.separate:
        parser.error("--separate needs audio input")
    if args.string_model and (args.events or args.fretting != "polyphonic"):
        parser.error("--string-model needs audio input and polyphonic fretting")
    try:
        quantize(0, args.bpm)
        path = (args.audio or args.events).resolve()
        if not path.is_file():
            raise ValueError(f"Input file does not exist: {path}")
        if args.separate:
            path = separate_guitar(path, args.output / "stems")
        detected = (
            load_events(path)
            if args.events
            else transcribe(path, args.backend, args.min_confidence)
        )
        metadata = {
            "input": str(path),
            "backend": "events" if args.events else args.backend,
            "min_confidence": None if args.events else args.min_confidence,
            "timing": "seconds, original detected timing before score quantization",
            "experimental_string_model": str(args.string_model) if args.string_model else None,
        }
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        diagnostic = args.output / "diagnostics" / f"detected-{stamp}.json"
        save_events(detected, diagnostic, metadata)
        print(f"Detected note events saved to {diagnostic.resolve()}", flush=True)
        assign = assign_frets if args.fretting == "melodic" else assign_polyphonic_frets
        if args.string_model:
            from .string_model import string_priors

            priors = string_priors(path, detected, args.string_model)
            notes = assign(detected, string_priors=priors)
        else:
            notes = assign(detected)
        if not notes:
            raise ValueError("No notes detected. Try a louder, clean single-note recording.")
        write_outputs(notes, args.output, args.bpm, args.grid)
        save_events(detected, args.output / "detected-notes.json", metadata)
    except (ValueError, OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"Could not transcribe: {exc}\n")
    print(f"Wrote {len(notes)} notes to {args.output.resolve()}")


from .events import load_events, save_events

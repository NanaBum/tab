import argparse
import subprocess
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from .export import write_outputs
from .fretting import assign_frets, assign_polyphonic_frets
from .rhythm import quantize
from .separate import separate_guitar
from .tempo import estimate_tempo, parse_bpm
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
    parser.add_argument(
        "--bpm",
        type=parse_bpm,
        default=120.0,
        help="Quarter-note BPM, or auto for a local estimate (review half/double time)",
    )
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
    if args.events and args.bpm == "auto":
        parser.error("--bpm auto needs audio input; supply BPM when rebuilding saved events")
    if args.string_model and (args.events or args.fretting != "polyphonic"):
        parser.error("--string-model needs audio input and polyphonic fretting")
    try:
        path = (args.audio or args.events).resolve()
        if not path.is_file():
            raise ValueError(f"Input file does not exist: {path}")
        tempo = estimate_tempo(path) if args.bpm == "auto" else None
        bpm = tempo.bpm if tempo else args.bpm
        quantize(0, bpm)
        if tempo:
            print(
                f"Estimated tempo: {bpm:.1f} BPM (provisional; review rhythmic grouping)",
                flush=True,
            )
        if args.separate:
            path = separate_guitar(path, args.output / "stems")
        detected = (
            load_events(path)
            if args.events
            else transcribe(path, args.backend, args.min_confidence)
        )
        metadata = {
            "input": str(path),
            "original_input": str((args.audio or args.events).resolve()),
            "separated": args.separate,
            "tempo_source": "estimated" if tempo else "supplied",
            "tempo_estimate": asdict(tempo) if tempo else None,
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
        timing = write_outputs(notes, args.output, bpm, args.grid)
        save_events(detected, args.output / "detected-notes.json", metadata)
    except (ValueError, OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"Could not transcribe: {exc}\n")
    print(f"Wrote {len(notes)} notes to {args.output.resolve()}")
    if timing["starts_moved_over_50ms"]:
        suggestion = "Try a finer rhythm grid" if args.grid < 64 else "Review the tempo and rhythm"
        print(
            f"Timing note: {timing['starts_moved_over_50ms']} note "
            f"{'start' if timing['starts_moved_over_50ms'] == 1 else 'starts'} moved by over 50 ms "
            f"when fitted to the score. {suggestion}; saved notes can be rebuilt without listening again."
        )


from .events import load_events, save_events

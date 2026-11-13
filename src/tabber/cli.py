import argparse
import json
import math
import subprocess
from dataclasses import asdict
from datetime import datetime
from functools import partial
from pathlib import Path

from .audio import inspect_audio, prepare_audio
from .export import write_outputs
from .fretting import (
    StringAssignmentConflict,
    UnplayablePitch,
    assign_frets,
    assign_polyphonic_frets,
    fret_positions,
    recover_overlapping_notes,
)
from .gp5 import GridCollision
from .models import STANDARD_TUNING
from .pitch_midi import check_notes_only_output, write_pitch_midi
from .rhythm import (
    DEFAULT_METER,
    SCORE_GRIDS,
    lead_attacks,
    parse_meter,
    quantize,
    recorded_meter,
    recorded_score_grid,
)
from .separate import separate_guitar
from .tempo import estimate_tempo, parse_bpm, recorded_bpm
from .transcribe import baseline_frequency_floor, transcribe
from .tuning import parse_tuning, recorded_tuning


def _write_score_at_grid(notes, output, bpm, grid, tuning, meter, refit):
    try:
        return write_outputs(notes, output, bpm, grid, tuning=tuning, meter=meter), False
    except GridCollision as collision:
        if refit is None:
            raise
        try:
            fitted = refit(score_grid=(int(bpm + 0.5), grid))
        except ValueError:
            raise collision from None
        return write_outputs(fitted, output, bpm, grid, tuning=tuning, meter=meter), True


def _record_overlap_recovery(original_events, retained, audit, *, score_grid=None):
    shortened, omitted = [], []
    for index, original in enumerate(original_events):
        record = {"source_index": index, "original": asdict(original)}
        if index not in retained:
            omitted.append(record)
        elif retained[index].end < original.end:
            shortened.append({**record, "new_end": retained[index].end})
    audit.write_text(
        json.dumps(
            {
                "index_convention": "Zero-based index into the events before overlap recovery",
                "shortened": shortened,
                "omitted": omitted,
                "score_grid": score_grid,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    scope = f" after a collision on the 1/{score_grid} grid" if score_grid else " during fingering"
    print(
        f"Fingering note: Shortened {len(shortened)} releases and omitted {len(omitted)} "
        f"notes for tab export{scope}. Original detections are saved.",
        flush=True,
    )
    return {"shortened": len(shortened), "omitted": len(omitted), "audit": str(audit.resolve())}


def main():
    parser = argparse.ArgumentParser(description="Experimental audio-to-guitar-tab converter")
    parser.add_argument("audio", type=Path, nargs="?")
    parser.add_argument("--events", type=Path, help="Rebuild a tab from saved detected-notes.json")
    parser.add_argument(
        "--attack-lead-ms",
        type=float,
        default=0,
        help="For saved-event tab rebuilds, move attacks earlier by up to 50 ms and retain releases",
    )
    parser.add_argument(
        "--string-model",
        type=Path,
        help="Experimental local string-timbre NPZ model (audio input, polyphonic mode)",
    )
    parser.add_argument("--output", type=Path, default=Path("runs/latest"))
    parser.add_argument(
        "--notes-only",
        action="store_true",
        help="Save detected events and original-timing MIDI without fingering or GP5/grid export",
    )
    parser.add_argument(
        "--tuning",
        type=parse_tuning,
        help="A tuning preset or six or seven MIDI pitches, thin to thick. Defaults to saved tuning or standard.",
    )
    parser.add_argument(
        "--bpm",
        type=parse_bpm,
        help="Quarter-note BPM or auto. Default is saved BPM when available, otherwise 120.",
    )
    parser.add_argument(
        "--grid",
        type=int,
        choices=SCORE_GRIDS,
        help="Score divisions per whole note. Defaults to the saved grid or 16.",
    )
    parser.add_argument(
        "--retry-finer-grid",
        action="store_true",
        help="Try the next finer grid if score quantization still causes a collision",
    )
    parser.add_argument(
        "--meter",
        type=parse_meter,
        help="Constant time signature, for example 6/8. Defaults to the saved meter or 4/4.",
    )
    parser.add_argument(
        "--backend", choices=("baseline", "basic-pitch", "guitar-gaps"), default="baseline"
    )
    parser.add_argument(
        "--onset-threshold", type=float, help="Guitar-model attack threshold (default 0.3)"
    )
    parser.add_argument(
        "--guitar-checkpoint", type=Path, help="Location of the pinned published guitar checkpoint"
    )
    parser.add_argument(
        "--guitar-retry-empty",
        action="store_true",
        help="Retry an empty guitar-model result once at half input level",
    )
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
    parser.add_argument(
        "--guitar-range",
        action="store_true",
        help="Explicitly exclude pitches outside selected tuning / 24 frets; retain raw diagnostics",
    )
    parser.add_argument(
        "--preferred-span",
        "--max-span",
        type=int,
        default=5,
        help="Preferred simultaneous fretted span, 0–24 (default 5). Wider spans are allowed.",
    )
    parser.add_argument(
        "--strict-overlaps",
        action="store_true",
        help="Keep all detected overlaps even when they prevent editable tab export",
    )
    args = parser.parse_args()
    if (args.audio is None) == (args.events is None):
        parser.error("Provide either an audio file or --events, not both")
    if args.events and args.separate:
        parser.error("--separate needs audio input")
    if args.events and args.bpm == "auto":
        parser.error("--bpm auto needs audio input; supply BPM when rebuilding saved events")
    if not math.isfinite(args.attack_lead_ms) or not 0 <= args.attack_lead_ms <= 50:
        parser.error("--attack-lead-ms must be from 0 to 50")
    if args.attack_lead_ms and (not args.events or args.notes_only):
        parser.error("--attack-lead-ms applies only to editable tab rebuilds from --events")
    if args.retry_finer_grid and args.notes_only:
        parser.error("--retry-finer-grid requires editable tab output")
    if args.meter and args.notes_only:
        parser.error("--meter requires editable tab output")
    if not 0 <= args.preferred_span <= 24:
        parser.error("--preferred-span must be from 0 to 24")
    if args.fretting == "melodic" and args.preferred_span != 5:
        parser.error("--preferred-span applies to polyphonic fretting")
    if args.string_model and (args.events or args.fretting != "polyphonic"):
        parser.error("--string-model needs audio input and polyphonic fretting")
    if args.notes_only and args.string_model:
        parser.error("--string-model does not apply to --notes-only output")
    if args.string_model and (args.tuning or STANDARD_TUNING) != STANDARD_TUNING:
        parser.error(
            "The experimental string-tone model has only been evaluated in standard tuning"
        )
    if (args.onset_threshold is not None or args.guitar_checkpoint or args.guitar_retry_empty) and (
        args.events or args.backend != "guitar-gaps"
    ):
        parser.error("Guitar-model options need --backend guitar-gaps and audio input")
    try:
        if args.attack_lead_ms and args.output.exists() and any(args.output.iterdir()):
            raise ValueError("Choose a fresh output folder for the timing comparison")
        if args.notes_only:
            check_notes_only_output(args.output, source=args.audio or args.events)
        path = (args.audio or args.events).resolve()
        if not args.notes_only and path in {
            (args.output / name).resolve()
            for name in ("detected-notes.json", "notes.json", "notes.mid", "tab.gp5", "tab.txt")
        }:
            raise ValueError("Choose a different output folder to preserve the input file")
        if not path.is_file():
            raise ValueError(f"Input file does not exist: {path}")
        health = None
        if args.audio:
            path = prepare_audio(path, args.output / "diagnostics")
            health = inspect_audio(path)
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
            check_path = args.output / "diagnostics" / f"audio-{stamp}.json"
            check_path.parent.mkdir(parents=True, exist_ok=True)
            check_path.write_text(json.dumps(health, indent=2) + "\n", encoding="utf-8")
            for warning in health["warnings"]:
                print("Audio note: " + warning, flush=True)
        saved_bpm = None
        saved_tuning = None
        saved_grid = None
        saved_meter = None
        if args.events:
            detected, saved_metadata = load_event_document(path)
            saved_bpm = recorded_bpm(saved_metadata)
            saved_tuning = recorded_tuning(saved_metadata)
            saved_grid = recorded_score_grid(saved_metadata)
            saved_meter = recorded_meter(saved_metadata)
        tuning = args.tuning or saved_tuning or STANDARD_TUNING
        grid = args.grid or saved_grid or 16
        meter = args.meter or saved_meter or DEFAULT_METER
        tempo = estimate_tempo(path) if args.bpm == "auto" else None
        bpm = tempo.bpm if tempo else args.bpm or saved_bpm or 120.0
        tempo_source = "estimated" if tempo else "supplied"
        if args.bpm is None:
            tempo_source = "saved" if saved_bpm is not None else "default"
        quantize(0, bpm)
        if args.audio and args.backend == "baseline" and baseline_frequency_floor(min(tuning)) < 75:
            print(
                f"Detector note: Using the selected tuning's lower search limit ({baseline_frequency_floor(min(tuning)):.1f} Hz) for the simple melody detector.",
                flush=True,
            )
        if tempo:
            print(
                f"Estimated tempo: {bpm:.1f} BPM (provisional; review rhythmic grouping)",
                flush=True,
            )
        if args.separate:
            print("Progress: Separating guitar from the mix.", flush=True)
            path = separate_guitar(path, args.output / "stems")
        if args.audio:
            detector_status = {
                "baseline": "Detecting single-note melody (one pitch at a time).",
                "basic-pitch": "Detecting notes with Basic Pitch.",
                "guitar-gaps": "Detecting notes with the experimental guitar model.",
            }
            print(f"Progress: {detector_status[args.backend]}", flush=True)
            if args.backend == "guitar-gaps":
                detected = transcribe(
                    path,
                    args.backend,
                    args.min_confidence,
                    guitar_onset=args.onset_threshold if args.onset_threshold is not None else 0.3,
                    guitar_checkpoint=args.guitar_checkpoint,
                )
            elif args.backend == "baseline" and baseline_frequency_floor(min(tuning)) < 75:
                detected = transcribe(
                    path, args.backend, args.min_confidence, baseline_min_pitch=min(tuning)
                )
            else:
                detected = transcribe(path, args.backend, args.min_confidence)
        metadata = {
            "input": str(path),
            "audio_check": health,
            "original_input": str((args.audio or args.events).resolve()),
            "separated": args.separate,
            "bpm": bpm,
            "tempo_source": tempo_source,
            "tempo_estimate": asdict(tempo) if tempo else None,
            "backend": "events" if args.events else args.backend,
            "min_confidence": None
            if args.events or args.backend == "guitar-gaps"
            else args.min_confidence,
            "guitar_model_onset_threshold": (
                args.onset_threshold if args.onset_threshold is not None else 0.3
            )
            if args.backend == "guitar-gaps" and not args.events
            else None,
            "guitar_model_confidence": "Onset regression activation, not calibrated probability"
            if args.backend == "guitar-gaps" and not args.events
            else None,
            "timing": "seconds, original detected timing before score quantization",
            "experimental_string_model": str(args.string_model) if args.string_model else None,
            "preferred_fret_span": args.preferred_span
            if args.fretting == "polyphonic" and not args.notes_only
            else None,
            "output_mode": "notes-only" if args.notes_only else "editable-tab",
            "score_grid": None if args.notes_only else grid,
            "score_meter": None if args.notes_only else meter,
            "fingering_requested": not args.notes_only,
            "guitar_range_filter_requested": args.guitar_range,
            "baseline_minimum_search_hz": baseline_frequency_floor(min(tuning))
            if args.audio and args.backend == "baseline"
            else None,
            "tuning_midi": list(tuning),
            "tuning_string_order": f"string 1 (thin) to string {len(tuning)} (thick)",
        }
        if args.backend == "guitar-gaps" and not args.events:
            from .guitar_gaps import (
                CHECKPOINT_NAME,
                CHECKPOINT_SHA256,
                MODEL_REPOSITORY,
                MODEL_REVISION,
                default_checkpoint,
            )

            metadata["guitar_model"] = {
                "repository": MODEL_REPOSITORY,
                "revision": MODEL_REVISION,
                "filename": CHECKPOINT_NAME,
                "sha256": CHECKPOINT_SHA256,
                "checkpoint": str((args.guitar_checkpoint or default_checkpoint()).resolve()),
                "verification": "Pinned checksum verified before loading weights",
            }
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        diagnostic = args.output / "diagnostics" / f"detected-{stamp}.json"
        if args.guitar_retry_empty:
            metadata["guitar_empty_retry_requested"] = True
        save_events(detected, diagnostic, metadata)
        print(f"Detected note events saved to {diagnostic.resolve()}", flush=True)
        if not detected and args.guitar_retry_empty:
            from .guitar_gaps import transcribe_gaps

            print(
                "Detector note: No notes on the first pass. Retrying at half input level.",
                flush=True,
            )
            first_diagnostic = diagnostic.resolve()
            detected = transcribe_gaps(
                path,
                checkpoint=args.guitar_checkpoint,
                onset_threshold=metadata["guitar_model_onset_threshold"],
                input_gain=0.5,
            )
            diagnostic = args.output / "diagnostics" / f"retry-{stamp}.json"
            metadata["guitar_empty_retry"] = {
                "first_attempt_events": str(first_diagnostic),
                "retry_events": str(diagnostic.resolve()),
                "input_gain": 0.5,
                "retry_note_count": len(detected),
            }
            save_events(detected, diagnostic, metadata)
        if not detected:
            if args.audio and args.backend == "guitar-gaps":
                raise ValueError(
                    "The guitar model detected no notes. Try Basic Pitch on the same audio. "
                    "For a full-band recording, try separating guitar first if you have not already."
                )
            raise ValueError(
                "No notes detected. Check that the guitar is clearly audible in the recording."
            )
        selected = detected
        if args.guitar_range:
            minimum, maximum = min(tuning), min(127, max(tuning) + 24)
            selected, excluded = [], []
            for index, note in enumerate(detected):
                if fret_positions(note.pitch, tuning):
                    selected.append(note)
                else:
                    excluded.append({"source_index": index, "note": asdict(note)})
            report_path = args.output / "diagnostics" / f"range-filter-{stamp}.json"
            audit = {
                "purpose": "Explicitly requested filter for pitches without a string at frets 0-24",
                "tuning_midi": list(tuning),
                "min_pitch": minimum,
                "max_pitch": maximum,
                "source_note_count": len(detected),
                "retained_note_count": len(selected),
                "excluded_note_count": len(excluded),
                "excluded": excluded,
                "unfiltered_events": str(diagnostic.resolve()),
                "source_index_convention": "Zero-based index into the unfiltered events file",
            }
            report_path.write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
            metadata["guitar_range_filter"] = {
                key: value for key, value in audit.items() if key != "excluded"
            }
            metadata["guitar_range_filter"]["audit_file"] = str(report_path.resolve())
            save_events(selected, args.output / "diagnostics" / f"selected-{stamp}.json", metadata)
            print(
                f"Range note: Excluded {len(excluded)} of {len(detected)} detections with no string "
                "in the selected tuning at frets 0-24. Raw notes and exclusions are saved in diagnostics.",
                flush=True,
            )
            if detected and not selected:
                raise ValueError(
                    "The requested range filter excluded every detection. Review the raw notes in diagnostics."
                )
        if args.notes_only:
            write_pitch_midi(selected, args.output, bpm)
            metadata["fingering_applied"] = False
            metadata["midi_timing"] = (
                "Original seconds rounded to 480 ticks per quarter note; minimum one tick duration. No score-grid snapping or string channels."
            )
            save_events(selected, args.output / "detected-notes.json", metadata)
            print(
                f"Wrote {len(selected)} detected events and MIDI to {args.output.resolve()} without fingering or score-grid snapping."
            )
            return
        assign = assign_frets if args.fretting == "melodic" else assign_polyphonic_frets
        assignment_options = {} if args.fretting == "melodic" else {"max_span": args.preferred_span}
        if args.string_model:
            from .string_model import string_priors

            assignment_options["string_priors"] = string_priors(path, selected, args.string_model)
        export_events = selected
        if args.attack_lead_ms:
            export_events, limited = lead_attacks(selected, args.attack_lead_ms / 1000)
            adjusted_path = args.output / "diagnostics" / f"export-events-{stamp}.json"
            metadata["export_attack_adjustment"] = {
                "lead_ms": args.attack_lead_ms,
                "changed_attacks": sum(a.start != b.start for a, b in zip(selected, export_events)),
                "positive_attacks_clamped_to_zero": sum(
                    a.start > 0 and b.start == 0 for a, b in zip(selected, export_events)
                ),
                "attacks_limited_by_previous_release": limited,
                "export_events": str(adjusted_path.resolve()),
                "unadjusted_events": str(diagnostic.resolve()),
            }
            save_events(
                export_events,
                adjusted_path,
                {**metadata, "timing": "Adjusted attacks in seconds before score quantization"},
            )
            print(
                f"Timing note: Applied a {args.attack_lead_ms:g} ms attack lead for export. Original events are preserved.",
                flush=True,
            )
        original_events = export_events
        original_options = assignment_options.copy()
        audit = args.output / "diagnostics" / f"overlap-recovery-{stamp}.json"
        print("Progress: Assigning notes to guitar strings.", flush=True)
        try:
            notes = assign(export_events, tuning=tuning, **assignment_options)
        except StringAssignmentConflict:
            if args.strict_overlaps:
                raise
            print("Progress: Resolving overlapping notes.", flush=True)
            notes, retained = recover_overlapping_notes(
                export_events, tuning=tuning, **assignment_options
            )
            metadata["overlap_recovery"] = _record_overlap_recovery(
                original_events, retained, audit
            )
            if "string_priors" in assignment_options:
                priors = assignment_options["string_priors"]
                assignment_options["string_priors"] = [priors[index] for index in retained]
            export_events = list(retained.values())
        refit = (
            partial(assign_polyphonic_frets, export_events, tuning=tuning, **assignment_options)
            if args.fretting == "polyphonic"
            else None
        )
        grids = SCORE_GRIDS[SCORE_GRIDS.index(grid) :] if args.retry_finer_grid else (grid,)
        print("Progress: Building the Guitar Pro score.", flush=True)
        for candidate in grids:
            try:
                timing, refitted = _write_score_at_grid(
                    notes, args.output, bpm, candidate, tuning, meter, refit
                )
            except GridCollision:
                if candidate != grids[-1]:
                    continue
                if not args.retry_finer_grid or args.strict_overlaps or refit is None:
                    raise
                print("Progress: Resolving overlapping notes on the score grid.", flush=True)
                notes, retained = recover_overlapping_notes(
                    original_events,
                    tuning=tuning,
                    score_grid=(int(bpm + 0.5), candidate),
                    **original_options,
                )
                metadata["overlap_recovery"] = _record_overlap_recovery(
                    original_events, retained, audit, score_grid=candidate
                )
                timing = write_outputs(
                    notes, args.output, bpm, candidate, tuning=tuning, meter=meter
                )
                refitted = True
                break
            else:
                break
        if refitted:
            metadata["score_grid_fingering_retry"] = True
        if candidate != grid:
            retry = {"requested": grid, "used": candidate}
            metadata.update(score_grid=candidate, finer_grid_retry=retry)
            _, original_metadata = load_event_document(diagnostic)
            original_metadata.update(score_grid=candidate, finer_grid_retry=retry)
            save_events(detected, diagnostic, original_metadata)
            print(
                f"Timing note: Used a 1/{candidate} grid after a collision at 1/{grid}.", flush=True
            )
            grid = candidate
        save_events(selected, args.output / "detected-notes.json", metadata)
    except (ValueError, OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        if isinstance(exc, GridCollision):
            if not args.retry_finer_grid and grid < SCORE_GRIDS[-1]:
                print(
                    "Timing note: Rebuild from the saved detections and enable "
                    "Try a finer grid if notes collide (--retry-finer-grid).",
                    flush=True,
                )
            else:
                print(
                    "Timing note: Review the tempo or edit the saved detections before rebuilding.",
                    flush=True,
                )
        if isinstance(exc, UnplayablePitch):
            message = "Check the guitar's tuning and rebuild from the saved detections."
            if not args.guitar_range:
                message += (
                    " If the tuning is correct, enable Exclude notes outside selected tuning / "
                    "24 frets (--guitar-range) to leave out pitches without a valid string and fret."
                )
            print(f"Range note: {message}", flush=True)
        parser.exit(1, f"Could not transcribe: {exc}\n")
    print(f"Wrote {len(notes)} notes to {args.output.resolve()}")
    if timing["starts_moved_over_50ms"]:
        suggestion = "Try a finer rhythm grid" if grid < 64 else "Review the tempo and rhythm"
        print(
            f"Timing note: {timing['starts_moved_over_50ms']} note "
            f"{'start' if timing['starts_moved_over_50ms'] == 1 else 'starts'} moved by over 50 ms "
            f"when fitted to the score. {suggestion}; saved notes can be rebuilt without listening again."
        )


from .events import load_event_document, save_events

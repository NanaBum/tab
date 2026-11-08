"""Check independent MIDI string voices from cached detections, without ML."""

import argparse
import json
import tempfile
import zipfile
from collections import Counter
from pathlib import Path

import mido

from tabber.export import write_outputs
from tabber.fretting import assign_polyphonic_frets
from tabber.models import Note


def midi_events(path):
    """Decode our one-track, one-channel-per-string MIDI; reject ambiguous releases."""
    midi = mido.MidiFile(path)
    if len(midi.tracks) != 1 or midi.ticks_per_beat != 480:
        raise ValueError("Unexpected MIDI track count or tick resolution")
    tick, active, events, programs, tempos = 0, {}, [], {}, []
    for message in midi.tracks[0]:
        tick += message.time
        if message.type == "program_change":
            programs[message.channel] = message.program
        elif message.type == "set_tempo":
            tempos.append(message.tempo)
        elif message.type == "note_on" and message.velocity:
            if message.channel in active:
                raise ValueError("Simultaneous notes share one string channel")
            if not 0 <= message.channel < 6 or programs.get(message.channel) != 24:
                raise ValueError("Unexpected MIDI channel or guitar program")
            active[message.channel] = tick, message.note
        elif message.type in ("note_on", "note_off"):
            if message.channel not in active:
                raise ValueError("Release has no active note")
            first, pitch = active.pop(message.channel)
            if pitch != message.note or tick <= first:
                raise ValueError("Wrong MIDI release pitch or nonpositive duration")
            events.append((first, tick, message.channel, pitch))
    if active or len(tempos) != 1:
        raise ValueError("Stuck notes or unexpected tempo changes")
    return events, tempos[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("predictions", type=Path)
    parser.add_argument("--data", type=Path, default=Path("data/guitarset"))
    parser.add_argument("--output", type=Path, default=Path("runs/midi-validation.json"))
    args = parser.parse_args()
    data = json.loads(args.predictions.read_text(encoding="utf-8"))
    report = {
        "purpose": "MIDI serialization and independent releases, not transcription accuracy",
        "channels": "0-5 map to strings high E through low E; guitar program 24 on each",
        "resolution": "480 ticks per quarter; nearest ticks, at least one tick per note",
        "passed_clips": 0,
        "verified_notes": 0,
        "fingering_failures": [],
        "failures": [],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with (
        zipfile.ZipFile(args.data / "annotation.zip") as annotations,
        tempfile.TemporaryDirectory(prefix="midi-audit-", dir=args.output.parent) as temporary,
    ):
        folder = Path(temporary) / "export"
        for index, row in enumerate(data["tracks"]):
            if index % 30 == 0:
                print(f"MIDI check {index}/{len(data['tracks'])}", flush=True)
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
            try:
                write_outputs(notes, folder, bpm, grid=32)
                actual, tempo = midi_events(folder / "notes.mid")
                expected = []
                for note in notes:
                    first = round(note.note.start * bpm / 60 * 480)
                    last = max(first + 1, round(note.note.end * bpm / 60 * 480))
                    expected.append((first, last, note.string, note.note.pitch))
                if tempo != mido.bpm2tempo(bpm) or Counter(actual) != Counter(expected):
                    raise ValueError("MIDI changed source note events")
            except (ValueError, OSError) as error:
                report["failures"].append({"track": row["track"], "error": str(error)})
            else:
                report["passed_clips"] += 1
                report["verified_notes"] += len(notes)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

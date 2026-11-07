import json
from dataclasses import asdict
from pathlib import Path

import mido

from .gp5 import build_song, write_gp5
from .models import FrettedNote
from .rhythm import quantize


def write_outputs(notes: list[FrettedNote], output: Path, bpm: float) -> None:
    quantize(0, bpm)
    song = build_song(notes, bpm)
    output.mkdir(parents=True, exist_ok=True)
    payload = {"bpm": bpm, "string_order": "high E to low E", "notes": [asdict(n) for n in notes]}
    (output / "notes.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    cells = max((quantize(n.note.end, bpm) for n in notes), default=1) + 1
    rows = [["----"] * cells for _ in range(6)]
    occupied = set()
    for n in notes:
        column = quantize(n.note.start, bpm)
        if (n.string, column) in occupied:
            raise ValueError(
                "Two notes collide on the tab grid; increase the tempo or edit the JSON"
            )
        occupied.add((n.string, column))
        rows[n.string][column] = f"{n.fret:-^4}"
    text = [
        f"Tempo: {bpm:g} BPM | one cell = a sixteenth note; dashes show no new onset",
        "Timing and durations are preserved in notes.json and notes.mid.",
        "",
    ]
    for first in range(0, cells, 32):
        text.extend(
            f"{label}|{''.join(row[first : first + 32])}|"
            for label, row in zip(("e", "B", "G", "D", "A", "E"), rows)
        )
        text.append("")
    (output / "tab.txt").write_text("\n".join(text), encoding="utf-8")
    midi = mido.MidiFile(ticks_per_beat=480)
    track = mido.MidiTrack()
    midi.tracks.append(track)
    track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(bpm)))
    track.append(mido.Message("program_change", program=24))
    events = []
    for n in notes:
        for time, kind in ((n.note.start, "note_on"), (n.note.end, "note_off")):
            tick = round(time * bpm / 60 * 480)
            events.append((tick, kind, n.note.pitch))
    previous = 0
    for tick, kind, pitch in sorted(events, key=lambda e: (e[0], e[1] == "note_on")):
        track.append(
            mido.Message(
                kind, note=pitch, velocity=80 if kind == "note_on" else 0, time=tick - previous
            )
        )
        previous = tick
    midi.save(output / "notes.mid")
    write_gp5(song, output / "tab.gp5")

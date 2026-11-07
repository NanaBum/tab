import io
import json
import os
import tempfile
from dataclasses import asdict
from pathlib import Path

import mido

from .gp5 import build_song, write_gp5
from .models import FrettedNote
from .rhythm import quantize


def write_outputs(notes: list[FrettedNote], output: Path, bpm: float, grid: int = 16) -> None:
    quantize(0, bpm)
    song = build_song(notes, bpm, grid)
    payload = {"bpm": bpm, "string_order": "high E to low E", "notes": [asdict(n) for n in notes]}
    payload["score_grid"] = grid
    cells = max((quantize(n.note.end, bpm, grid // 4) for n in notes), default=1) + 1
    rows = [["----"] * cells for _ in range(6)]
    occupied = set()
    for n in notes:
        column = quantize(n.note.start, bpm, grid // 4)
        if (n.string, column) in occupied:
            raise ValueError(f"Two notes collide on the 1/{grid} tab grid; choose a finer --grid")
        occupied.add((n.string, column))
        rows[n.string][column] = f"{n.fret:-^4}"
    text = [
        f"Tempo: {bpm:g} BPM | one cell = 1/{grid} note; dashes show no new onset",
        "Timing and durations are preserved in notes.json and notes.mid.",
        "",
    ]
    for first in range(0, cells, 32):
        text.extend(
            f"{label}|{''.join(row[first : first + 32])}|"
            for label, row in zip(("e", "B", "G", "D", "A", "E"), rows)
        )
        text.append("")
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
    midi_bytes = io.BytesIO()
    midi.save(file=midi_bytes)
    # Render all formats before creating or changing the requested output folder.
    # Per-file replacements are atomic; a filesystem failure during replacement
    # can still leave a mixture of old and new formats, so it is not a transaction.
    gp5_bytes = io.BytesIO()
    write_gp5(song, gp5_bytes)
    rendered = {
        "notes.json": (json.dumps(payload, indent=2) + "\n").encode("utf-8"),
        "tab.txt": "\n".join(text).encode("utf-8"),
        "notes.mid": midi_bytes.getvalue(),
        "tab.gp5": gp5_bytes.getvalue(),
    }
    output.mkdir(parents=True, exist_ok=True)
    for filename, content in rendered.items():
        with tempfile.NamedTemporaryFile(dir=output, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content)
        try:
            os.replace(temporary, output / filename)
        finally:
            temporary.unlink(missing_ok=True)

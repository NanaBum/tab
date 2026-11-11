import io
import json
import os
import tempfile
from dataclasses import asdict
from pathlib import Path

import mido

from .gp5 import build_song, read_gp5, timing_summary, verify_export, write_gp5
from .models import STANDARD_TUNING, FrettedNote
from .rhythm import DEFAULT_METER, parse_meter, quantize
from .tuning import pitch_name, validate_tuning


def write_outputs(
    notes: list[FrettedNote],
    output: Path,
    bpm: float,
    grid: int = 16,
    *,
    tuning=STANDARD_TUNING,
    meter=DEFAULT_METER,
) -> dict:
    tuning = validate_tuning(tuning)
    meter = parse_meter(meter)
    quantize(0, bpm)
    song = build_song(notes, bpm, grid, tuning=tuning, meter=meter)
    payload = {"bpm": bpm, "string_order": "high E to low E", "notes": [asdict(n) for n in notes]}
    if tuning != STANDARD_TUNING:
        payload["string_order"] = f"string 1 to string {len(tuning)}"
    payload["score_grid"] = grid
    payload["score_meter"] = meter
    payload["tuning_midi"] = list(tuning)
    payload["tuning_string_order"] = f"string 1 (thin) to string {len(tuning)} (thick)"
    cells = max((quantize(n.note.end, bpm, grid // 4) for n in notes), default=1) + 1
    rows = [["----"] * cells for _ in tuning]
    occupied = set()
    for n in notes:
        column = quantize(n.note.start, bpm, grid // 4)
        if (n.string, column) in occupied:
            raise ValueError(f"Two notes collide on the 1/{grid} tab grid; choose a finer --grid")
        occupied.add((n.string, column))
        rows[n.string][column] = f"{n.fret:-^4}"
    text = [
        f"Tempo: {bpm:g} BPM | one cell = 1/{grid} note; dashes show no new onset",
        "Pre-quantization timing is in notes.json; MIDI rounds it to 480 ticks per quarter note.",
        "",
    ]
    labels = (
        ("e", "B", "G", "D", "A", "E")
        if tuning == STANDARD_TUNING
        else tuple(pitch_name(p) for p in tuning)
    )
    if tuning != STANDARD_TUNING:
        text.insert(1, f"Open strings (1 to {len(tuning)}): " + " ".join(labels))
    if meter != DEFAULT_METER:
        text.insert(1, f"Time signature: {meter}")
    for first in range(0, cells, 32):
        text.extend(
            f"{label}|{''.join(row[first : first + 32])}|" for label, row in zip(labels, rows)
        )
        text.append("")
    midi = mido.MidiFile(ticks_per_beat=480)
    track = mido.MidiTrack()
    midi.tracks.append(track)
    track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(bpm)))
    if meter != DEFAULT_METER:
        numerator, denominator = map(int, meter.split("/"))
        track.append(
            mido.MetaMessage("time_signature", numerator=numerator, denominator=denominator)
        )
    # One channel per string keeps overlapping unisons independently releasable.
    # Channels 0-6 avoid the conventional percussion channel (9).
    for channel in range(len(tuning)):
        track.append(mido.Message("program_change", program=24, channel=channel))
    events = []
    ends_by_string = {}
    shifted_starts = maximum_delay = 0
    for n in sorted(notes, key=lambda n: n.note.start):
        start = round(n.note.start * bpm / 60 * 480)
        previous_end, previous_tick = ends_by_string.get(n.string, (0.0, 0))
        if start < previous_tick:
            if n.note.start + 1e-6 < previous_end:
                raise ValueError("Notes on one string overlap before MIDI timing conversion")
            shifted_starts += 1
            maximum_delay = max(maximum_delay, previous_tick - start)
            start = previous_tick
        end = max(start + 1, round(n.note.end * bpm / 60 * 480))
        ends_by_string[n.string] = (n.note.end, end)
        for tick, kind in ((start, "note_on"), (end, "note_off")):
            events.append((tick, kind, n.note.pitch, n.string))
    if shifted_starts:
        payload["midi_timing"] = {
            "shifted_starts": shifted_starts,
            "maximum_start_delay_ticks": maximum_delay,
            "ticks_per_quarter_note": 480,
        }
    previous = 0
    for tick, kind, pitch, channel in sorted(events, key=lambda e: (e[0], e[1] == "note_on")):
        track.append(
            mido.Message(
                kind,
                note=pitch,
                velocity=80 if kind == "note_on" else 0,
                time=tick - previous,
                channel=channel,
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
    gp5_bytes.seek(0)
    saved_song = read_gp5(gp5_bytes)
    verify_export(saved_song, notes, bpm, grid, tuning=tuning, meter=meter)
    timing = timing_summary(saved_song, notes)
    payload["score_timing"] = timing
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
    return timing

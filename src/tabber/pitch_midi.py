"""MIDI audition of raw note events, independent of string/fret assignment."""

import io
import os
import tempfile
from pathlib import Path

import mido

from .rhythm import quantize


def check_notes_only_output(output, *, source=None):
    if source is not None and source.resolve() in {
        (output / name).resolve() for name in ("notes.mid", "detected-notes.json")
    }:
        raise ValueError(
            "Use a different output folder; notes-only output must not overwrite its input"
        )
    if any((output / name).exists() for name in ("tab.gp5", "tab.txt", "notes.json")):
        raise ValueError(
            "Use a new output folder for notes-only mode; existing tab files would be misleading"
        )


def write_pitch_midi(notes, output, bpm):
    """Preserve every pitch and approximate original times at MIDI tick resolution.

    Channels separate overlapping unisons without inventing guitar positions.
    Different pitches may share a channel. Refuse over 15 simultaneous same-pitch
    events rather than merging their releases or dropping any notes.
    """
    check_notes_only_output(output)
    quantize(0, bpm)
    midi = mido.MidiFile(ticks_per_beat=480)
    track = mido.MidiTrack()
    midi.tracks.append(track)
    track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(bpm)))
    channels = tuple(c for c in range(16) if c != 9)
    events, ends, used = [], {}, set()
    for note in sorted(notes, key=lambda item: item.start):
        first = round(note.start * bpm / 60 * 480)
        last = max(first + 1, round(note.end * bpm / 60 * 480))
        channel = next((c for c in channels if ends.get((note.pitch, c), -1) <= first), None)
        if channel is None:
            raise ValueError(
                "MIDI cannot preserve more than 15 overlapping unisons; original events were not filtered"
            )
        used.add(channel)
        ends[note.pitch, channel] = last
        events.extend(
            ((first, "note_on", note.pitch, channel), (last, "note_off", note.pitch, channel))
        )
    for channel in sorted(used):
        track.append(mido.Message("program_change", program=24, channel=channel))
    previous = 0
    for tick, kind, pitch, channel in sorted(events, key=lambda e: (e[0], e[1] == "note_on")):
        track.append(
            mido.Message(
                kind,
                note=pitch,
                channel=channel,
                velocity=80 if kind == "note_on" else 0,
                time=tick - previous,
            )
        )
        previous = tick
    stream = io.BytesIO()
    midi.save(file=stream)
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=output, delete=False) as temporary:
        path = Path(temporary.name)
        temporary.write(stream.getvalue())
    try:
        os.replace(path, output / "notes.mid")
    finally:
        path.unlink(missing_ok=True)

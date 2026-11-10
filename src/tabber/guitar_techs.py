"""Read the explicitly named string tracks in Guitar-TECHS MIDI."""

from dataclasses import asdict

import mido

from .midi_reference import extract_midi_reference
from .models import STANDARD_TUNING

STRING_NAMES = ("e", "B", "G", "D", "A", "E")


def _tempo_track(track):
    """Preserve absolute tempo ticks when omitting another string's events."""
    output = mido.MidiTrack()
    delta = 0
    for message in track:
        delta += message.time
        if message.type == "set_tempo":
            output.append(message.copy(time=delta))
            delta = 0
    return output


def string_notes(midi):
    if midi.type != 1:
        raise ValueError("Expected synchronous multi-track Guitar-TECHS MIDI")
    tracks = {}
    for index, track in enumerate(midi.tracks):
        name = track.name
        if name in STRING_NAMES:
            if name in tracks:
                raise ValueError(f"Duplicate MIDI string track: {name}")
            tracks[name] = index
        elif any(m.type == "note_on" and m.velocity for m in track):
            raise ValueError(f"Sounding MIDI track has no recognized string name: {name}")
    if set(tracks) != set(STRING_NAMES):
        raise ValueError("Expected six explicitly named string tracks")
    tempos = [_tempo_track(track) for track in midi.tracks]
    notes = []
    for string, name in enumerate(STRING_NAMES):
        index = tracks[name]
        track = midi.tracks[index]
        if not any(m.type == "note_on" and m.velocity for m in track):
            continue
        isolated = mido.MidiFile(type=1, ticks_per_beat=midi.ticks_per_beat)
        isolated.tracks = tempos.copy()
        isolated.tracks[index] = track
        reference = extract_midi_reference(
            isolated, track_number=index + 1, allow_approximate_expression=True
        )
        for note in reference.notes:
            fret = note.pitch - STANDARD_TUNING[string]
            notes.append(
                {
                    **asdict(note),
                    "string": string,
                    "fret": fret,
                    "playable_standard": 0 <= fret <= 24,
                    "track_expression": reference.metadata["technique_flags"],
                }
            )
    return sorted(notes, key=lambda note: (note["start"], note["pitch"], note["string"]))

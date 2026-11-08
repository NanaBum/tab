import mido
import pytest

from scripts.validate_midi_exports import midi_events
from tabber.export import write_outputs
from tabber.models import FrettedNote, Note


def test_unison_strings_have_independent_midi_releases(tmp_path):
    # B-string fret 5 and open high E sound the same pitch, but release separately.
    notes = [FrettedNote(Note(0, 2, 64), 1, 5), FrettedNote(Note(0.5, 1, 64), 0, 0)]
    write_outputs(notes, tmp_path, 120)
    midi = mido.MidiFile(tmp_path / "notes.mid")
    active, recovered, programs = {}, [], {}
    tick = 0
    for message in midi.tracks[0]:
        tick += message.time
        if message.type == "program_change":
            programs[message.channel] = message.program
        elif message.type == "note_on" and message.velocity:
            key = message.channel, message.note
            assert key not in active, "Two sustained notes share a MIDI channel and pitch"
            active[key] = tick
        elif message.type in ("note_on", "note_off"):
            key = message.channel, message.note
            recovered.append((active.pop(key), tick, message.channel, message.note))
    assert not active
    assert sorted(recovered) == [(0, 1920, 1, 64), (480, 960, 0, 64)]
    assert programs[0] == programs[1] == 24


def test_subtick_note_has_positive_midi_duration_and_keeps_original_json(tmp_path):
    import json

    note = FrettedNote(Note(0.0001, 0.0002, 64), 0, 0)
    write_outputs([note], tmp_path, 120)
    messages = mido.MidiFile(tmp_path / "notes.mid").tracks[0]
    tick = 0
    events = []
    for message in messages:
        tick += message.time
        if message.type in ("note_on", "note_off"):
            events.append((tick, message.type))
    assert events == [(0, "note_on"), (1, "note_off")]
    original = json.loads((tmp_path / "notes.json").read_text())["notes"][0]["note"]
    assert original["start"] == 0.0001 and original["end"] == 0.0002


def test_adjacent_repeated_notes_release_before_reattack_on_the_same_string(tmp_path):
    notes = [FrettedNote(Note(0, 0.5, 64), 0, 0), FrettedNote(Note(0.5, 1, 64), 0, 0)]
    write_outputs(notes, tmp_path, 120)
    tick, at_boundary = 0, []
    for message in mido.MidiFile(tmp_path / "notes.mid").tracks[0]:
        tick += message.time
        if tick == 480 and message.type in ("note_on", "note_off"):
            at_boundary.append(message.type)
    assert at_boundary == ["note_off", "note_on"]


def test_midi_audit_detects_a_missing_release(tmp_path):
    write_outputs([FrettedNote(Note(0, 0.5, 64), 0, 0)], tmp_path, 120)
    path = tmp_path / "notes.mid"
    assert midi_events(path)[0] == [(0, 480, 0, 64)]
    midi = mido.MidiFile(path)
    midi.tracks[0][:] = [m for m in midi.tracks[0] if m.type != "note_off"]
    midi.save(path)
    with pytest.raises(ValueError, match="Stuck notes"):
        midi_events(path)

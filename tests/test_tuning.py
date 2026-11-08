import json

import mido
import pytest

from tabber.cli import main
from tabber.events import load_events, save_events
from tabber.export import write_outputs
from tabber.fretting import assign_polyphonic_frets
from tabber.gp5 import read_gp5, score_events, verify_export
from tabber.models import FrettedNote, Note
from tabber.note_files import read_notes
from tabber.reference import extract_reference
from tabber.tuning import PRESETS, parse_tuning, validate_tuning


@pytest.mark.parametrize("name", list(PRESETS))
def test_every_preset_exports_six_held_open_strings_with_correct_pitches(tmp_path, name):
    tuning = parse_tuning(name)
    notes = [Note(0, 2.5, pitch) for pitch in tuning]
    fretted = assign_polyphonic_frets(notes, tuning=tuning, max_span=0)
    assert {(n.string, n.fret) for n in fretted} == {(i, 0) for i in range(6)}
    write_outputs(fretted, tmp_path, 120, tuning=tuning)
    song = read_gp5(tmp_path / "tab.gp5")
    assert tuple(s.value for s in song.tracks[0].strings) == tuning
    assert len(score_events(song)) == 6
    verify_export(song, fretted, 120, 16, tuning=tuning)
    imported = extract_reference(song)
    assert sorted((n.start, n.end, n.pitch) for n in imported.notes) == sorted(
        (n.start, n.end, n.pitch) for n in notes
    )
    midi = mido.MidiFile(tmp_path / "notes.mid")
    assert sorted(m.note for m in midi if m.type == "note_on" and m.velocity) == sorted(tuning)
    payload = json.loads((tmp_path / "notes.json").read_text())
    assert payload["tuning_midi"] == list(tuning)
    assert sorted(n.pitch for n in read_notes(tmp_path / "notes.json")) == sorted(tuning)
    if name == "drop-d":
        assert "Open strings (1 to 6): E4 B3 G3 D3 A2 D2" in (tmp_path / "tab.txt").read_text()


def test_drop_d_fingering_cannot_be_exported_as_standard_tuning(tmp_path):
    note = FrettedNote(Note(0, 1, 38), 5, 0)
    with pytest.raises(ValueError, match="selected tuning"):
        write_outputs([note], tmp_path / "wrong", 120)
    assert not (tmp_path / "wrong").exists()


def test_drop_d_rebuild_and_range_audit_retain_low_d_without_listening(tmp_path, monkeypatch):
    source = tmp_path / "events.json"
    notes = [Note(i / 2, i / 2 + 0.25, pitch) for i, pitch in enumerate((37, 38, 64, 89))]
    save_events(notes, source)
    original = source.read_bytes()
    output = tmp_path / "out"
    monkeypatch.setattr(
        "sys.argv",
        [
            "tabber",
            "--events",
            str(source),
            "--output",
            str(output),
            "--tuning",
            "drop-d",
            "--guitar-range",
        ],
    )
    monkeypatch.setattr("tabber.cli.transcribe", lambda *a, **k: pytest.fail("Must not listen"))
    main()
    assert source.read_bytes() == original
    assert load_events(output / "detected-notes.json") == notes[1:3]
    audit = json.loads(next((output / "diagnostics").glob("range-filter-*.json")).read_text())
    assert audit["min_pitch"] == 38 and audit["max_pitch"] == 88
    assert audit["tuning_midi"] == list(PRESETS["drop-d"])
    assert [n["source_index"] for n in audit["excluded"]] == [0, 3]
    song = read_gp5(output / "tab.gp5")
    assert song.tracks[0].strings[5].value == 38


def test_custom_tuning_keeps_physical_string_order():
    assert parse_tuning("64,59,55,50,45,36") == (64, 59, 55, 50, 45, 36)
    assert parse_tuning(" DROP-D ") == PRESETS["drop-d"]


@pytest.mark.parametrize(
    "value", ["drop-c-typo", "64,59,55,50,45", "64,59,55,50,45,128", "64,59,55,50,45,38.5"]
)
def test_invalid_tuning_fails_before_conversion(value):
    with pytest.raises(ValueError):
        parse_tuning(value)


def test_boolean_is_not_a_tuning_pitch():
    with pytest.raises(ValueError):
        validate_tuning((64, 59, 55, 50, 45, False))


def test_string_tone_experiment_refuses_unsupported_tuning(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "sys.argv",
        [
            "tabber",
            str(tmp_path / "riff.wav"),
            "--tuning",
            "drop-d",
            "--string-model",
            "unused.npz",
        ],
    )
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2

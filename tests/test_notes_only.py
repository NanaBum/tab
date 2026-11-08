import json

import mido
import pytest

from tabber.cli import main
from tabber.events import load_events, save_events
from tabber.models import Note
from tabber.pitch_midi import write_pitch_midi


def midi_events(path):
    ticks, active, notes = 0, {}, []
    for message in mido.MidiFile(path).tracks[0]:
        ticks += message.time
        if message.type == "note_on" and message.velocity:
            key = message.channel, message.note
            assert key not in active, "Same-channel unisons would have ambiguous releases"
            assert message.channel != 9
            active[key] = ticks
        elif message.type == "note_off" or message.type == "note_on":
            key = message.channel, message.note
            notes.append((message.note, active.pop(key), ticks))
    assert not active
    return sorted(notes)


def test_notes_only_preserves_overlapping_unisons_extreme_pitches_and_releases(tmp_path):
    notes = [Note(i / 100, 1 + i / 100, 64) for i in range(7)] + [Note(0, 0.5, 0), Note(0, 2, 127)]
    write_pitch_midi(notes, tmp_path, 120)
    assert midi_events(tmp_path / "notes.mid") == sorted(
        (n.pitch, round(n.start * 960), round(n.end * 960)) for n in notes
    )
    assert not (tmp_path / "tab.gp5").exists()


def test_short_notes_have_positive_duration_and_touching_unisons_reuse_channels(tmp_path):
    notes = [Note(0, 0.00001, 64), Note(1 / 960, 2 / 960, 64)]
    write_pitch_midi(notes, tmp_path, 120)
    assert midi_events(tmp_path / "notes.mid") == [(64, 0, 1), (64, 1, 2)]


def test_unrepresentable_overlap_fails_without_changing_existing_midi(tmp_path):
    midi = tmp_path / "notes.mid"
    midi.write_bytes(b"earlier result")
    with pytest.raises(ValueError, match="15 overlapping"):
        write_pitch_midi([Note(0, 1, 64)] * 16, tmp_path, 120)
    assert midi.read_bytes() == b"earlier result"


def test_cli_notes_only_skips_fretting_and_preserves_every_saved_event(tmp_path, monkeypatch):
    source = tmp_path / "events.json"
    notes = [Note(0, 1, 38, 0.01)] + [Note(0, 1, 64, 0.01)] * 7
    save_events(notes, source)
    original = source.read_bytes()
    output = tmp_path / "out"
    monkeypatch.setattr(
        "sys.argv", ["tabber", "--events", str(source), "--notes-only", "--output", str(output)]
    )
    monkeypatch.setattr(
        "tabber.cli.assign_polyphonic_frets", lambda *a, **k: pytest.fail("Must not assign strings")
    )
    monkeypatch.setattr(
        "tabber.cli.transcribe", lambda *a, **k: pytest.fail("Must not listen again")
    )
    main()
    assert source.read_bytes() == original
    assert load_events(output / "detected-notes.json") == notes
    assert len(midi_events(output / "notes.mid")) == 8
    metadata = json.loads((output / "detected-notes.json").read_text())["metadata"]
    assert metadata["output_mode"] == "notes-only" and metadata["fingering_applied"] is False
    assert not (output / "tab.gp5").exists() and not (output / "notes.json").exists()


@pytest.mark.parametrize("filename", ["tab.gp5", "tab.txt", "notes.json"])
def test_stale_tab_folder_is_refused_before_listening_or_overwriting(
    tmp_path, monkeypatch, filename
):
    old = tmp_path / filename
    old.write_bytes(b"keep previous tab")
    monkeypatch.setattr(
        "sys.argv", ["tabber", "absent.wav", "--notes-only", "--output", str(tmp_path)]
    )
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 1
    assert old.read_bytes() == b"keep previous tab"


def test_range_filter_stays_explicit_in_notes_only_mode(tmp_path, monkeypatch):
    source = tmp_path / "input.json"
    notes = [Note(0, 1, 38), Note(1, 2, 64)]
    save_events(notes, source)
    output = tmp_path / "filtered"
    monkeypatch.setattr(
        "sys.argv",
        [
            "tabber",
            "--events",
            str(source),
            "--notes-only",
            "--guitar-range",
            "--output",
            str(output),
        ],
    )
    main()
    assert load_events(output / "detected-notes.json") == [notes[1]]
    raw = next((output / "diagnostics").glob("detected-*.json"))
    assert load_events(raw) == notes
    audit = json.loads(next((output / "diagnostics").glob("range-filter-*.json")).read_text())
    assert audit["excluded"][0]["source_index"] == 0


@pytest.mark.parametrize("filename", ["detected-notes.json", "notes.mid"])
def test_notes_only_refuses_overwriting_its_source_even_with_unusual_extension(
    tmp_path, monkeypatch, filename
):
    source = tmp_path / filename
    save_events([Note(0, 1, 64)], source, metadata={"original": "retain"})
    before = source.read_bytes()
    monkeypatch.setattr(
        "sys.argv", ["tabber", "--events", str(source), "--notes-only", "--output", str(tmp_path)]
    )
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 1
    assert source.read_bytes() == before

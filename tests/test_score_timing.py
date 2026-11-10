import io

import pytest

from scripts.audit_score_timing import decoded_notes
from tabber.gp5 import build_song, read_gp5, timing_summary, write_gp5
from tabber.models import FrettedNote, Note


@pytest.mark.parametrize("grid", [16, 32, 64])
def test_saved_score_decoding_measures_timing_from_ticks_and_preserves_ties(grid):
    original = [FrettedNote(Note(0, 2.5, 40), 5, 0), FrettedNote(Note(0.5, 1, 64), 0, 0)]
    stream = io.BytesIO()
    write_gp5(build_song(original, 120, grid), stream)
    stream.seek(0)
    decoded = sorted(decoded_notes(read_gp5(stream)), key=lambda n: n.pitch)
    assert decoded == [Note(0, 2.5, 40), Note(0.5, 1, 64)]


def test_coarse_grid_short_note_extension_is_measured_in_saved_score():
    note = FrettedNote(Note(0.02, 0.04, 64), 0, 0)
    saved = decoded_notes(build_song([note], 120, 16))
    assert saved == [Note(0, 0.125, 64)]
    assert note.note == Note(0.02, 0.04, 64)


def test_timing_summary_reports_movement_and_keeps_chord_notes_distinct():
    notes = [
        FrettedNote(Note(0.06, 0.07, pitch), string, 0) for string, pitch in ((0, 64), (1, 59))
    ]
    report = timing_summary(build_song(notes, 120, 16), notes)
    assert report["note_count"] == 2
    assert report["starts_moved_over_50ms"] == 2
    assert report["maximum_start_shift_ms"] == pytest.approx(60)
    assert report["maximum_end_shift_ms"] == pytest.approx(55)
    finer = timing_summary(build_song(notes, 120, 32), notes)
    assert finer["starts_moved_over_50ms"] == 0


def test_cli_warns_about_score_movement_but_preserves_detected_times(tmp_path, monkeypatch, capsys):
    import json

    from tabber.cli import main
    from tabber.events import load_events, save_events

    source = tmp_path / "source.json"
    notes = [Note(0.06, 0.2, 64)]
    save_events(notes, source)
    output = tmp_path / "result"
    monkeypatch.setattr("sys.argv", ["tabber", "--events", str(source), "--output", str(output)])
    main()
    assert "Timing note: 1 note start moved" in capsys.readouterr().out
    assert load_events(output / "detected-notes.json") == notes
    payload = json.loads((output / "notes.json").read_text())
    assert payload["score_timing"]["starts_moved_over_50ms"] == 1
    assert payload["notes"][0]["note"]["start"] == 0.06

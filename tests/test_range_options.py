import json

import pytest

from tabber.cli import main
from tabber.events import load_events, save_events
from tabber.gp5 import read_gp5, score_events
from tabber.models import Note


def test_explicit_range_filter_keeps_boundaries_and_audits_every_exclusion(
    tmp_path, monkeypatch, capsys
):
    source = tmp_path / "input.json"
    notes = [Note(i / 2, i / 2 + 0.25, pitch, 0.01) for i, pitch in enumerate((39, 40, 88, 89))]
    save_events(notes, source)
    original = source.read_bytes()
    output = tmp_path / "filtered"
    monkeypatch.setattr(
        "sys.argv", ["tabber", "--events", str(source), "--output", str(output), "--guitar-range"]
    )
    main()
    assert source.read_bytes() == original
    assert load_events(output / "detected-notes.json") == [notes[1], notes[2]]
    raw = next((output / "diagnostics").glob("detected-*.json"))
    assert load_events(raw) == notes
    report = json.loads(next((output / "diagnostics").glob("range-filter-*.json")).read_text())
    assert report["source_note_count"] == 4
    assert report["retained_note_count"] == 2
    assert [item["source_index"] for item in report["excluded"]] == [0, 3]
    assert [item["note"]["pitch"] for item in report["excluded"]] == [39, 89]
    assert "Range note: Excluded 2 of 4" in capsys.readouterr().out
    assert len(score_events(read_gp5(output / "tab.gp5"))) == 2


@pytest.mark.parametrize("pitches", [(38, 39), (40, 45, 50, 55, 59, 64, 67)])
def test_filter_failure_preserves_raw_notes_and_existing_tab(tmp_path, monkeypatch, pitches):
    source = tmp_path / "input.json"
    notes = [Note(0, 1, pitch) for pitch in pitches]
    save_events(notes, source)
    output = tmp_path / "previous"
    output.mkdir()
    (output / "tab.gp5").write_bytes(b"previous successful score")
    monkeypatch.setattr(
        "sys.argv", ["tabber", "--events", str(source), "--output", str(output), "--guitar-range"]
    )
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 1
    assert (output / "tab.gp5").read_bytes() == b"previous successful score"
    assert load_events(next((output / "diagnostics").glob("detected-*.json"))) == notes
    report = json.loads(next((output / "diagnostics").glob("range-filter-*.json")).read_text())
    assert report["retained_note_count"] == (0 if pitches == (38, 39) else 7)


def test_wider_span_preserves_a_chord_that_fails_the_default_limit(tmp_path, monkeypatch):
    source = tmp_path / "chord.json"
    notes = [Note(0, 1, pitch) for pitch in (41, 47, 52, 57, 64, 71)]
    save_events(notes, source)
    output = tmp_path / "score"
    arguments = ["tabber", "--events", str(source), "--output", str(output)]
    monkeypatch.setattr("sys.argv", arguments)
    with pytest.raises(SystemExit):
        main()
    monkeypatch.setattr("sys.argv", arguments + ["--max-span", "7"])
    main()
    assert load_events(output / "detected-notes.json") == notes
    assert len(score_events(read_gp5(output / "tab.gp5"))) == len(notes)
    metadata = json.loads((output / "detected-notes.json").read_text())["metadata"]
    assert metadata["max_span"] == 7
    assert metadata["guitar_range_filter_requested"] is False

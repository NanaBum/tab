import json
from pathlib import Path

import guitarpro
import pytest
import soundfile as sf

from tabber.cli import main
from tabber.events import load_events, save_events
from tabber.models import Note
from tabber.rhythm import lead_attacks


def test_cli_rebuilds_gp5_from_events_without_audio_or_ml(tmp_path, monkeypatch):
    events = tmp_path / "edited.json"
    output = tmp_path / "score"
    save_events([Note(0, 0.5, 65)], events)
    monkeypatch.setattr("sys.argv", ["tabber", "--events", str(events), "--output", str(output)])
    main()
    score = guitarpro.parse(str(output / "tab.gp5"))
    track = score.tracks[0]
    note = track.measures[0].voices[0].beats[0].notes[0]
    assert track.strings[note.string - 1].value + note.value == 65


def test_attack_lead_affects_export_but_preserves_raw_events(tmp_path, monkeypatch):
    events, output = tmp_path / "input.json", tmp_path / "adjusted"
    original = [Note(0.081, 0.5, 65, 0.7)]
    save_events(original, events)
    source_bytes = events.read_bytes()
    monkeypatch.setattr(
        "sys.argv",
        ["tabber", "--events", str(events), "--attack-lead-ms", "20", "--output", str(output)],
    )
    main()
    assert events.read_bytes() == source_bytes
    assert load_events(output / "detected-notes.json") == original
    metadata = json.loads((output / "detected-notes.json").read_text())["metadata"]
    audit = metadata["export_attack_adjustment"]
    adjusted = load_events(Path(audit["export_events"]))
    assert adjusted == [Note(0.061, 0.5, 65, 0.7)]
    payload = json.loads((output / "notes.json").read_text())
    assert payload["notes"][0]["note"]["start"] == pytest.approx(0.061)
    song = guitarpro.parse(str(output / "tab.gp5"))
    sounding = [beat for beat in song.tracks[0].measures[0].voices[0].beats if beat.notes]
    assert sounding[0].start == 960
    with pytest.raises(SystemExit):
        main()


def test_cli_saves_detections_if_fingering_fails_and_keeps_old_tab(tmp_path, monkeypatch):
    audio = tmp_path / "input.wav"
    sf.write(audio, [0.0] * 2205, 22050)
    output = tmp_path / "existing"
    output.mkdir()
    old_tab = output / "tab.gp5"
    old_tab.write_bytes(b"previous successful export")
    monkeypatch.setattr("tabber.cli.transcribe", lambda *args: [Note(0, 1, 20)])
    monkeypatch.setattr("sys.argv", ["tabber", str(audio), "--output", str(output)])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 1
    diagnostics = list((output / "diagnostics").glob("detected-*.json"))
    assert len(diagnostics) == 1
    assert load_events(diagnostics[0]) == [Note(0, 1, 20)]
    assert old_tab.read_bytes() == b"previous successful export"


def test_attack_lead_does_not_cross_an_earlier_release():
    notes = [Note(0.01, 0.2, 64), Note(0.21, 0.4, 64), Note(0.31, 0.5, 67)]
    adjusted, limited = lead_attacks(notes, 0.02)
    assert [n.start for n in adjusted] == pytest.approx([0, 0.2, 0.29])
    assert [n.end for n in adjusted] == [n.end for n in notes]
    assert limited == 1

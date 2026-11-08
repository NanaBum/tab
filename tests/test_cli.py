import guitarpro
import pytest
import soundfile as sf

from tabber.cli import main
from tabber.events import load_events, save_events
from tabber.models import Note


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

import queue
import sys
from types import SimpleNamespace

import pytest

pytest.importorskip("tkinter")

from tabber.cli import main
from tabber.events import load_events, save_events
from tabber.gp5 import read_gp5, score_events
from tabber.gui import GUITAR_MODEL, SAVED_NOTES, TabberApp, conversion_command
from tabber.models import Note


def test_guitar_method_uses_its_own_sensitivity_scale(tmp_path):
    command = conversion_command(
        sys.executable,
        tmp_path / "riff.ogg",
        tmp_path / "out",
        method=GUITAR_MODEL,
        tempo=140,
        grid=32,
        confidence=0.5,
        separate=False,
    )
    assert command[command.index("--backend") + 1] == "guitar-gaps"
    assert command[command.index("--onset-threshold") + 1] == "0.3"
    assert "--min-confidence" not in command
    assert "--guitar-range" not in command
    assert "--max-span" not in command


def test_saved_note_rebuild_only_filters_when_explicitly_requested(tmp_path):
    source = tmp_path / "notes.json"
    save_events([Note(0, 1, 39)], source)
    command = conversion_command(
        sys.executable,
        source,
        tmp_path / "out",
        method=SAVED_NOTES,
        tempo=120,
        grid=32,
        confidence=0.7,
        separate=False,
        guitar_range=True,
        max_span=7,
    )
    assert "--guitar-range" in command
    assert command[command.index("--max-span") + 1] == "7"
    assert "--min-confidence" not in command


def test_app_routes_selected_tuning_through_saved_note_rebuild(tmp_path):
    source = tmp_path / "notes.json"
    save_events([Note(0, 1, 38)], source)
    command = conversion_command(
        sys.executable,
        source,
        tmp_path / "out",
        method=SAVED_NOTES,
        tempo=120,
        grid=16,
        confidence=0.5,
        separate=False,
        tuning="drop-d",
    )
    assert command[command.index("--tuning") + 1] == "drop-d"


def test_worker_shows_filter_notice_even_when_export_fails(tmp_path, monkeypatch):
    result = SimpleNamespace(
        returncode=1,
        stdout="Range note: Excluded 2 of 4 detections.\n",
        stderr="Could not transcribe: sustained strings conflict\n",
    )
    monkeypatch.setattr("tabber.gui.subprocess.run", lambda *args, **kwargs: result)
    app = object.__new__(TabberApp)
    app.root = tmp_path
    app.messages = queue.Queue()
    app.worker(["python", "-m", "tabber"], tmp_path / "out")
    success, _, message = app.messages.get_nowait()
    assert success is False
    assert "Range note: Excluded 2 of 4" in message
    assert "sustained strings conflict" in message


def test_app_rebuild_preserves_weak_notes_without_listening_again(tmp_path, monkeypatch):
    source = tmp_path / "detected-notes.json"
    notes = [Note(0, 0.5, 64, 0.1), Note(0.5, 1, 65, 0.2)]
    save_events(notes, source)
    original = source.read_bytes()
    output = tmp_path / "rebuilt"
    command = conversion_command(
        sys.executable,
        source,
        output,
        method=SAVED_NOTES,
        tempo=120,
        grid=32,
        confidence=0.7,
        separate=False,
    )
    monkeypatch.setattr(sys, "argv", ["tabber", *command[3:]])

    def unexpected_listening(*args, **kwargs):
        raise AssertionError("Saved-note rebuild must not transcribe audio")

    monkeypatch.setattr("tabber.cli.transcribe", unexpected_listening)
    main()
    assert source.read_bytes() == original
    assert load_events(output / "detected-notes.json") == notes
    assert len(score_events(read_gp5(output / "tab.gp5"))) == 2


@pytest.mark.parametrize("tempo,separate", [("auto", False), (120, True)])
def test_app_rebuild_requires_explicit_tempo_and_no_audio_separation(tmp_path, tempo, separate):
    with pytest.raises(ValueError):
        conversion_command(
            sys.executable,
            tmp_path / "notes.json",
            tmp_path / "out",
            method=SAVED_NOTES,
            tempo=tempo,
            grid=16,
            confidence=0.5,
            separate=separate,
        )

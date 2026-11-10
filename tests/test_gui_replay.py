import queue
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("tkinter")

from tabber.cli import main
from tabber.events import load_events, save_events
from tabber.gp5 import read_gp5, score_events
from tabber.gui import GUITAR_MODEL, SAVED_NOTES, TabberApp, conversion_command
from tabber.jobs import RunResult
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


def test_app_notes_only_replay_has_no_fret_stretch_request(tmp_path):
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
        notes_only=True,
        max_span=7,
    )
    assert "--notes-only" in command and "--max-span" not in command


@pytest.mark.parametrize(
    "success,tab_exists,preview_exists",
    [(True, False, False), (False, True, False), (False, True, True)],
)
def test_notes_only_or_cancelled_result_never_enables_a_missing_or_partial_tab(
    tmp_path, success, tab_exists, preview_exists
):
    states = {}
    app = object.__new__(TabberApp)
    app.messages = queue.Queue()
    app.messages.put((success, tmp_path, "result"))
    (tmp_path / "notes.mid").write_bytes(b"test output")
    preview = Path("diagnostics/preview-attempt/notes.mid")
    if preview_exists:
        (tmp_path / preview).parent.mkdir(parents=True)
        (tmp_path / preview).write_bytes(b"detected note preview")
    if tab_exists:
        (tmp_path / "tab.gp5").write_bytes(b"cancelled partial file")
    app.window = SimpleNamespace(after=lambda *args: None)
    app.progress = SimpleNamespace(stop=lambda: None)
    app.status = SimpleNamespace(set=lambda value: states.update(message=value))
    for field in ("convert", "stop_conversion", "browse", "open_folder", "open_tab", "open_midi"):
        setattr(
            app,
            field,
            SimpleNamespace(configure=lambda key=field, **kwargs: states.update({key: kwargs})),
        )
    app.poll()
    assert app.running is False
    assert states["open_tab"]["state"] == "disabled"
    assert states["open_midi"]["state"] == ("normal" if success or preview_exists else "disabled")
    assert app.midi_result == (
        Path("notes.mid") if success else preview if preview_exists else None
    )
    assert ("Use Open detected MIDI" in states["message"]) == preview_exists
    assert states["convert"]["state"] == "normal"


@pytest.mark.parametrize("notes_only", [True, False])
def test_output_mode_disables_and_restores_score_only_controls(notes_only):
    states = {}
    app = object.__new__(TabberApp)
    app.notes_only = SimpleNamespace(get=lambda: notes_only)
    for name in ("rhythm_detail", "stretch_control", "convert"):
        setattr(
            app,
            name,
            SimpleNamespace(configure=lambda key=name, **kwargs: states.update({key: kwargs})),
        )
    app.update_output_mode()
    assert states["rhythm_detail"]["state"] == ("disabled" if notes_only else "readonly")
    assert states["stretch_control"]["state"] == ("disabled" if notes_only else "normal")
    assert states["convert"]["text"] == (
        "Detect notes and create MIDI" if notes_only else "Create guitar tab"
    )


def test_worker_shows_filter_notice_even_when_export_fails(tmp_path, monkeypatch):
    def failed_run(*args, log_path, **kwargs):
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(
            "Range note: Excluded 2 of 4 detections.\nCould not transcribe: sustained strings conflict\n",
            encoding="utf-8",
        )
        return RunResult(1)

    monkeypatch.setattr("tabber.gui.run_conversion", failed_run)
    app = object.__new__(TabberApp)
    app.root = tmp_path
    app.messages = queue.Queue()
    app.cancel_event = threading.Event()
    app.worker(["python", "-m", "tabber"], tmp_path / "out")
    success, _, message = app.messages.get_nowait()
    assert success is False
    assert "Range note: Excluded 2 of 4" in message
    assert "sustained strings conflict" in message


def test_cancelled_worker_keeps_partial_tab_but_never_reports_success(tmp_path, monkeypatch):
    output = tmp_path / "out"
    output.mkdir()
    partial = output / "tab.gp5"
    partial.write_bytes(b"partial result")

    def cancelled_run(*args, log_path, **kwargs):
        log_path.write_text("Cancelled by user\n", encoding="utf-8")
        return RunResult(1, True)

    monkeypatch.setattr("tabber.gui.run_conversion", cancelled_run)
    app = object.__new__(TabberApp)
    app.root, app.messages, app.cancel_event = tmp_path, queue.Queue(), threading.Event()
    app.worker(["unused"], output)
    success, path, message = app.messages.get_nowait()
    assert not success and path == output
    assert "not a completed tab" in message
    assert partial.read_bytes() == b"partial result"


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

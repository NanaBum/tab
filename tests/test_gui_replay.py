import sys

import pytest

pytest.importorskip("tkinter")

from tabber.cli import main
from tabber.events import load_events, save_events
from tabber.gp5 import read_gp5, score_events
from tabber.gui import GUITAR_MODEL, SAVED_NOTES, conversion_command
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

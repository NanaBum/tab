import json
from pathlib import Path

import guitarpro
import pytest
import soundfile as sf

from tabber.cli import main
from tabber.events import load_events, save_events
from tabber.gp5 import read_gp5, score_events
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


@pytest.mark.parametrize(
    "metadata,override,expected,source",
    [
        ({"bpm": 87.5}, [], 87.5, "saved"),
        ({"bpm": 87.5}, ["--bpm", "96"], 96, "supplied"),
        ({}, [], 120, "default"),
        ({"bpm": "auto"}, [], 120, "default"),
        ({"tempo_source": "estimated", "tempo_estimate": {"bpm": 108.5}}, [], 108.5, "saved"),
    ],
)
def test_cli_rebuild_uses_valid_saved_tempo_without_an_override(
    tmp_path, monkeypatch, metadata, override, expected, source
):
    events, output = tmp_path / "events.json", tmp_path / "score"
    save_events([Note(0, 0.5, 64)], events, metadata)
    monkeypatch.setattr(
        "sys.argv", ["tabber", "--events", str(events), "--output", str(output), *override]
    )

    main()

    info = json.loads((output / "detected-notes.json").read_text())["metadata"]
    assert info["bpm"] == expected
    assert info["tempo_source"] == source
    assert guitarpro.parse(str(output / "tab.gp5")).tempo == int(expected + 0.5)


@pytest.mark.parametrize(
    "saved,override,grid,attack_tick",
    [
        (32, [], 32, 1080),
        (32, ["--grid", "64"], 64, 1140),
        ("32", [], 16, 1200),
        (None, [], 16, 1200),
    ],
)
def test_cli_rebuild_applies_saved_or_explicit_score_grid(
    tmp_path, monkeypatch, saved, override, grid, attack_tick
):
    events, output = tmp_path / "events.json", tmp_path / "score"
    original = [Note(0.082, 0.5, 64)]
    save_events(original, events, {} if saved is None else {"score_grid": saved})
    monkeypatch.setattr(
        "sys.argv", ["tabber", "--events", str(events), "--output", str(output), *override]
    )

    main()

    assert load_events(output / "detected-notes.json") == original
    assert (
        json.loads((output / "detected-notes.json").read_text())["metadata"]["score_grid"] == grid
    )
    assert score_events(read_gp5(output / "tab.gp5"))[0][0] == attack_tick


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
    monkeypatch.setattr(
        "sys.argv", ["tabber", str(audio), "--output", str(output), "--bpm", "87.5"]
    )
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 1
    diagnostics = list((output / "diagnostics").glob("detected-*.json"))
    assert len(diagnostics) == 1
    assert load_events(diagnostics[0]) == [Note(0, 1, 20)]
    metadata = json.loads(diagnostics[0].read_text())["metadata"]
    assert metadata["bpm"] == 87.5
    assert metadata["tempo_source"] == "supplied"
    assert old_tab.read_bytes() == b"previous successful export"


def test_attack_lead_does_not_cross_an_earlier_release():
    notes = [Note(0.01, 0.2, 64), Note(0.21, 0.4, 64), Note(0.31, 0.5, 67)]
    adjusted, limited = lead_attacks(notes, 0.02)
    assert [n.start for n in adjusted] == pytest.approx([0, 0.2, 0.29])
    assert [n.end for n in adjusted] == [n.end for n in notes]
    assert limited == 1


@pytest.mark.parametrize("notes_only", [False, True])
def test_empty_guitar_result_saves_diagnostics_and_suggests_basic_pitch(
    tmp_path, monkeypatch, capsys, notes_only
):
    source, output = tmp_path / "riff.wav", tmp_path / "results"
    sf.write(source, [0.0, 0.1] * 4000, 16000)
    monkeypatch.setattr("tabber.cli.transcribe", lambda *args, **kwargs: [])
    argv = ["tabber", str(source), "--backend", "guitar-gaps", "--output", str(output)]
    monkeypatch.setattr("sys.argv", argv + (["--notes-only"] if notes_only else []))
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 1
    assert "Try Basic Pitch on the same audio" in capsys.readouterr().err
    [diagnostic] = list((output / "diagnostics").glob("detected-*.json"))
    assert load_events(diagnostic) == []
    assert not (output / "tab.gp5").exists()
    assert not (output / "notes.mid").exists()


@pytest.mark.parametrize("empty_first_pass", [True, False])
def test_guitar_retry_only_runs_after_an_empty_first_pass(tmp_path, monkeypatch, empty_first_pass):
    source, output = tmp_path / "riff.wav", tmp_path / "results"
    sf.write(source, [0.0, 0.1] * 4000, 16000)
    notes = [Note(0.1, 0.3, 64)]
    monkeypatch.setattr(
        "tabber.cli.transcribe", lambda *args, **kwargs: [] if empty_first_pass else notes
    )
    calls = []

    def retry(path, **settings):
        calls.append((path, settings))
        assert len(list((output / "diagnostics").glob("detected-*.json"))) == 1
        return notes

    monkeypatch.setattr("tabber.guitar_gaps.transcribe_gaps", retry)
    monkeypatch.setattr(
        "sys.argv",
        [
            "tabber",
            str(source),
            "--backend",
            "guitar-gaps",
            "--guitar-retry-empty",
            "--onset-threshold",
            "0.24",
            "--notes-only",
            "--output",
            str(output),
        ],
    )
    main()
    [first] = list((output / "diagnostics").glob("detected-*.json"))
    retry_events = list((output / "diagnostics").glob("retry-*.json"))
    assert load_events(output / "detected-notes.json") == notes
    if empty_first_pass:
        assert calls == [
            (
                source.resolve(),
                {
                    "checkpoint": None,
                    "onset_threshold": 0.24,
                    "input_gain": 0.5,
                },
            )
        ]
        assert load_events(first) == []
        [second] = retry_events
        assert load_events(second) == notes
    else:
        assert not calls and not retry_events
        assert load_events(first) == notes

import json
from pathlib import Path

import guitarpro
import mido
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
    "saved,override,expected,ticks",
    [
        ("6/8", [], "6/8", 2880),
        ("6/8", ["--meter", "7/8"], "7/8", 3360),
        ("17/16", [], "17/16", 4080),
        ("6/7", [], "4/4", 3840),
    ],
)
def test_meter_round_trip_keeps_attacks_and_barline_ties(
    tmp_path, monkeypatch, saved, override, expected, ticks
):
    source, output = tmp_path / "events.json", tmp_path / "score"
    original = [Note(1, 2.5, 64)]
    save_events(original, source, {"score_meter": saved})
    monkeypatch.setattr(
        "sys.argv", ["tabber", "--events", str(source), "--output", str(output), *override]
    )

    main()

    song = read_gp5(output / "tab.gp5")
    assert [header.start for header in song.measureHeaders] == [960, 960 + ticks]
    assert [header.length for header in song.measureHeaders] == [ticks, ticks]
    assert all(
        f"{header.timeSignature.numerator}/{header.timeSignature.denominator.value}" == expected
        for header in song.measureHeaders
    )
    assert [(start, end) for start, end, _, _ in score_events(song)] == [(2880, 5760)]
    midi_meters = [
        f"{msg.numerator}/{msg.denominator}"
        for msg in mido.MidiFile(output / "notes.mid").tracks[0]
        if msg.type == "time_signature"
    ]
    assert midi_meters == ([expected] if expected != "4/4" else [])
    assert load_events(output / "detected-notes.json") == original
    for path in (output / "detected-notes.json", *output.glob("diagnostics/detected-*.json")):
        assert json.loads(path.read_text())["metadata"]["score_meter"] == expected


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


def test_cli_retries_fingering_when_attacks_share_a_score_cell(tmp_path, monkeypatch):
    source, output = tmp_path / "events.json", tmp_path / "score"
    events = [Note(0, 0.04, 64), Note(0.05, 0.1, 65)]
    save_events(events, source)
    monkeypatch.setattr("sys.argv", ["tabber", "--events", str(source), "--output", str(output)])

    main()

    assert load_events(source) == load_events(output / "detected-notes.json") == events
    metadata = json.loads((output / "detected-notes.json").read_text())["metadata"]
    assert metadata["score_grid_fingering_retry"] is True
    song = read_gp5(output / "tab.gp5")
    attacks = score_events(song)
    assert [first for first, _, _, _ in attacks] == [960, 960]
    assert len({string for _, _, string, _ in attacks}) == 2
    assert sorted(
        song.tracks[0].strings[string - 1].value + fret for _, _, string, fret in attacks
    ) == [64, 65]


def test_cli_keeps_grid_collision_if_there_is_only_one_eligible_string(
    tmp_path, monkeypatch, capsys
):
    source, output = tmp_path / "events.json", tmp_path / "score"
    events = [Note(0, 0.04, 40), Note(0.05, 0.1, 41)]
    save_events(events, source)
    monkeypatch.setattr("sys.argv", ["tabber", "--events", str(source), "--output", str(output)])

    with pytest.raises(SystemExit) as error:
        main()

    assert error.value.code == 1
    assert "collide on the GP5" in capsys.readouterr().err
    assert not (output / "tab.gp5").exists()
    [saved] = (output / "diagnostics").glob("detected-*.json")
    assert load_events(saved) == events


@pytest.mark.parametrize("start,grid", [(0.05, 32), (0.023, 64)])
def test_cli_can_retry_a_finer_grid_without_changing_detections(
    tmp_path, monkeypatch, capsys, start, grid
):
    source, output = tmp_path / "events.json", tmp_path / "score"
    events = [Note(0, 0.02, 40), Note(start, 0.1, 41)]
    save_events(events, source)
    original = source.read_bytes()
    monkeypatch.setattr(
        "sys.argv",
        ["tabber", "--events", str(source), "--output", str(output), "--retry-finer-grid"],
    )

    main()

    assert source.read_bytes() == original
    [diagnostic] = (output / "diagnostics").glob("detected-*.json")
    for saved in (diagnostic, output / "detected-notes.json"):
        assert load_events(saved) == events
        metadata = json.loads(saved.read_text())["metadata"]
        assert metadata["score_grid"] == grid
        assert metadata["finer_grid_retry"] == {"requested": 16, "used": grid}
    song = read_gp5(output / "tab.gp5")
    assert [(first, string, fret) for first, _, string, fret in score_events(song)] == [
        (960, 6, 0),
        (960 + 3840 // grid, 6, 1),
    ]
    assert f"Used a 1/{grid} grid after a collision at 1/16" in capsys.readouterr().out


@pytest.mark.parametrize("simultaneous", [False, True])
def test_overlap_recovery_preserves_original_detections(tmp_path, monkeypatch, simultaneous):
    source, output = tmp_path / "events.json", tmp_path / "score"
    events = [
        Note(0, 1, 40, 0.8),
        Note(0 if simultaneous else 0.5, 1, 41, 0.2 if simultaneous else 1.0),
    ]
    save_events(events, source)
    monkeypatch.setattr("sys.argv", ["tabber", "--events", str(source), "--output", str(output)])

    main()

    assert load_events(output / "detected-notes.json") == events
    song = read_gp5(output / "tab.gp5")
    assert score_events(song) == (
        [(960, 2880, 6, 0)] if simultaneous else [(960, 1920, 6, 0), (1920, 2880, 6, 1)]
    )
    [audit] = (output / "diagnostics").glob("overlap-recovery-*.json")
    edits = json.loads(audit.read_text())
    if simultaneous:
        assert edits["omitted"][0]["source_index"] == 1
        assert edits["shortened"] == []
    else:
        assert edits["shortened"][0]["source_index"] == 0
        assert edits["shortened"][0]["new_end"] == 0.5
        assert edits["omitted"] == []


@pytest.mark.parametrize("strict", [False, True])
def test_finer_grid_can_recover_a_collision_at_64(tmp_path, monkeypatch, strict):
    source, output = tmp_path / "events.json", tmp_path / "score"
    events = [Note(0, 0.003, 40, 0.9), Note(0.005, 0.1, 41, 0.1)]
    save_events(events, source)
    args = ["tabber", "--events", str(source), "--output", str(output), "--retry-finer-grid"]
    monkeypatch.setattr("sys.argv", args + (["--strict-overlaps"] if strict else []))

    if strict:
        with pytest.raises(SystemExit):
            main()
        assert not (output / "tab.gp5").exists()
        return

    main()

    assert load_events(output / "detected-notes.json") == events
    metadata = json.loads((output / "detected-notes.json").read_text())["metadata"]
    assert metadata["score_grid"] == 64
    audit = json.loads(Path(metadata["overlap_recovery"]["audit"]).read_text())
    assert audit["score_grid"] == 64
    assert audit["omitted"][0]["source_index"] == 1
    assert score_events(read_gp5(output / "tab.gp5")) == [(960, 1020, 6, 0)]


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

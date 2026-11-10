import json

import numpy as np
import pytest
import soundfile as sf

from tabber.cli import main
from tabber.events import load_events
from tabber.gp5 import read_gp5, score_events
from tabber.transcribe import baseline_frequency_floor, transcribe


def audio_sequence(path, pitches):
    rate = 22050
    t = np.arange(int(rate * 0.4)) / rate
    envelope = np.minimum(t / 0.01, 1) * np.minimum((0.4 - t) / 0.03, 1)
    parts = []
    for pitch in pitches:
        parts.extend(
            (
                0.3 * np.sin(2 * np.pi * 440 * 2 ** ((pitch - 69) / 12) * t) * envelope,
                np.zeros(int(rate * 0.1)),
            )
        )
    sf.write(path, np.concatenate(parts), rate)


def test_drop_d_band_detects_low_d_without_changing_default_band(tmp_path):
    path = tmp_path / "tones.wav"
    audio_sequence(path, [38, 40, 45, 50, 55, 59, 64])
    original = transcribe(path)
    assert [n.pitch for n in original] == [40, 45, 50, 55, 59, 64]
    assert transcribe(path, baseline_min_pitch=40) == original
    assert [n.pitch for n in transcribe(path, baseline_min_pitch=38)] == [
        38,
        40,
        45,
        50,
        55,
        59,
        64,
    ]


@pytest.mark.parametrize("pitch", [24, 36, 38])
def test_lower_tunings_have_enough_cycles_for_their_open_string(tmp_path, pitch):
    path = tmp_path / "tone.wav"
    audio_sequence(path, [pitch])
    assert [n.pitch for n in transcribe(path, baseline_min_pitch=pitch)] == [pitch]


def test_cli_drop_d_audio_preserves_low_note_and_logs_search_band(tmp_path, monkeypatch, capsys):
    source = tmp_path / "riff.wav"
    audio_sequence(source, [38, 45])
    before = source.read_bytes()
    output = tmp_path / "out"
    monkeypatch.setattr(
        "sys.argv", ["tabber", str(source), "--tuning", "drop-d", "--output", str(output)]
    )
    main()
    assert source.read_bytes() == before
    assert [n.pitch for n in load_events(output / "detected-notes.json")] == [38, 45]
    metadata = json.loads((output / "detected-notes.json").read_text())["metadata"]
    assert metadata["baseline_minimum_search_hz"] == pytest.approx(71.32617550580561)
    assert "71.3 Hz" in capsys.readouterr().out
    song = read_gp5(output / "tab.gp5")
    assert score_events(song)[0][2:] == (6, 0)


def test_standard_and_eb_keep_original_search_floor():
    assert (
        baseline_frequency_floor()
        == baseline_frequency_floor(40)
        == baseline_frequency_floor(39)
        == 75
    )


@pytest.mark.parametrize("pitch", [-1, 128, 38.5, True])
def test_invalid_band_input_fails_before_reading_audio(tmp_path, pitch):
    with pytest.raises(ValueError, match="integer MIDI"):
        transcribe(tmp_path / "absent.wav", baseline_min_pitch=pitch)


def test_baseline_band_cannot_silently_modify_an_ml_backend(tmp_path):
    with pytest.raises(ValueError, match="only to the simple"):
        transcribe(tmp_path / "absent.wav", "basic-pitch", baseline_min_pitch=38)

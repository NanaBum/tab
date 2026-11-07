import numpy as np
import pytest
import soundfile as sf

from tabber.tempo import TapTempo, estimate_tempo, parse_bpm


def test_tempo_argument_accepts_auto_and_finite_bpm():
    assert parse_bpm(" auto ") == "auto"
    assert parse_bpm("129.5") == 129.5


@pytest.mark.parametrize("value", ["0", "-120", "1000", "nan", "inf", "song"])
def test_invalid_tempo_argument_is_rejected(value):
    with pytest.raises(ValueError):
        parse_bpm(value)


def test_tempo_rejects_short_or_silent_audio_before_loading_optional_dependencies(tmp_path):
    path = tmp_path / "audio.wav"
    sf.write(path, np.ones(22050) * 0.1, 22050)
    with pytest.raises(ValueError, match="2 seconds"):
        estimate_tempo(path)
    sf.write(path, np.zeros(3 * 22050), 22050)
    with pytest.raises(ValueError, match="audible"):
        estimate_tempo(path)


def test_tap_tempo_smooths_intervals_and_resets_after_a_pause():
    taps = TapTempo()
    for timestamp in (0, 0.5, 1):
        assert taps.tap(timestamp) is None
    assert taps.tap(1.5) == 120
    assert taps.tap(1.51) is None
    assert taps.tap(2) == 120
    assert taps.tap(10) is None
    assert taps.times == [10]

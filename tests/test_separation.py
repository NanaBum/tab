from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from tabber.separate import saved_guitar_stem, separate_guitar


def test_mono_input_is_materialized_as_stereo_without_changing_original(tmp_path, monkeypatch):
    path = tmp_path / "mono.wav"
    sf.write(path, np.linspace(-0.5, 0.5, 1000), 22050)
    original = path.read_bytes()
    output = tmp_path / "stems"

    def run(command, **kwargs):
        normalized = Path(command[-1])
        audio, rate = sf.read(normalized, always_2d=True)
        assert audio.shape == (1000, 2)
        assert np.array_equal(audio[:, 0], audio[:, 1])
        target = output / "htdemucs_6s/mono/guitar.wav"
        target.parent.mkdir(parents=True)
        sf.write(target, audio, rate)

    monkeypatch.setattr("tabber.separate.subprocess.run", run)
    result = separate_guitar(path, output)
    assert result.is_file()
    assert saved_guitar_stem(output) == result
    assert path.read_bytes() == original
    assert not list(output.glob("input-*"))


def test_partial_or_external_guitar_stem_is_not_reused(tmp_path):
    output = tmp_path / "stems"
    output.mkdir()
    (output / "guitar.wav").touch()
    (tmp_path / "guitar.wav").touch()
    assert saved_guitar_stem(output) is None
    (output / "guitar-stem.json").write_text('"../guitar.wav"', encoding="utf-8")
    assert saved_guitar_stem(output) is None


def test_silent_audio_is_rejected_before_separation(tmp_path):
    path = tmp_path / "silence.wav"
    sf.write(path, np.zeros(1000), 22050)
    with pytest.raises(ValueError, match="audible"):
        separate_guitar(path, tmp_path / "stems")
    assert not (tmp_path / "stems").exists()

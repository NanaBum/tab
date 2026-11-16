import subprocess
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from tabber.separate import separate_guitar


def test_mono_input_is_materialized_as_stereo_without_changing_original(tmp_path, monkeypatch):
    path = tmp_path / "mono.wav"
    sf.write(path, np.linspace(-0.5, 0.5, 1000), 22050)
    original = path.read_bytes()
    output = tmp_path / "stems"

    def run(command, **kwargs):
        assert command[1:4] == ["-I", "-m", "demucs"]
        normalized = Path(command[-1])
        audio, rate = sf.read(normalized, always_2d=True)
        assert audio.shape == (1000, 2)
        assert np.array_equal(audio[:, 0], audio[:, 1])
        staging = Path(command[command.index("-o") + 1])
        target = staging / "htdemucs_6s/mono/guitar.wav"
        target.parent.mkdir(parents=True)
        sf.write(target, audio, rate)
        sf.write(target.with_name("no_guitar.wav"), audio, rate)

    monkeypatch.setattr("tabber.separate.subprocess.run", run)
    result = separate_guitar(path, output)
    assert result.is_file()
    assert path.read_bytes() == original
    assert not list(output.glob("input-*"))


def test_silent_audio_is_rejected_before_separation(tmp_path):
    path = tmp_path / "silence.wav"
    sf.write(path, np.zeros(1000), 22050)
    with pytest.raises(ValueError, match="audible"):
        separate_guitar(path, tmp_path / "stems")
    assert not (tmp_path / "stems").exists()


def test_failed_separator_explains_how_to_retry(tmp_path, monkeypatch):
    path = tmp_path / "mix.wav"
    sf.write(path, np.full(1000, 0.2), 22050)
    original = path.read_bytes()
    output = tmp_path / "stems"

    def fail(command, **kwargs):
        raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr("tabber.separate.subprocess.run", fail)
    with pytest.raises(RuntimeError, match="turn off separation and retry"):
        separate_guitar(path, output)
    assert path.read_bytes() == original
    assert not list(output.glob("input-*"))


def test_separation_requires_fresh_stems_before_replacing_prior_results(tmp_path, monkeypatch):
    path = tmp_path / "mix.wav"
    sf.write(path, np.full(1000, 0.2), 22050)
    output = tmp_path / "stems"
    stem = output / "htdemucs_6s/mix/guitar.wav"
    stem.parent.mkdir(parents=True)
    backing = stem.with_name("no_guitar.wav")
    stem.write_bytes(b"previous guitar")
    backing.write_bytes(b"previous backing")

    def partial(command, **kwargs):
        staging = Path(command[command.index("-o") + 1])
        fresh = staging / "htdemucs_6s/mix/no_guitar.wav"
        fresh.parent.mkdir(parents=True)
        fresh.write_bytes(b"new backing only")

    monkeypatch.setattr("tabber.separate.subprocess.run", partial)
    with pytest.raises(ValueError, match="expected guitar and backing stems"):
        separate_guitar(path, output)

    assert stem.read_bytes() == b"previous guitar"
    assert backing.read_bytes() == b"previous backing"
    assert not list(output.glob("input-*"))

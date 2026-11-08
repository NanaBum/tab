from types import SimpleNamespace

import numpy as np
import pytest
import soundfile as sf

from tabber.audio import inspect_audio, prepare_audio


def test_supported_wav_is_not_copied_or_sent_to_a_decoder(tmp_path, monkeypatch):
    path = tmp_path / "source.wav"
    sf.write(path, np.sin(np.arange(1000) * 0.1) * 0.1, 22050, subtype="FLOAT")
    original = path.read_bytes()

    def unexpected_decoder():
        raise AssertionError("WAV must not require a codec environment")

    monkeypatch.setattr("tabber.audio.find_ffmpeg", unexpected_decoder)
    assert prepare_audio(path, tmp_path / "diagnostics") == path.resolve()
    assert path.read_bytes() == original
    assert not (tmp_path / "diagnostics").exists()


def test_unsupported_source_decodes_to_a_new_file_and_preserves_original(tmp_path, monkeypatch):
    source = tmp_path / "recording.m4a"
    source.write_bytes(b"test encoded audio")
    monkeypatch.setattr("tabber.audio.find_ffmpeg", lambda: "test-ffmpeg")

    def decode(command, **kwargs):
        assert command[command.index("-i") + 1] == str(source.resolve())
        sf.write(command[-1], np.ones(100) * 0.1, 22050, subtype="FLOAT")
        return SimpleNamespace(returncode=0, stderr="")

    monkeypatch.setattr("tabber.audio.subprocess.run", decode)
    converted = prepare_audio(source, tmp_path / "diagnostics")
    assert source.read_bytes() == b"test encoded audio"
    assert converted != source and converted.exists()
    assert inspect_audio(converted)["sample_rate"] == 22050


def test_failed_codec_removes_partial_copy_and_leaves_source_untouched(tmp_path, monkeypatch):
    source = tmp_path / "bad.m4a"
    source.write_bytes(b"not audio")
    monkeypatch.setattr("tabber.audio.find_ffmpeg", lambda: "test-ffmpeg")
    monkeypatch.setattr(
        "tabber.audio.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1, stderr="bad stream"),
    )
    output = tmp_path / "diagnostics"
    with pytest.raises(ValueError, match="bad stream"):
        prepare_audio(source, output)
    assert not list(output.iterdir())
    assert source.read_bytes() == b"not audio"


def test_input_checks_report_low_level_and_stereo_cancellation_without_changes(tmp_path):
    path = tmp_path / "quiet.wav"
    mono = np.sin(np.arange(70000) * 0.1) * 0.001
    sf.write(path, np.column_stack((mono, -mono)), 22050, subtype="FLOAT")
    before = path.read_bytes()
    report = inspect_audio(path)
    assert len(report["warnings"]) == 2
    assert report["peak"] == pytest.approx(0.001)
    assert report["mono_rms"] == 0
    assert report["seconds"] == pytest.approx(70000 / 22050)
    assert path.read_bytes() == before


def test_invalid_samples_fail_before_transcription(tmp_path):
    path = tmp_path / "invalid.wav"
    sf.write(path, np.array([0, np.nan, 0.2]), 22050, subtype="FLOAT")
    with pytest.raises(ValueError, match="non-finite"):
        inspect_audio(path)


def test_cli_saves_audio_checks_and_warns_even_when_no_notes_are_detected(
    tmp_path, monkeypatch, capsys
):
    import json

    from tabber.cli import main

    audio = tmp_path / "quiet.wav"
    sf.write(audio, np.zeros(1000), 22050)
    output = tmp_path / "run"
    monkeypatch.setattr("tabber.cli.transcribe", lambda *args: [])
    monkeypatch.setattr("sys.argv", ["tabber", str(audio), "--output", str(output)])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 1
    assert "Audio note: Recording level is very low" in capsys.readouterr().out
    check = next((output / "diagnostics").glob("audio-*.json"))
    assert json.loads(check.read_text())["peak"] == 0
    assert not (output / "tab.gp5").exists()

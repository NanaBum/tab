import hashlib
import sys
from types import SimpleNamespace

import numpy as np
import pytest

from tabber.guitar_gaps import _load_model, _make_segments, _stitch_segments, decode_gaps
from tabber.models import Note
from tabber.transcribe import transcribe


def test_window_stitching_retains_boundaries_without_duplicate_overlap():
    # 8-frame windows overlap by 4; centered analysis adds an endpoint.
    activations = np.array([np.arange(i, i + 9) for i in (0, 4, 8)])[:, :, None]
    assert _stitch_segments(activations)[:, 0].tolist() == list(range(16))
    assert _stitch_segments(activations[:1])[:, 0].tolist() == list(range(9))


def test_audio_windows_pad_tail_and_keep_half_window_overlap():
    windows = _make_segments(np.arange(11.0), segment_samples=8)
    assert windows.tolist() == [list(range(8)), list(range(4, 11)) + [0], [8, 9, 10, 0, 0, 0, 0, 0]]
    with pytest.raises(ValueError, match="finite"):
        _make_segments(np.array([np.nan]))


def test_unverified_checkpoint_is_rejected_before_loading_optional_code(tmp_path, monkeypatch):
    checkpoint = tmp_path / "untrusted.pth"
    checkpoint.write_bytes(b"not the published checkpoint")
    monkeypatch.setitem(sys.modules, "torch", None)
    with pytest.raises(ValueError, match="checksum"):
        _load_model(checkpoint)


def test_unverified_release_is_rejected_before_loading_optional_code(tmp_path, monkeypatch):
    checkpoint, release = tmp_path / "base.pth", tmp_path / "release.pt"
    checkpoint.write_bytes(b"known base")
    release.write_bytes(b"unexpected release")
    monkeypatch.setattr(
        "tabber.guitar_gaps.CHECKPOINT_SHA256", hashlib.sha256(checkpoint.read_bytes()).hexdigest()
    )
    monkeypatch.setitem(sys.modules, "torch", None)
    with pytest.raises(ValueError, match="release checkpoint checksum"):
        _load_model(checkpoint, release)


def test_guitar_route_keeps_low_activations_and_uses_attack_threshold(monkeypatch, tmp_path):
    notes = [Note(0, 0.1, 64, 0.05)]
    calls = []

    def infer(path, **kwargs):
        calls.append((path, kwargs))
        return notes

    monkeypatch.setattr("tabber.guitar_gaps.transcribe_gaps", infer)
    source = tmp_path / "riff.ogg"
    assert transcribe(source, "guitar-gaps", guitar_onset=0.2) == notes
    assert calls == [(source, {"checkpoint": None, "onset_threshold": 0.2})]
    with pytest.raises(ValueError, match="onset-threshold"):
        transcribe(source, "guitar-gaps", min_confidence=0.7)


def test_redecode_keeps_shared_activations_and_applies_requested_threshold(monkeypatch):
    class Processor:
        def __init__(self, _rate, _pitches, threshold, *_other_thresholds):
            self.threshold = threshold

        def output_dict_to_midi_events(self, values):
            assert "onset_output" not in values
            values["onset_output"] = None
            return (
                [{"onset_time": 0, "offset_time": 0.08, "midi_note": 60}]
                if self.threshold < 0.4
                else [],
                None,
            )

    monkeypatch.setitem(
        sys.modules,
        "piano_transcription_inference.utilities",
        SimpleNamespace(RegressionPostProcessor=Processor),
    )
    output = {"reg_onset_output": np.full((10, 88), 0.35)}
    assert decode_gaps(output, 0.1, onset_threshold=0.3) == [Note(0, 0.08, 60, 0.35)]
    assert decode_gaps(output, 0.1, onset_threshold=0.42) == []
    assert set(output) == {"reg_onset_output"}

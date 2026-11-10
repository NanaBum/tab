import json

import pytest

from scripts.evaluate_onset_excerpts import load_partition, reuse_inputs
from tabber.media import sha256_file


def test_benchmark_refuses_test_song_that_also_appears_in_training(tmp_path):
    manifest = tmp_path / "manifest.json"
    common = {"song_id": "song", "original_recording_sha256": "a", "decoded_audio_sha256": "b"}
    manifest.write_text(
        json.dumps(
            {
                "format": "tabber-onset-excerpts",
                "schema_version": 1,
                "excerpts": [
                    {**common, "split": "train"},
                    {**common, "split": "test"},
                ],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="multiple splits"):
        load_partition(manifest, "test")


def test_reused_stem_must_match_the_reported_bytes(tmp_path):
    stem = tmp_path / "excerpt-001/stems/htdemucs_6s/audio/guitar.wav"
    stem.parent.mkdir(parents=True)
    stem.write_bytes(b"original stem")
    row = {"song_id": "song", "audio_sha256": "audio", "labels_sha256": "labels"}
    report = {
        "manifest_sha256": "manifest",
        "split": "test",
        "separate_guitar": True,
        "excerpts": [{**row, "detector_input_sha256": sha256_file(stem)}],
    }
    (tmp_path / "report.json").write_text(json.dumps(report), encoding="utf-8")
    excerpts = [(row, None, [])]
    assert reuse_inputs(tmp_path, "manifest", "test", excerpts) == [stem]
    stem.write_bytes(b"different stem")
    with pytest.raises(ValueError, match="verification"):
        reuse_inputs(tmp_path, "manifest", "test", excerpts)

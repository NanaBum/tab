import json

import numpy as np
import pytest
import soundfile as sf

from scripts.prepare_training_excerpts import prepare
from tabber.events import save_events
from tabber.media import sha256_file
from tabber.models import Note


def test_same_song_cannot_enter_both_splits_or_leave_partial_output(tmp_path):
    def save(path, contents):
        path.write_text(json.dumps(contents), encoding="utf-8")

    pair = tmp_path / "song/pair/pair.json"
    pair.parent.mkdir(parents=True)
    audio = pair.parent / "recording.wav"
    sf.write(audio, np.zeros(8000), 8000, subtype="FLOAT")
    save(
        pair,
        {
            "format": "tabber-training-pair",
            "schema_version": 1,
            "song_id": "song",
            "roles": {"audio_original": audio.name},
            "assets": [
                {"path": audio.name, "bytes": audio.stat().st_size, "sha256": sha256_file(audio)}
            ],
        },
    )
    reference = pair.parent.parent / "labels/gp7-track-1.json"
    save_events(
        [Note(0.25, 0.5, 60)],
        reference,
        {"source_pair_sha256": sha256_file(pair), "score_track": {"track": 1}},
    )
    evidence = tmp_path / "evidence.json"
    save(
        evidence,
        {
            "source_pair_sha256": sha256_file(pair),
            "audio_sha256": sha256_file(audio),
            "calibrated_shift_seconds": 0,
            "windows": [{"window_seconds": [0, 1], "calibrated_flux": 1, "control_max_flux": 0}],
            "references": [{"sha256": sha256_file(reference)}],
        },
    )
    row = {
        "song_id": "song",
        "audio": str(audio),
        "pair": str(pair),
        "evidence": str(evidence),
        "tracks": [1],
        "score_shift_seconds": 0,
        "score_scale": 1,
        "windows": [[0, 1]],
    }
    plan = tmp_path / "plan.json"
    save(
        plan,
        {
            "format": "tabber-excerpt-plan",
            "schema_version": 1,
            "label_status": "weak_score_candidates",
            "rows": [dict(row, split="train"), dict(row, split="validation")],
        },
    )
    output = tmp_path / "output"
    with pytest.raises(ValueError, match="multiple splits"):
        prepare(plan, output, tmp_path)
    assert not output.exists()

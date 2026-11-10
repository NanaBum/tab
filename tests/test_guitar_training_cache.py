import importlib
import json
from pathlib import Path

import pytest

from tabber.media import sha256_file


def test_completed_cache_reuses_identical_entry_and_rejects_changed_scores(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    module = importlib.import_module("prepare_guitar_training_cache")
    dest = tmp_path / "train-001"
    stem = dest / module.STEM_PATH
    stem.parent.mkdir(parents=True)
    stem.write_bytes(b"saved stem")
    scores = dest / "activations.npz"
    scores.write_bytes(b"saved scores")
    identity = {"audio_sha256": "audio", "labels_sha256": "labels", "split": "train"}
    entry = {
        **identity,
        "stem_sha256": sha256_file(stem),
        "activations_sha256": sha256_file(scores),
    }
    (dest / "entry.json").write_text(json.dumps(entry), encoding="utf-8")
    monkeypatch.setattr(
        module, "separate_guitar", lambda *args: pytest.fail("Valid cache should be reused")
    )
    assert module.prepare_clip(tmp_path / "unused.wav", dest, identity) == entry
    scores.write_bytes(b"different scores")
    with pytest.raises(ValueError, match="Cached files do not match"):
        module.prepare_clip(tmp_path / "unused.wav", dest, identity)

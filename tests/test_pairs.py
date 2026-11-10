import copy
import json

import pytest

from scripts.evaluate_pairs import main
from tabber.events import save_events
from tabber.models import Note
from tabber.pairs import evaluate_manifest, file_hash, inspect_manifest


def make_manifest(tmp_path):
    audio = tmp_path / "recording.wav"
    audio.write_bytes(b"synthetic hash-only audio fixture; not decoded by evaluator")
    reference, prediction = tmp_path / "reference.json", tmp_path / "prediction.json"
    save_events([Note(0.2, 0.5, 64), Note(0.6, 0.9, 66)], reference)
    save_events([Note(0.1, 0.4, 64), Note(0.5, 0.8, 66), Note(1, 1.2, 67)], prediction)
    row = {
        "pair_id": "take-1",
        "song_id": "song-1",
        "split": "development",
        "model_id": "model-1",
        "model_provenance": "synthetic fixed settings",
        "reference_quality": "candidate",
        "alignment_review": "candidate",
    }
    for kind, path in (("audio", audio), ("reference", reference), ("prediction", prediction)):
        row[kind] = {
            "path": path.name,
            "sha256": file_hash(path),
            "source": "generated test fixture",
            "permission_note": "synthetic test",
        }
    payload = {"format": "tabber-evaluation-pairs", "schema_version": 1, "pairs": [row]}
    path = tmp_path / "pairs.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path, payload


def write(path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_raw_and_shifted_scores_preserve_extras_metadata_and_source_bytes(tmp_path):
    path, payload = make_manifest(tmp_path)
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    report = evaluate_manifest(path, max_shift=0.2)
    total = report["aggregates"][0]
    assert total["raw"]["onsets"]["matched_notes"] == 0
    assert total["shifted"]["onsets"] == {
        "reference_notes": 2,
        "predicted_notes": 3,
        "matched_notes": 2,
        "precision": 2 / 3,
        "recall": 1,
        "f1": 0.8,
    }
    assert report["pairs"][0]["manifest_entry"] == payload["pairs"][0]
    assert report["pairs"][0]["comparison"]["prediction_shift_seconds"] == pytest.approx(0.1)
    assert before == {p.name: p.read_bytes() for p in tmp_path.iterdir()}


@pytest.mark.parametrize("kind", ["audio", "reference", "prediction"])
def test_changed_asset_fails_instead_of_silently_omitting_pair(tmp_path, kind):
    path, payload = make_manifest(tmp_path)
    (tmp_path / payload["pairs"][0][kind]["path"]).write_bytes(b"changed")
    with pytest.raises(ValueError, match=f"changed {kind}"):
        evaluate_manifest(path)


def test_song_groups_cannot_cross_splits_even_with_different_capitalization(tmp_path):
    path, payload = make_manifest(tmp_path)
    second = copy.deepcopy(payload["pairs"][0])
    second.update(pair_id="take-2", song_id=" SONG-1 ", split="test")
    payload["pairs"].append(second)
    write(path, payload)
    with pytest.raises(ValueError, match="Song appears in different splits"):
        inspect_manifest(path)


@pytest.mark.parametrize("shared", ["audio", "reference"])
def test_identical_source_bytes_catch_leakage_under_different_song_names(tmp_path, shared):
    path, payload = make_manifest(tmp_path)
    second = copy.deepcopy(payload["pairs"][0])
    second.update(pair_id="take-2", song_id="another-song", split="test")
    other = "reference" if shared == "audio" else "audio"
    different = tmp_path / "different-source"
    different.write_bytes(b"different")
    second[other].update(path=different.name, sha256=file_hash(different))
    payload["pairs"].append(second)
    write(path, payload)
    with pytest.raises(ValueError, match=f"Identical {shared}"):
        inspect_manifest(path)


def test_micro_counts_do_not_average_track_f1_or_pool_different_models(tmp_path):
    path, payload = make_manifest(tmp_path)
    second = copy.deepcopy(payload["pairs"][0])
    second.update(pair_id="take-2", song_id="song-2")
    empty = tmp_path / "empty.json"
    save_events([], empty)
    second["prediction"].update(path=empty.name, sha256=file_hash(empty))
    payload["pairs"].append(second)
    third = copy.deepcopy(second)
    third.update(pair_id="take-3", model_id="another-model", model_provenance="different")
    payload["pairs"].append(third)
    write(path, payload)
    report = evaluate_manifest(path, max_shift=0.2)
    groups = {row["model_id"]: row for row in report["aggregates"]}
    assert len(groups) == 2
    assert groups["model-1"]["shifted"]["onsets"]["f1"] == pytest.approx(4 / 7)
    assert groups["another-model"]["shifted"]["onsets"]["f1"] == 0


def test_model_id_cannot_silently_mix_different_settings(tmp_path):
    path, payload = make_manifest(tmp_path)
    second = copy.deepcopy(payload["pairs"][0])
    second.update(pair_id="take-2", model_provenance="different threshold")
    payload["pairs"].append(second)
    write(path, payload)
    with pytest.raises(ValueError, match="same model and settings"):
        inspect_manifest(path)


def test_source_reference_caveats_survive_manifest_review_declaration(tmp_path):
    path, payload = make_manifest(tmp_path)
    reference = tmp_path / "reference.json"
    caveats = {
        "reference_status": "candidate",
        "approximate_techniques": True,
        "technique_flags": ["bend"],
        "data_permission": "unassessed",
    }
    save_events([Note(0.2, 0.5, 64)], reference, metadata=caveats)
    payload["pairs"][0]["reference"].update(sha256=file_hash(reference))
    payload["pairs"][0]["reference_quality"] = "reviewed"
    write(path, payload)
    report = evaluate_manifest(path, max_shift=0)
    assert report["pairs"][0]["reference_metadata"] == caveats
    assert report["pairs"][0]["manifest_entry"]["reference_quality"] == "reviewed"


def test_cli_refuses_overwriting_source_and_keeps_existing_report_on_failure(tmp_path, monkeypatch):
    path, payload = make_manifest(tmp_path)
    source = tmp_path / payload["pairs"][0]["reference"]["path"]
    before = source.read_bytes()
    monkeypatch.setattr("sys.argv", ["evaluate_pairs", str(path), "--output", str(source)])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 1
    assert source.read_bytes() == before
    output = tmp_path / "report.json"
    output.write_text("previous result", encoding="utf-8")
    source.write_bytes(b"changed")
    monkeypatch.setattr("sys.argv", ["evaluate_pairs", str(path), "--output", str(output)])
    with pytest.raises(SystemExit):
        main()
    assert output.read_text() == "previous result"

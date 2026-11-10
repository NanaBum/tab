import json

import numpy as np
import pytest
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import maximum_bipartite_matching

from scripts.compare_timed_events import main, read_notes
from tabber.alignment import _groups, _onset_fit, compare_with_global_shift
from tabber.evaluation import match_notes
from tabber.events import save_events
from tabber.export import write_outputs
from tabber.models import FrettedNote, Note


def test_start_shift_recovers_attacks_without_erasing_early_noise():
    reference = [Note(i, i + 0.4, 60 + i) for i in range(4)]
    prediction = [Note(n.start + 2.3, n.end + 2.3, n.pitch) for n in reference]
    prediction.insert(0, Note(0, 0.2, 20))
    original = list(prediction)
    report = compare_with_global_shift(reference, prediction, max_shift=3)
    assert report["prediction_shift_seconds"] == pytest.approx(-2.3)
    assert report["raw"]["onsets"]["matched_notes"] == 0
    assert report["shifted"]["onsets"]["matched_notes"] == 4
    assert report["shifted"]["onsets"]["predicted_notes"] == 5
    assert report["shifted"]["onsets"]["precision"] == 0.8
    assert report["comparison_origin_padding_seconds"] == pytest.approx(2.3)
    assert prediction == original


def test_positive_shift_moves_releases_by_the_same_amount():
    report = compare_with_global_shift([Note(2, 3, 64)], [Note(0, 1, 64)], max_shift=2)
    assert report["prediction_shift_seconds"] == 2
    assert report["shifted"]["onsets_offsets"]["f1"] == 1
    assert report["at_search_boundary"] is True


def test_one_shift_does_not_repair_tempo_drift_or_wrong_notes():
    reference = [Note(i, i + 0.2, 60 + i) for i in range(4)]
    prediction = [Note(i * 1.2, i * 1.2 + 0.2, 60 + i) for i in range(4)]
    report = compare_with_global_shift(reference, prediction, max_shift=1)
    assert report["shifted"]["onsets"]["matched_notes"] == 1
    wrong = compare_with_global_shift(reference, [Note(0, 1, 100)])
    assert wrong["prediction_shift_seconds"] == 0
    assert wrong["shifted"]["onsets"]["matched_notes"] == 0


def test_repeated_pattern_reports_alternative_offsets_and_keeps_extras():
    report = compare_with_global_shift(
        [Note(i, i + 0.2, 64) for i in (0, 1)],
        [Note(i, i + 0.2, 64) for i in (0, 1, 2)],
        max_shift=2,
    )
    assert report["prediction_shift_seconds"] == 0
    assert report["ambiguous_shift"] is True
    assert -1 in report["alternative_shifts_seconds"]
    assert report["shifted"]["onsets"]["predicted_notes"] == 3


def test_sparse_matching_and_shift_search_match_small_dense_oracle():
    random = np.random.default_rng(23)
    for _ in range(30):
        reference = [
            Note(float(t), float(t + 0.2), int(p))
            for t, p in zip(random.uniform(0, 1, 12), random.integers(60, 63, 12))
        ]
        predicted = [
            Note(float(t), float(t + 0.3), int(p))
            for t, p in zip(random.uniform(0, 1, 15), random.integers(60, 63, 15))
        ]
        dense = np.array(
            [
                [r.pitch == p.pitch and abs(r.start - p.start) <= 0.05 + 1e-9 for p in predicted]
                for r in reference
            ]
        )
        expected = sum(maximum_bipartite_matching(csr_matrix(dense), perm_type="column") >= 0)
        assert len(match_notes(reference, predicted)) == expected
        assert _onset_fit(_groups(reference), _groups(predicted), 0, 0.05)[0] == expected


def test_full_song_sized_matching_keeps_all_events():
    reference = [Note(i * 0.2, i * 0.2 + 0.1, 40 + i % 40) for i in range(5000)]
    assert len(match_notes(reference, reference)) == 5000


def test_sparse_release_matching_preserves_alternative_one_to_one_assignment():
    reference = [Note(0, 1, 64), Note(0.02, 2, 64)]
    predicted = [Note(0.01, 2, 64), Note(0.01, 1, 64)]
    assert set(match_notes(reference, predicted, offsets=True)) == {(0, 1), (1, 0)}


def test_comparison_cli_preserves_inputs_and_reports_both_scores(tmp_path, monkeypatch):
    reference, prediction, output = (
        tmp_path / name for name in ("r.json", "p.json", "report.json")
    )
    save_events([Note(0, 1, 64)], reference)
    save_events([Note(1, 2, 64)], prediction)
    originals = (reference.read_bytes(), prediction.read_bytes())
    monkeypatch.setattr(
        "sys.argv", ["compare", str(reference), str(prediction), "--output", str(output)]
    )
    main()
    report = json.loads(output.read_text())
    assert report["raw"]["onsets"]["f1"] == 0
    assert report["shifted"]["onsets"]["f1"] == 1
    assert originals == (reference.read_bytes(), prediction.read_bytes())


def test_reader_uses_original_times_from_actual_exported_notes(tmp_path):
    note = Note(0.02, 0.17, 64, 0.1)
    write_outputs([FrettedNote(note, 0, 0)], tmp_path, 120, 16)
    assert read_notes(tmp_path / "notes.json") == [note]


def test_comparison_refuses_overwriting_its_input(tmp_path, monkeypatch):
    source = tmp_path / "input.json"
    save_events([Note(0, 1, 64)], source)
    original = source.read_bytes()
    monkeypatch.setattr("sys.argv", ["compare", str(source), str(source), "--output", str(source)])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 1
    assert source.read_bytes() == original


@pytest.mark.parametrize(
    "options", [{"max_shift": float("inf")}, {"step": 0}, {"max_shift": 10, "step": 0.00001}]
)
def test_shift_search_rejects_invalid_or_excessive_work(options):
    with pytest.raises(ValueError):
        compare_with_global_shift([], [], **options)

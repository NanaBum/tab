import pytest

from tabber.evaluation import guitarset_notes, match_notes, score_notes
from tabber.models import Note


def test_duplicate_predictions_cannot_match_the_same_reference_twice():
    reference = [Note(0, 1, 60)]
    prediction = [Note(0, 1, 60), Note(0.01, 1, 60)]
    score = score_notes(reference, prediction)
    assert score.matched_notes == 1
    assert score.precision == 0.5
    assert score.recall == 1


def test_matching_finds_global_assignment_instead_of_greedy_loss():
    reference = [Note(0.04, 1, 60), Note(0, 1, 60)]
    predicted = [Note(0.02, 1, 60), Note(0.08, 1, 60)]
    assert len(match_notes(reference, predicted)) == 2


def test_offsets_and_wrong_pitches_are_separate_errors():
    reference = [Note(0, 1, 60), Note(2, 3, 62)]
    predicted = [Note(0, 2, 60), Note(2, 3, 63)]
    assert score_notes(reference, predicted).matched_notes == 1
    assert score_notes(reference, predicted, offsets=True).matched_notes == 0
    assert score_notes([], predicted).precision == 0
    assert score_notes(reference, []).recall == 0
    with pytest.raises(ValueError):
        match_notes(reference, predicted, onset_tolerance=float("nan"))


def test_guitarset_string_order_and_relative_observation_times():
    jams = {
        "annotations": [
            {
                "namespace": "note_midi",
                "time": 500,
                "annotation_metadata": {"data_source": "0"},
                "data": [{"time": 1, "duration": 2, "value": 43.01}],
            }
        ]
    }
    note = guitarset_notes(jams, end=2)[0]
    assert (note.string, note.fret, note.note.pitch) == (5, 3, 43)
    assert (note.note.start, note.note.end) == (1, 2)

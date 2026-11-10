import numpy as np
import pytest

from tabber.fretting import assign_frets, assign_polyphonic_frets
from tabber.models import Note
from tabber.string_model import StringModel, isolated_features


@pytest.mark.parametrize("assign", [assign_frets, assign_polyphonic_frets])
def test_string_priors_change_fingering_without_changing_notes(assign):
    notes = [Note(0, 1, 64)]
    assert assign(notes)[0].string == 0
    prior = [[0.01, 0.95, 0.01, 0.01, 0.01, 0.01]]
    assigned = assign(notes, string_priors=prior)
    assert (assigned[0].string, assigned[0].fret) == (1, 5)
    assert assigned[0].note is notes[0]


@pytest.mark.parametrize("priors", [[], [[0] * 6], [[float("nan")] * 6], [[1, 0]]])
@pytest.mark.parametrize("assign", [assign_frets, assign_polyphonic_frets])
def test_invalid_priors_are_rejected(assign, priors):
    with pytest.raises(ValueError):
        assign([Note(0, 1, 64)], string_priors=priors)


def test_melodic_prior_rows_follow_unsorted_notes():
    first, second = Note(0, 1, 64), Note(1, 2, 64)
    notes = [second, first]
    priors = [[0, 0, 1, 0, 0, 0], [0, 1, 0, 0, 0, 0]]
    assigned = assign_frets(notes, string_priors=priors)
    assert [(item.note, item.string, item.fret) for item in assigned] == [
        (first, 1, 5),
        (second, 2, 9),
    ]
    assert assign_frets(notes, string_priors=[[1] * 6] * 2) == assign_frets(notes)


def test_model_masks_impossible_strings_before_softmax(tmp_path):
    path = tmp_path / "weights.npz"
    np.savez(
        path,
        feature_version=1,
        mean=np.zeros(88),
        scale=np.ones(88),
        coefficients=np.zeros((6, 88)),
        intercept=np.array([10000, 0, 0, 0, 0, 0]),
        classes=np.arange(6),
    )
    probabilities = StringModel(path).predict([40], np.zeros((1, 39)))
    assert np.all(np.isfinite(probabilities))
    assert np.array_equal(probabilities, [[0, 0, 0, 0, 0, 1]])


def test_model_does_not_use_mixed_or_short_windows():
    waveform = np.sin(np.arange(22050) * 0.1)
    mfcc = np.zeros((13, 102))
    notes = [Note(0, 0.5, 64), Note(0.1, 0.5, 67), Note(0.7, 0.74, 64)]
    assert isolated_features(waveform, mfcc, notes) == [None, None, None]

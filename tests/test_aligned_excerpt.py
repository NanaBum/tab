import pytest

from scripts.compare_aligned_excerpt import excerpt_target
from tabber.models import Note


def test_fixed_shift_crops_excerpt_and_collapses_only_coincident_unisons():
    tracks = [
        [Note(1.4, 1.8, 64), Note(1.5, 1.9, 64), Note(2.4, 2.8, 64), Note(2.5, 2.6, 65)],
        [Note(1.5, 2.0, 64), Note(1.51, 1.8, 64), Note(1.5, 1.9, 65)],
    ]
    result = excerpt_target(tracks, score_shift=-0.5, recording_start=1, duration=1)
    assert [n.pitch for n in result] == [64, 65, 64, 64]
    assert [n.start for n in result] == pytest.approx([0, 0, 0.01, 0.9])
    assert [n.end for n in result] == pytest.approx([0.5, 0.4, 0.3, 1])

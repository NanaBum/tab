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


def test_score_scale_applies_to_attack_and_release_before_excerpt_crop():
    result = excerpt_target(
        [[Note(10, 11, 64), Note(12, 13, 65)]],
        score_shift=-1,
        score_scale=1.1,
        recording_start=10,
        duration=2,
    )
    assert len(result) == 1
    assert (result[0].start, result[0].end) == pytest.approx((0, 1.1))

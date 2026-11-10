import mido
import numpy as np
import pytest

from scripts.screen_pair_alignment import STEP, scan_windows, score_features


def test_coarse_score_counts_overlapping_unisons_without_pairing_releases():
    midi = mido.MidiFile()
    track = midi.add_track()
    track.extend(
        [
            mido.Message("note_on", note=60, velocity=90),
            mido.Message("note_on", note=60, velocity=90, time=240),
            mido.Message("note_off", note=60, time=240),
            mido.Message("note_on", note=60, velocity=0, time=240),
        ]
    )
    chroma = score_features(midi)
    assert chroma[round(0.375 / STEP), 0] == 2
    assert chroma[round(0.625 / STEP), 0] == 1
    assert chroma[-1, 0] == 0


def test_coarse_search_reports_positive_shift_and_later_clock_residuals():
    rng = np.random.default_rng(11)
    score = rng.normal(size=(round(120 / STEP), 12))
    score /= np.linalg.norm(score, axis=1, keepdims=True)
    lag = 18
    audio = np.pad(score, ((lag, 0), (0, 0)))
    result = scan_windows(score, audio)
    assert result["global_shift_seconds"] == pytest.approx(lag * STEP, abs=0.0005)
    assert result["global_mean_similarity"] == 1
    assert all(row["peak_margin_at_least_0_4_seconds"] > 0 for row in result["windows"])
    assert result["early_fit"]["score_scale"] == 1
    assert set(result["early_fit"]["later_shift_residuals_seconds"]) == {0}

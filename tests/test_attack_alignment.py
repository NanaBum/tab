import numpy as np
import pytest

from scripts.probe_attack_alignment import LOW_PITCH, STEP, assess_windows


def test_later_window_checks_fixed_calibration_even_when_its_peak_moves():
    flux = np.zeros((4, round(12 / STEP)))
    attacks = []
    for window_start, shift in ((2, 8 * STEP), (7, -10 * STEP)):
        for index in range(12):
            time = window_start + 0.17 * index
            pitch_index = index % 4
            attacks.append((time, LOW_PITCH + pitch_index))
            flux[pitch_index, round((time + shift) / STEP)] = 3

    result = assess_windows(flux, attacks, [(2, 5), (7, 10)], coarse=0, duration=12)

    assert result["calibrated_shift_seconds"] == pytest.approx(8 * STEP, abs=0.0001)
    later = result["windows"][1]
    assert later["local_best_shift_seconds"] == pytest.approx(-10 * STEP, abs=0.0001)
    assert later["local_best_flux"] == 3
    assert later["calibrated_flux"] == 0


def test_same_affine_clock_applies_in_calibration_and_later_window():
    flux = np.zeros((4, round(12 / STEP)))
    attacks = [
        (start + index * 0.1, LOW_PITCH + index % 4) for start in (2, 7) for index in range(12)
    ]
    for time, pitch in attacks:
        flux[pitch - LOW_PITCH, round((1.03 * time + 0.2) / STEP)] = 3
    result = assess_windows(
        flux,
        attacks,
        [(2, 5), (7, 10)],
        coarse=0.2,
        duration=12,
        scale=1.03,
    )
    assert result["calibrated_shift_seconds"] == 0.2
    assert [row["calibrated_flux"] for row in result["windows"]] == [3, 3]

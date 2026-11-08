"""Bounded, single-offset event comparison; no tempo warping or note deletion."""

import math
from dataclasses import asdict

from .evaluation import score_notes
from .models import Note


def _onset_fit(reference, predicted, shift, tolerance):
    """Maximum cardinality for sorted equal-width onset intervals, by pitch."""
    count, residual = 0, 0.0
    for pitch, references in reference.items():
        predictions = predicted.get(pitch, [])
        i, j = 0, 0
        while i < len(references) and j < len(predictions):
            difference = references[i] - predictions[j] - shift
            if abs(difference) <= tolerance + 1e-9:
                count += 1
                residual += abs(difference)
                i += 1
                j += 1
            elif difference < 0:
                i += 1
            else:
                j += 1
    return count, residual


def _groups(notes):
    groups = {}
    for note in notes:
        groups.setdefault(note.pitch, []).append(note.start)
    return {pitch: sorted(times) for pitch, times in groups.items()}


def compare_with_global_shift(
    reference: list[Note], predicted: list[Note], *, max_shift=5.0, step=0.01, onset_tolerance=0.05
) -> dict:
    """Compare unchanged events, then a bounded grid search over one translation.

    Shift is added to every prediction's attack AND release. Selection maximizes
    pitch/onset matches, then minimizes the sorted matching's onset residual,
    then prefers the smallest absolute shift. This is a reference-assisted
    diagnostic, not an independently measured timing-accuracy benchmark.
    """
    if not math.isfinite(max_shift) or max_shift < 0:
        raise ValueError("Maximum shift must be finite and nonnegative")
    if not math.isfinite(step) or step <= 0:
        raise ValueError("Shift step must be finite and positive")
    if not math.isfinite(onset_tolerance) or onset_tolerance < 0:
        raise ValueError("Onset tolerance must be finite and nonnegative")
    intervals = math.floor(max_shift / step + 1e-9)
    if intervals > 5000:
        raise ValueError("Use at most 10,001 shift-grid points")
    shifts = [index * step for index in range(-intervals, intervals + 1)]
    # Include the declared bounds even when the grid does not divide them.
    shifts = sorted(set(shifts + [-max_shift, 0.0, max_shift]))
    if len(shifts) > 10001:
        raise ValueError("Use at most 10,001 shift-grid points")
    refs, preds = _groups(reference), _groups(predicted)
    ranked = [(*_onset_fit(refs, preds, shift, onset_tolerance), shift) for shift in shifts]
    matches = max(row[0] for row in ranked)
    residual = min(row[1] for row in ranked if row[0] == matches)
    tied = [row[2] for row in ranked if row[0] == matches and abs(row[1] - residual) <= 1e-9]
    shift = min(tied, key=lambda value: (abs(value), value)) if matches else 0.0
    # Negative shifted noise still counts as extra. Move both timelines to a
    # common nonnegative origin instead of clipping/discarding those events.
    padding = max(0.0, -shift)
    moved_reference = [
        Note(n.start + padding, n.end + padding, n.pitch, n.confidence) for n in reference
    ]
    moved_prediction = [
        Note(n.start + shift + padding, n.end + shift + padding, n.pitch, n.confidence)
        for n in predicted
    ]
    raw = {
        "onsets": asdict(score_notes(reference, predicted, onset_tolerance=onset_tolerance)),
        "onsets_offsets": asdict(
            score_notes(reference, predicted, onset_tolerance=onset_tolerance, offsets=True)
        ),
    }
    aligned = {
        "onsets": asdict(
            score_notes(moved_reference, moved_prediction, onset_tolerance=onset_tolerance)
        ),
        "onsets_offsets": asdict(
            score_notes(
                moved_reference, moved_prediction, onset_tolerance=onset_tolerance, offsets=True
            )
        ),
    }
    alternatives = (
        [value for value in tied if abs(value - shift) > max(step, 2 * onset_tolerance) + 1e-9]
        if matches
        else []
    )
    return {
        "purpose": "Reference-assisted global-shift diagnostic; raw timing scores retained",
        "prediction_shift_seconds": shift,
        "sign_convention": "Add this shift to every predicted attack and release",
        "comparison_origin_padding_seconds": padding,
        "search": {
            "max_shift_seconds": max_shift,
            "step_seconds": step,
            "candidate_count": len(shifts),
            "onset_tolerance_seconds": onset_tolerance,
            "criterion": "Most pitch/onset matches, least sorted-match absolute onset residual, smallest absolute shift",
        },
        "raw": raw,
        "shifted": aligned,
        "ambiguous_shift": bool(alternatives),
        "alternative_shifts_seconds": alternatives[:20],
        "alternatives_truncated": len(alternatives) > 20,
        "at_search_boundary": bool(
            matches and max_shift > 0 and abs(abs(shift) - max_shift) <= 1e-9
        ),
        "limits": "One translation on a finite grid; no tempo/section warping, pitch correction or note removal. Shift is fitted using this reference, not independently calibrated.",
    }

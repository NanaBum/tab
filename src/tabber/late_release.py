"""Use audio evidence to recover an unusually wide chord voicing."""

from dataclasses import replace

import numpy as np
import soundfile as sf

from .fretting import (
    CHORD_ATTACK_SECONDS,
    CHORD_SUSTAIN_SECONDS,
    StringAssignmentConflict,
    assign_polyphonic_frets,
)

WINDOW_SECONDS = 0.05
QUIET_RATIO = 0.075


def _release_ratio(path, note, handoff):
    """Compare stable pitch energy with two quiet windows before the new chord."""
    quiet_end = handoff - 0.005
    loud_end = quiet_end - 2 * WINDOW_SECONDS
    start = loud_end - 2 * WINDOW_SECONDS
    if start < note.start + 0.025:
        return
    try:
        with sf.SoundFile(path) as audio:
            rate = audio.samplerate
            samples = round(WINDOW_SECONDS * rate)
            first_frame = round(start * rate)
            if samples < 3 or first_frame + 4 * samples > audio.frames:
                return
            audio.seek(first_frame)
            chunk = audio.read(4 * samples, dtype="float32", always_2d=True)
    except (OSError, sf.LibsndfileError):
        return
    if len(chunk) != 4 * samples or not np.isfinite(chunk).all():
        return

    # Check nearby frequencies too, so a little vibrato does not look like silence.
    harmonics = (
        np.arange(1, 4)[:, None]
        * 440
        * 2 ** ((note.pitch - 69 + np.array([-1, -0.5, 0, 0.5, 1])) / 12)
    )
    window = np.hanning(samples)
    basis = np.exp(-2j * np.pi * np.outer(np.arange(samples) / rate, harmonics.ravel()))
    spectrum = np.abs(chunk.reshape(4, samples, -1).transpose(0, 2, 1) @ (window[:, None] * basis))
    energy = spectrum.reshape(4, chunk.shape[1], 3, -1).max(axis=(1, 3)) * (2 / window.sum())
    before = energy[:2].min(axis=0)
    if before.max() < 0.0001:
        return
    supported = before >= 0.2 * before.max()
    # A tail may still be fading in the penultimate window. Reject strong
    # pitch evidence there, and require a much quieter final window.
    if max(energy[2, supported] / before[supported]) > 0.3:
        return
    return float(max(energy[3, supported] / before[supported]))


def _span(positions):
    frets = [position.fret for position in positions if position.fret]
    return max(frets, default=0) - min(frets, default=0)


def repair_late_releases(events, assigned, audio, *, tuning, max_span, string_priors=None):
    """Retry a chord with one audio-supported earlier release. Keep every attack."""
    order = sorted(range(len(events)), key=lambda index: events[index].start)
    retained = list(events)
    repairs = []
    group_end = 0
    for group_start, first_index in enumerate(order):
        if group_start < group_end:
            continue
        handoff = events[first_index].start
        group_end = group_start + 1
        while (
            group_end < len(order)
            and events[order[group_end]].start - handoff <= CHORD_ATTACK_SECONDS
        ):
            group_end += 1
        group = order[group_start:group_end]
        if len({events[index].pitch for index in group}) < 3:
            continue
        chord_ids = {id(events[index]) for index in group}
        last_attack = events[group[-1]].start
        if any(events[index].end < last_attack + CHORD_SUSTAIN_SECONDS for index in group):
            continue
        span = _span(position for position in assigned if id(position.note) in chord_ids)
        if span < max(9, max_span + 3):
            continue

        best = None
        for index in order[:group_start]:
            note = retained[index]
            if not handoff + 0.01 < note.end <= handoff + 0.25:
                continue
            ratio = _release_ratio(audio, note, handoff)
            if ratio is None or ratio > QUIET_RATIO:
                continue
            trial = retained.copy()
            trial[index] = replace(note, end=handoff)
            try:
                fitted = assign_polyphonic_frets(
                    trial, tuning=tuning, max_span=max_span, string_priors=string_priors
                )
            except StringAssignmentConflict:
                continue
            fitted_span = _span(position for position in fitted if id(position.note) in chord_ids)
            if fitted_span > min(max_span + 1, span - 4):
                continue
            cost = (fitted_span, note.end - handoff)
            if best is None or cost < best[0]:
                best = (cost, trial, fitted, index, ratio)
        if best is not None:
            cost, retained, assigned, index, ratio = best
            repairs.append(
                {
                    "source_index": index,
                    "new_end": handoff,
                    "pitch_amplitude_ratio": ratio,
                    "chord_span_before": span,
                    "chord_span_after": cost[0],
                }
            )
    return assigned, retained, repairs

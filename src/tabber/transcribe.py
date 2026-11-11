"""A monophonic autocorrelation baseline and optional Basic Pitch adapter."""

import math
from functools import lru_cache
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import correlate, find_peaks

from .models import Note


def baseline_frequency_floor(min_pitch=40):
    """Preserve the original 75 Hz band unless explicit tuning requires lower.

    Half a semitone below the lowest open string leaves room for pitch estimation
    error. This is a search-band choice, not a filter that removes detected notes.
    """
    if type(min_pitch) is not int or not 0 <= min_pitch <= 127:
        raise ValueError("Baseline minimum pitch must be an integer MIDI pitch from 0 to 127")
    return min(75.0, 440 * 2 ** ((min_pitch - 0.5 - 69) / 12))


@lru_cache(maxsize=1)
def _basic_pitch_model():
    from basic_pitch import ICASSP_2022_MODEL_PATH
    from basic_pitch.inference import Model

    return Model(ICASSP_2022_MODEL_PATH)


def transcribe(
    path: Path,
    backend: str = "baseline",
    min_confidence: float = 0.5,
    *,
    guitar_onset: float = 0.3,
    guitar_checkpoint: Path | None = None,
    guitar_release_v1=False,
    guitar_input_gain: float = 1.0,
    baseline_min_pitch: int = 40,
) -> list[Note]:
    if not math.isfinite(min_confidence) or not 0 <= min_confidence <= 1:
        raise ValueError("Minimum confidence must be between 0 and 1")
    low_frequency = baseline_frequency_floor(baseline_min_pitch)
    if backend != "baseline" and baseline_min_pitch != 40:
        raise ValueError("Baseline search-band options apply only to the simple melody detector")
    if backend != "guitar-gaps" and guitar_release_v1:
        raise ValueError("The optional release weights need the guitar model")
    if backend != "guitar-gaps" and guitar_input_gain != 1.0:
        raise ValueError("Guitar input level applies only to the guitar model")
    if backend == "guitar-gaps":
        if min_confidence != 0.5:
            raise ValueError("Guitar model uses --onset-threshold instead of --min-confidence")
        from .guitar_gaps import transcribe_gaps

        options = {"release_v1": True} if guitar_release_v1 else {}
        if guitar_input_gain != 1.0:
            options["input_gain"] = guitar_input_gain
        return transcribe_gaps(
            path, checkpoint=guitar_checkpoint, onset_threshold=guitar_onset, **options
        )
    if backend == "basic-pitch":
        try:
            from basic_pitch.inference import predict
        except ImportError as exc:
            raise ValueError(
                f"Basic Pitch dependencies could not load ({exc}); "
                "install requirements/ml.in in the separate Python 3.11 environment"
            ) from exc
        _, _, events = predict(str(path), model_or_model_path=_basic_pitch_model())
        return sorted(
            [
                Note(float(a), float(b), int(p), float(np.clip(c, 0, 1)))
                for a, b, p, c, *_ in events
                if c >= min_confidence
            ],
            key=lambda n: n.start,
        )
    if backend != "baseline":
        raise ValueError(f"Unknown backend: {backend}")
    audio, rate = sf.read(path, always_2d=True)
    audio = audio.mean(axis=1)
    if not np.all(np.isfinite(audio)):
        raise ValueError("Audio contains non-finite samples")
    if len(audio) == 0 or np.max(np.abs(audio)) < 1e-7:
        return []
    # Low custom tunings need enough cycles for autocorrelation. Standard, Eb,
    # Drop D and D standard all retain the original 80 ms analysis window.
    frame = max(256, int(rate * 0.08), math.ceil(rate * 4 / low_frequency))
    hop = max(1, int(rate * 0.01))
    threshold = max(1e-5, float(np.max(np.abs(audio))) * 0.025)
    labels = []
    for start in range(0, len(audio), hop):
        chunk = audio[start : start + frame]
        label = None
        if len(chunk) >= frame // 2 and np.sqrt(np.mean(chunk**2)) > threshold:
            chunk = (chunk - chunk.mean()) * np.hanning(len(chunk))
            ac = correlate(chunk, chunk, mode="full", method="fft")[len(chunk) - 1 :]
            lo, hi = max(1, int(rate / 1400)), min(len(ac) - 1, int(rate / low_frequency))
            peaks, _ = find_peaks(ac[lo : hi + 1])
            if len(peaks) and ac[0] > 0:
                candidates = peaks + lo
                lag = int(candidates[np.argmax(ac[candidates])])
                confidence = float(np.clip(ac[lag] / ac[0], 0, 1))
                if confidence >= max(0.65, min_confidence):
                    label = (round(69 + 12 * np.log2(rate / lag / 440)), confidence)
        labels.append(label)
    notes = []
    first = 0
    while first < len(labels):
        label = labels[first]
        last = first + 1
        while last < len(labels) and (
            (labels[last] is None and label is None)
            or (labels[last] is not None and label is not None and labels[last][0] == label[0])
        ):
            last += 1
        if label is not None and (last - first) * hop / rate >= 0.07:
            notes.append(
                Note(
                    first * hop / rate,
                    min(last * hop / rate, len(audio) / rate),
                    int(label[0]),
                    float(np.mean([x[1] for x in labels[first:last]])),
                )
            )
        first = last
    return notes

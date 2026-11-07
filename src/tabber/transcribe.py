"""A monophonic autocorrelation baseline and optional Basic Pitch adapter."""

from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import correlate, find_peaks

from .models import Note


def transcribe(path: Path, backend: str = "baseline") -> list[Note]:
    if backend == "basic-pitch":
        try:
            from basic_pitch.inference import predict
        except ImportError as exc:
            raise ValueError("Basic Pitch is optional; see README.md for its environment") from exc
        _, _, events = predict(str(path))
        return sorted(
            [
                Note(float(a), float(b), int(p), float(np.clip(c, 0, 1)))
                for a, b, p, c, *_ in events
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
    frame = max(256, int(rate * 0.08))
    hop = max(1, int(rate * 0.01))
    threshold = max(1e-5, float(np.max(np.abs(audio))) * 0.025)
    labels = []
    for start in range(0, len(audio), hop):
        chunk = audio[start : start + frame]
        label = None
        if len(chunk) >= frame // 2 and np.sqrt(np.mean(chunk**2)) > threshold:
            chunk = (chunk - chunk.mean()) * np.hanning(len(chunk))
            ac = correlate(chunk, chunk, mode="full", method="fft")[len(chunk) - 1 :]
            lo, hi = max(1, int(rate / 1400)), min(len(ac) - 1, int(rate / 75))
            peaks, _ = find_peaks(ac[lo : hi + 1])
            if len(peaks) and ac[0] > 0:
                candidates = peaks + lo
                lag = int(candidates[np.argmax(ac[candidates])])
                confidence = float(np.clip(ac[lag] / ac[0], 0, 1))
                if confidence >= 0.65:
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

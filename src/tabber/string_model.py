"""Experimental string priors for isolated notes; all models stay local.

This is not a chord separator. Mixed/short windows receive uniform priors, leaving
the ergonomic fingering heuristic in charge. Feature extraction needs the ML env.
"""

import math
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

from .models import STANDARD_TUNING, Note

FEATURE_VERSION = 1
PITCH_MIN = 40
PITCH_MAX = 88


def audio_features(waveform: np.ndarray, rate: int):
    try:
        import librosa
    except ImportError as error:
        raise ValueError("String-tone features need the separate ML environment") from error
    if waveform.ndim > 1:
        waveform = waveform.mean(axis=1)
    if rate != 22050:
        divisor = math.gcd(rate, 22050)
        waveform = resample_poly(waveform, 22050 // divisor, rate // divisor)
    if len(waveform) < 2048 or not np.all(np.isfinite(waveform)):
        raise ValueError("String-tone features need at least 0.1 seconds of finite audio")
    mfcc = librosa.feature.mfcc(y=waveform, sr=22050, n_mfcc=14, n_fft=2048, hop_length=220)[1:]
    return waveform, mfcc


def isolated_features(waveform, mfcc, notes: list[Note]):
    """Return feature rows or None, using the same windows as the training recipe."""
    rows = []
    rate = 22050
    for note in notes:
        lo = note.start + 0.03
        hi = min(note.end, lo + 0.15)
        if hi - lo < 0.06 or not PITCH_MIN <= note.pitch <= PITCH_MAX:
            rows.append(None)
            continue
        if any(other is not note and other.start < hi and other.end > lo for other in notes):
            rows.append(None)
            continue
        chunk = waveform[int(lo * rate) : int(hi * rate)]
        coefficients = mfcc[:, max(0, int(lo * rate / 220)) : max(1, int(hi * rate / 220))]
        if len(chunk) < 128 or not coefficients.shape[1] or np.sqrt(np.mean(chunk**2)) < 1e-7:
            rows.append(None)
            continue
        spectrum = np.abs(np.fft.rfft((chunk - chunk.mean()) * np.hanning(len(chunk)), n=8192))
        frequencies = np.fft.rfftfreq(8192, 1 / rate)
        f0 = 440 * 2 ** ((note.pitch - 69) / 12)
        harmonics = np.array(
            [
                np.max(spectrum[np.abs(frequencies - f0 * h) < max(12, f0 * 0.025)], initial=1e-8)
                for h in range(1, 13)
            ]
        )
        log_h = np.log(harmonics + 1e-8)
        log_h -= log_h.mean()
        centroid = np.sum(frequencies * spectrum) / (np.sum(spectrum) + 1e-8) / f0
        rows.append(
            np.concatenate((coefficients.mean(axis=1), coefficients.std(axis=1), log_h, [centroid]))
        )
    return rows


def pitch_features(pitches):
    pitches = np.asarray(pitches, dtype=int)
    if np.any((pitches < PITCH_MIN) | (pitches > PITCH_MAX)):
        raise ValueError("String model pitch is outside the supported guitar range")
    return np.eye(PITCH_MAX - PITCH_MIN + 1)[pitches - PITCH_MIN]


class StringModel:
    def __init__(self, path: Path):
        # Numeric NPZ only: no pickle or executable model loading.
        try:
            with np.load(path, allow_pickle=False) as weights:
                if int(weights["feature_version"]) != FEATURE_VERSION:
                    raise ValueError("Unsupported string-model feature version")
                self.mean = weights["mean"]
                self.scale = weights["scale"]
                self.coefficients = weights["coefficients"]
                self.intercept = weights["intercept"]
                self.classes = weights["classes"]
        except (KeyError, TypeError) as error:
            raise ValueError(f"Not a compatible string-model file: {error}") from error
        if (
            self.mean.shape != (88,)
            or self.scale.shape != (88,)
            or self.coefficients.shape != (6, 88)
            or self.intercept.shape != (6,)
            or not np.array_equal(self.classes, np.arange(6))
        ):
            raise ValueError("String-model weights have incompatible shapes or classes")
        if any(
            a.dtype.kind not in "fiu"
            for a in (self.mean, self.scale, self.coefficients, self.intercept)
        ):
            raise ValueError("String-model weights must be numeric")
        if not all(
            np.all(np.isfinite(a))
            for a in (self.mean, self.scale, self.coefficients, self.intercept)
        ) or np.any(self.scale <= 0):
            raise ValueError("String-model weights must be finite with positive scales")

    def predict(self, pitches, timbre):
        if len(pitches) == 0:
            return np.empty((0, 6))
        x = np.column_stack((pitch_features(pitches), timbre))
        if x.shape[1] != 88 or not np.all(np.isfinite(x)):
            raise ValueError("Invalid string-tone features")
        logits = ((x - self.mean) / self.scale) @ self.coefficients.T + self.intercept
        valid = np.array(
            [[0 <= pitch - tuning <= 24 for tuning in STANDARD_TUNING] for pitch in pitches]
        )
        logits = np.where(valid, logits, -np.inf)
        logits -= logits.max(axis=1, keepdims=True)
        probabilities = np.exp(logits)
        return probabilities / probabilities.sum(axis=1, keepdims=True)


def string_priors(audio: Path, notes: list[Note], model_path: Path):
    model = StringModel(model_path)
    waveform, rate = sf.read(audio, always_2d=True)
    waveform, mfcc = audio_features(waveform, rate)
    features = isolated_features(waveform, mfcc, notes)
    priors = np.full((len(notes), 6), 1 / 6)
    indices = [i for i, row in enumerate(features) if row is not None]
    if indices:
        priors[indices] = model.predict(
            [notes[i].pitch for i in indices], np.asarray([features[i] for i in indices])
        )
    return priors

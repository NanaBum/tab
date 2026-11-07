"""Optional local tempo estimate; never a claim of reliable beat/downbeat alignment."""

import math
from dataclasses import dataclass, field
from pathlib import Path
from statistics import median

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly


@dataclass(frozen=True)
class TempoEstimate:
    bpm: float
    beats: int
    analyzed_seconds: float


@dataclass
class TapTempo:
    times: list[float] = field(default_factory=list)

    def tap(self, now: float) -> float | None:
        if not math.isfinite(now):
            raise ValueError("Tap time must be finite")
        if self.times and now - self.times[-1] > 3:
            self.times.clear()
        if self.times and now <= self.times[-1] + 0.05:
            return None
        self.times.append(now)
        self.times = self.times[-9:]
        if len(self.times) < 4:
            return None
        interval = median(b - a for a, b in zip(self.times, self.times[1:]))
        bpm = 60 / interval
        return bpm if 1 <= bpm <= 999 else None


def parse_bpm(value: str):
    if value.strip().lower() == "auto":
        return "auto"
    bpm = float(value)
    if not math.isfinite(bpm) or not 1 <= bpm <= 999:
        raise ValueError("Use auto or a tempo from 1 to 999 BPM")
    return bpm


def estimate_tempo(path: Path, max_seconds=60.0) -> TempoEstimate:
    if not math.isfinite(max_seconds) or max_seconds < 2:
        raise ValueError("Tempo analysis needs a window of at least 2 seconds")
    info = sf.info(path)
    waveform, rate = sf.read(
        path, frames=int(info.samplerate * max_seconds), dtype="float32", always_2d=True
    )
    waveform = waveform.mean(axis=1)
    if len(waveform) < 2 * rate:
        raise ValueError("Tempo estimation needs at least 2 seconds; enter BPM manually")
    if not np.all(np.isfinite(waveform)) or np.max(np.abs(waveform)) < 1e-7:
        raise ValueError("Tempo estimation needs audible finite audio; enter BPM manually")
    try:
        import librosa
    except ImportError as error:
        raise ValueError(
            "Automatic tempo needs the ML environment; otherwise enter BPM manually"
        ) from error
    analyzed = len(waveform) / rate
    if rate != 22050:
        divisor = math.gcd(rate, 22050)
        waveform = resample_poly(waveform, 22050 // divisor, rate // divisor)
        rate = 22050
    tempo, beats = librosa.beat.beat_track(
        y=waveform, sr=rate, hop_length=256, units="time", trim=False
    )
    bpm = float(np.asarray(tempo).reshape(-1)[0])
    if not 1 <= bpm <= 999 or len(beats) < 3:
        raise ValueError("Not enough regular beats for a tempo estimate; enter BPM manually")
    return TempoEstimate(bpm, len(beats), analyzed)

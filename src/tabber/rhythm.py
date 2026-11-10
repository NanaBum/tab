import math
from bisect import bisect_right
from dataclasses import replace

from .models import Note

SCORE_GRIDS = (16, 32, 64)


def recorded_score_grid(metadata):
    """Return the saved rhythm grid if the app supports it."""
    grid = metadata.get("score_grid")
    return grid if type(grid) is int and grid in SCORE_GRIDS else None


def lead_attacks(notes: list[Note], seconds: float) -> tuple[list[Note], int]:
    """Advance attacks up to the requested lead without introducing overlaps."""
    releases = sorted(note.end for note in notes)
    adjusted = []
    limited = 0
    for note in notes:
        target = max(0.0, note.start - seconds)
        previous_release = bisect_right(releases, note.start) - 1
        start = max(target, releases[previous_release]) if previous_release >= 0 else target
        limited += start > target
        adjusted.append(replace(note, start=start))
    return adjusted, limited


def quantize(time: float, bpm: float, subdivisions: int = 4) -> int:
    """Return a grid index; four subdivisions per beat means sixteenth notes."""
    if not math.isfinite(bpm) or bpm <= 0 or subdivisions < 1:
        raise ValueError("Tempo and subdivisions must be positive")
    if not math.isfinite(time) or time < 0:
        raise ValueError("Time must be finite and nonnegative")
    return int(time * bpm / 60 * subdivisions + 0.5)


def score_interval(note: Note, tempo: int, grid: int) -> tuple[int, int]:
    start = quantize(note.start, tempo, grid // 4)
    return start, max(start + 1, quantize(note.end, tempo, grid // 4))

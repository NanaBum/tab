import math


def quantize(time: float, bpm: float, subdivisions: int = 4) -> int:
    """Return a grid index; four subdivisions per beat means sixteenth notes."""
    if not math.isfinite(bpm) or bpm <= 0 or subdivisions < 1:
        raise ValueError("Tempo and subdivisions must be positive")
    if not math.isfinite(time) or time < 0:
        raise ValueError("Time must be finite and nonnegative")
    return int(time * bpm / 60 * subdivisions + 0.5)

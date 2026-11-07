import math
from dataclasses import dataclass

STANDARD_TUNING = (64, 59, 55, 50, 45, 40)


@dataclass(frozen=True)
class Note:
    start: float
    end: float
    pitch: int
    confidence: float = 1.0

    def __post_init__(self):
        if not all(math.isfinite(x) for x in (self.start, self.end, self.confidence)):
            raise ValueError("Note times and confidence must be finite")
        if self.start < 0 or self.end <= self.start:
            raise ValueError("Notes need nonnegative starts and positive durations")
        if not isinstance(self.pitch, int) or not 0 <= self.pitch <= 127:
            raise ValueError("Pitch must be a MIDI integer from 0 to 127")
        if not 0 <= self.confidence <= 1:
            raise ValueError("Confidence must be from 0 to 1")


@dataclass(frozen=True)
class FrettedNote:
    note: Note
    string: int
    fret: int

"""Explicit six-string open pitches, string 1 (thin) through string 6 (thick)."""

from .models import STANDARD_TUNING

PRESETS = {
    "standard": STANDARD_TUNING,
    "drop-d": (64, 59, 55, 50, 45, 38),
    "eb-standard": (63, 58, 54, 49, 44, 39),
    "d-standard": (62, 57, 53, 48, 43, 38),
}


def validate_tuning(tuning):
    pitches = tuple(tuning)
    if len(pitches) != 6 or any(type(p) is not int or not 0 <= p <= 127 for p in pitches):
        raise ValueError("Tuning needs six integer MIDI pitches from 0 to 127, string 1 to 6")
    return pitches


def parse_tuning(value):
    key = value.strip().lower()
    if key in PRESETS:
        return PRESETS[key]
    try:
        return validate_tuning(int(p.strip()) for p in key.split(","))
    except (TypeError, ValueError) as error:
        raise ValueError(
            "Choose standard, drop-d, eb-standard, d-standard, or six comma-separated MIDI pitches (string 1 to 6)"
        ) from error


def pitch_name(pitch):
    return f"{('C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B')[pitch % 12]}{pitch // 12 - 1}"

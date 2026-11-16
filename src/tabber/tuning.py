"""Explicit open pitches in physical string order, from thin to thick."""

from .models import STANDARD_TUNING

PRESETS = {
    "standard": STANDARD_TUNING,
    "drop-d": (64, 59, 55, 50, 45, 38),
    "drop-c-sharp": (63, 58, 54, 49, 44, 37),
    "eb-standard": (63, 58, 54, 49, 44, 39),
    "d-standard": (62, 57, 53, 48, 43, 38),
    "c-sharp-standard": (61, 56, 52, 47, 42, 37),
    "seven-string-standard": (*STANDARD_TUNING, 35),
    "seven-string-drop-a": (*STANDARD_TUNING, 33),
}


def validate_tuning(tuning):
    pitches = tuple(tuning)
    if len(pitches) not in (6, 7) or any(type(p) is not int or not 0 <= p <= 127 for p in pitches):
        raise ValueError("Tuning needs six or seven integer MIDI pitches from 0 to 127, thin to thick")
    return pitches


def parse_tuning(value):
    key = value.strip().lower()
    if key in PRESETS:
        return PRESETS[key]
    try:
        return validate_tuning(int(p.strip()) for p in key.split(","))
    except (TypeError, ValueError) as error:
        raise ValueError(
            f"Choose {', '.join(PRESETS)}, or six or seven comma-separated MIDI pitches (thin to thick)"
        ) from error


def recorded_tuning(metadata):
    """Restore an explicit physical-string tuning from a saved note file."""
    pitches = metadata.get("tuning_midi")
    if not isinstance(pitches, list):
        return None
    try:
        return validate_tuning(pitches)
    except ValueError:
        return None


def format_tuning(pitches):
    for name, preset in PRESETS.items():
        if pitches == preset:
            return name
    return ",".join(map(str, pitches))


def pitch_name(pitch):
    return f"{('C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B')[pitch % 12]}{pitch // 12 - 1}"

"""Compare detector event lists while preserving a preferred event's timing."""

from .evaluation import match_notes
from .models import Note


def complementary_notes(primary: list[Note], secondary: list[Note], *, tolerance=0.05):
    """Add unmatched secondary events and retain one-to-one agreements."""
    matched = dict(match_notes(primary, secondary, onset_tolerance=tolerance))
    used = set(matched.values())
    entries = [(note, index, matched.get(index)) for index, note in enumerate(primary)]
    entries.extend((note, None, index) for index, note in enumerate(secondary) if index not in used)
    return sorted(entries, key=lambda entry: entry[0].start)

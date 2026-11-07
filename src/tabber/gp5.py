"""Build editable GP5 scores on a sixteenth-note grid in 4/4."""

from pathlib import Path

import guitarpro
from guitarpro import models as gp

from .models import STANDARD_TUNING, FrettedNote
from .rhythm import quantize

# Grid cells, GP duration denominator, dotted. Largest aligned value wins.
_DURATIONS = (
    (16, 1, False),
    (12, 2, True),
    (8, 2, False),
    (6, 4, True),
    (4, 4, False),
    (3, 8, True),
    (2, 8, False),
    (1, 16, False),
)


def build_song(notes: list[FrettedNote], bpm: float) -> gp.Song:
    """Quantize a monophonic performance without changing the source records.

    GP5 stores integer tempo. Snap the score using that same rounded tempo,
    reject onsets that collide, and give short notes at least one grid cell.
    """
    quantize(0, bpm)
    tempo = int(bpm + 0.5)
    if not 1 <= tempo <= 999:
        raise ValueError("GP5 export requires a tempo from 1 to 999 BPM")
    ordered = sorted(notes, key=lambda n: n.note.start)
    events = []
    for n in ordered:
        if (
            not isinstance(n.string, int)
            or not 0 <= n.string < 6
            or not isinstance(n.fret, int)
            or not 0 <= n.fret <= 24
        ):
            raise ValueError("GP5 export needs a valid string and fret from 0 to 24")
        if STANDARD_TUNING[n.string] + n.fret != n.note.pitch:
            raise ValueError("Fingering does not match the pitch in standard tuning")
        if events and n.note.start < events[-1][2].note.end - 1e-6:
            raise ValueError("GP5 export currently supports one note at a time")
        start = quantize(n.note.start, tempo)
        end = max(start + 1, quantize(n.note.end, tempo))
        if events and start < events[-1][1]:
            raise ValueError(
                "Notes collide on the GP5 sixteenth-note grid; use a finer transcription"
            )
        events.append((start, end, n))

    song = gp.Song(title="Guitar transcription", tempo=tempo)
    song.instructions = "Draft transcription: verify notes and rhythm against the recording."
    track = song.tracks[0]
    track.name = "Guitar"
    track.channel.instrument = 24
    track.strings = [gp.GuitarString(i + 1, pitch) for i, pitch in enumerate(STANDARD_TUNING)]
    track.measures.clear()
    song.measureHeaders.clear()
    measure_count = max(1, (events[-1][1] + 15) // 16 if events else 1)
    for index in range(measure_count):
        header = gp.MeasureHeader(number=index + 1, start=960 + index * 3840)
        song.measureHeaders.append(header)
        track.measures.append(gp.Measure(track, header))

    def append_segment(start, end, fretted=None):
        first = True
        while start < end:
            bar, offset = divmod(start, 16)
            available = min(end - start, 16 - offset)
            for cells, denominator, dotted in _DURATIONS:
                base_cells = 16 // denominator
                if cells <= available and offset % base_cells == 0:
                    break
            voice = track.measures[bar].voices[0]
            beat = gp.Beat(
                voice,
                start=960 + start * 240,
                duration=gp.Duration(value=denominator, isDotted=dotted),
                status=gp.BeatStatus.rest if fretted is None else gp.BeatStatus.normal,
            )
            if fretted is not None:
                beat.notes.append(
                    gp.Note(
                        beat,
                        value=fretted.fret,
                        string=fretted.string + 1,
                        type=gp.NoteType.normal if first else gp.NoteType.tie,
                    )
                )
            voice.beats.append(beat)
            start += cells
            first = False

    cursor = 0
    for start, end, fretted in events:
        append_segment(cursor, start)
        append_segment(start, end, fretted)
        cursor = end
    append_segment(cursor, measure_count * 16)
    return song


def write_gp5(song: gp.Song, path: Path) -> None:
    guitarpro.write(song, str(path), version=(5, 1, 0))

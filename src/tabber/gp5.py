"""Build editable GP5 scores on a sixteenth-note grid in 4/4."""

import itertools
from pathlib import Path
from typing import BinaryIO

import guitarpro
from guitarpro import models as gp

from .models import STANDARD_TUNING, FrettedNote
from .rhythm import quantize


def build_song(notes: list[FrettedNote], bpm: float, grid: int = 16) -> gp.Song:
    """Quantize a performance without changing the source records.

    GP5 stores integer tempo. Snap the score using that same rounded tempo,
    reject onsets that collide, and give short notes at least one grid cell.
    """
    quantize(0, bpm)
    if grid not in (16, 32, 64):
        raise ValueError("GP5 grid must be 16, 32, or 64 divisions per whole note")
    step = 3840 // grid
    durations = sorted(
        [
            (grid // denominator, denominator, False)
            for denominator in (1, 2, 4, 8, 16, 32, 64)
            if denominator <= grid
        ]
        + [
            (3 * grid // (2 * denominator), denominator, True)
            for denominator in (2, 4, 8, 16, 32)
            if 2 * denominator <= grid
        ],
        reverse=True,
    )
    tempo = int(bpm + 0.5)
    if not 1 <= tempo <= 999:
        raise ValueError("GP5 export requires a tempo from 1 to 999 BPM")
    ordered = sorted(notes, key=lambda n: n.note.start)
    events = []
    ends_by_string = {}
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
        start = quantize(n.note.start, tempo, grid // 4)
        end = max(start + 1, quantize(n.note.end, tempo, grid // 4))
        previous = ends_by_string.get(n.string)
        if previous and n.note.start < previous[0] - 1e-6:
            raise ValueError("Overlapping notes cannot occupy the same guitar string")
        if previous and start < previous[1]:
            raise ValueError(
                f"Notes collide on the GP5 1/{grid} grid; choose --grid 32 or --grid 64"
            )
        events.append((start, end, n))
        ends_by_string[n.string] = (n.note.end, end)

    song = gp.Song(title="Guitar transcription", tempo=tempo)
    song.instructions = "Draft transcription: verify notes and rhythm against the recording."
    track = song.tracks[0]
    track.name = "Guitar"
    track.channel.instrument = 24
    track.strings = [gp.GuitarString(i + 1, pitch) for i, pitch in enumerate(STANDARD_TUNING)]
    track.measures.clear()
    song.measureHeaders.clear()
    final_cell = max((event[1] for event in events), default=1)
    measure_count = max(1, (final_cell + grid - 1) // grid)
    for index in range(measure_count):
        header = gp.MeasureHeader(number=index + 1, start=960 + index * 3840)
        song.measureHeaders.append(header)
        track.measures.append(gp.Measure(track, header))

    def append_segment(start, end, sounding):
        while start < end:
            bar, offset = divmod(start, grid)
            available = min(end - start, grid - offset)
            for cells, denominator, dotted in durations:
                base_cells = grid // denominator
                if cells <= available and offset % base_cells == 0:
                    break
            voice = track.measures[bar].voices[0]
            beat = gp.Beat(
                voice,
                start=960 + start * step,
                duration=gp.Duration(value=denominator, isDotted=dotted),
                status=gp.BeatStatus.normal if sounding else gp.BeatStatus.rest,
            )
            for onset, fretted in sorted(sounding, key=lambda item: item[1].string):
                beat.notes.append(
                    gp.Note(
                        beat,
                        value=fretted.fret,
                        string=fretted.string + 1,
                        type=gp.NoteType.normal if start == onset else gp.NoteType.tie,
                    )
                )
            voice.beats.append(beat)
            start += cells

    # A single rhythmic voice can contain chord attacks mixed with tied notes.
    # Split at every attack/release, retaining held strings through those splits.
    boundaries = sorted({0, measure_count * grid} | {t for a, b, _ in events for t in (a, b)})
    for start, end in itertools.pairwise(boundaries):
        sounding = [(onset, fretted) for onset, stop, fretted in events if onset <= start < stop]
        append_segment(start, end, sounding)
    return song


def write_gp5(song: gp.Song, path: Path | BinaryIO) -> None:
    guitarpro.write(song, str(path) if isinstance(path, Path) else path, version=(5, 1, 0))

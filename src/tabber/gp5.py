"""Build editable GP5 scores on a sixteenth-note grid in 4/4."""

import itertools
from collections import Counter
from pathlib import Path
from typing import BinaryIO

import guitarpro
from guitarpro import models as gp

from .models import STANDARD_TUNING, FrettedNote
from .rhythm import quantize
from .tuning import pitch_name, validate_tuning


def build_song(
    notes: list[FrettedNote], bpm: float, grid: int = 16, *, tuning=STANDARD_TUNING
) -> gp.Song:
    """Quantize a performance without changing the source records.

    GP5 stores integer tempo. Snap the score using that same rounded tempo,
    reject onsets that collide, and give short notes at least one grid cell.
    """
    tuning = validate_tuning(tuning)
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
        if tuning[n.string] + n.fret != n.note.pitch:
            raise ValueError("Fingering does not match the pitch in the selected tuning")
        start = quantize(n.note.start, tempo, grid // 4)
        end = max(start + 1, quantize(n.note.end, tempo, grid // 4))
        previous = ends_by_string.get(n.string)
        if previous and n.note.start < previous[0].end - 1e-6:
            raise ValueError("Overlapping notes cannot occupy the same guitar string")
        if previous and start < previous[1]:
            first = previous[0]
            recovery = (
                "Try a finer rhythm grid."
                if grid < 64
                else "Review these detections or save notes and MIDI without a tab."
            )
            raise ValueError(
                f"{pitch_name(first.pitch)} at {first.start:.3f}s and "
                f"{pitch_name(n.note.pitch)} at {n.note.start:.3f}s collide on string "
                f"{n.string + 1} on the GP5 1/{grid} grid. {recovery}"
            )
        events.append((start, end, n))
        ends_by_string[n.string] = (n.note, end)

    song = gp.Song(title="Guitar transcription", tempo=tempo)
    song.instructions = "Draft transcription: verify notes and rhythm against the recording."
    track = song.tracks[0]
    track.name = "Guitar"
    track.channel.instrument = 24
    track.strings = [gp.GuitarString(i + 1, pitch) for i, pitch in enumerate(tuning)]
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


def read_gp5(path: Path | BinaryIO) -> gp.Song:
    """Read exports with tie frets reconstructed by chronological string history.

    GP5 ties store no independent fret. PyGuitarPro 0.11 locates a beat using
    value equality (which excludes its time), so a partially read tied beat can
    match an earlier open-string tie and inherit the wrong fret. Reconstructing
    the format's continuation semantics avoids global patches to that library.
    """
    song = guitarpro.parse(str(path) if isinstance(path, Path) else path)
    for track in song.tracks:
        history = {}
        for measure in track.measures:
            for voice_index, voice in enumerate(measure.voices):
                for beat in voice.beats:
                    for note in beat.notes:
                        key = voice_index, note.string
                        if note.type == gp.NoteType.tie:
                            if key not in history:
                                raise ValueError("GP5 tie has no preceding note on its string")
                            note.value = history[key]
                        else:
                            history[key] = note.value
    return song


def score_events(song: gp.Song) -> list[tuple[int, int, int, int]]:
    """Canonical attack/end/string/fret events, including all tied segments."""
    if len(song.tracks) != 1:
        raise ValueError("Expected a single guitar track in this export")
    events, active = [], {}
    for measure in song.tracks[0].measures:
        if (
            measure.timeSignature.numerator != 4
            or measure.timeSignature.denominator.value != 4
            or any(beat.notes for voice in measure.voices[1:] for beat in voice.beats)
        ):
            raise ValueError("Unexpected meter or extra sounding voice in the GP5 export")
        beats = measure.voices[0].beats
        if sum(beat.duration.time for beat in beats) != 3840:
            raise ValueError("GP5 export contains an incomplete or overfull 4/4 measure")
        for beat in beats:
            for note in beat.notes:
                if note.type == gp.NoteType.normal:
                    event = [beat.start, beat.start + beat.duration.time, note.string, note.value]
                    events.append(event)
                    active[note.string] = event
                elif note.type == gp.NoteType.tie:
                    previous = active.get(note.string)
                    if previous is None or previous[1] != beat.start or previous[3] != note.value:
                        raise ValueError("GP5 export contains a broken sustained-note tie")
                    previous[1] += beat.duration.time
                else:
                    raise ValueError("Unexpected note type in the GP5 export")
    return [tuple(event) for event in events]


def verify_export(
    song: gp.Song, notes: list[FrettedNote], bpm: float, grid: int, *, tuning=STANDARD_TUNING
) -> None:
    tuning = validate_tuning(tuning)
    tempo = int(bpm + 0.5)
    if len(song.tracks) != 1 or tuple(s.value for s in song.tracks[0].strings) != tuning:
        raise ValueError("GP5 verification found an unexpected track or tuning")
    expected = []
    for note in notes:
        first = quantize(note.note.start, tempo, grid // 4)
        last = max(first + 1, quantize(note.note.end, tempo, grid // 4))
        expected.append(
            (960 + first * (3840 // grid), 960 + last * (3840 // grid), note.string + 1, note.fret)
        )
    if song.tempo != tempo or Counter(score_events(song)) != Counter(expected):
        raise ValueError("GP5 verification could not preserve the intended note events")


def timing_summary(song: gp.Song, notes: list[FrettedNote]) -> dict:
    """Measure saved-score movement from detections, not from reference music."""
    starts, ends = [], []
    tick_seconds = 60 / (song.tempo * 960)
    events = score_events(song)
    for string in range(6):
        original = sorted((n.note for n in notes if n.string == string), key=lambda n: n.start)
        saved = sorted((e for e in events if e[2] == string + 1), key=lambda e: e[0])
        if len(original) != len(saved):
            raise ValueError("Cannot compare timing when score note counts differ")
        for note, (first, last, _, fret) in zip(original, saved):
            if note.pitch != song.tracks[0].strings[string].value + fret:
                raise ValueError("Cannot compare timing when score pitches differ")
            starts.append(abs((first - 960) * tick_seconds - note.start) * 1000)
            ends.append(abs((last - 960) * tick_seconds - note.end) * 1000)
    return {
        "note_count": len(starts),
        "score_bpm": song.tempo,
        "maximum_start_shift_ms": max(starts, default=0),
        "maximum_end_shift_ms": max(ends, default=0),
        "starts_moved_over_50ms": sum(value > 50 + 1e-6 for value in starts),
        "meaning": "Absolute movement from detected timing; not error against the original performance",
    }

import io
import random

import pytest

from tabber.gp5 import build_song, read_gp5, score_events, verify_export, write_gp5
from tabber.models import STANDARD_TUNING, FrettedNote, Note


@pytest.mark.parametrize("grid", [16, 32, 64])
@pytest.mark.parametrize("bpm", [80, 129.4])
def test_generated_polyphonic_scores_preserve_every_attack_and_sustain(grid, bpm):
    generator = random.Random(42)
    cell_seconds = 60 / int(bpm + 0.5) * 4 / grid
    notes = []
    for string, open_pitch in enumerate(STANDARD_TUNING):
        cursor = 0
        for _ in range(6):
            cursor += generator.randrange(3)
            duration = generator.randrange(1, 13)
            fret = generator.randrange(13)
            notes.append(
                FrettedNote(
                    Note(
                        cursor * cell_seconds, (cursor + duration) * cell_seconds, open_pitch + fret
                    ),
                    string,
                    fret,
                )
            )
            cursor += duration
    stream = io.BytesIO()
    write_gp5(build_song(notes, bpm, grid), stream)
    stream.seek(0)
    reread = read_gp5(stream)
    verify_export(reread, notes, bpm, grid)
    assert len(score_events(reread)) == len(notes)


def test_validation_rejects_wrong_tuning_even_when_fret_values_match():
    notes = [FrettedNote(Note(0, 1, 64), 0, 0)]
    score = build_song(notes, 120)
    score.tracks[0].strings[0].value = 63
    with pytest.raises(ValueError, match="tuning"):
        verify_export(score, notes, 120, 16)

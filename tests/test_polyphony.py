import guitarpro
import pytest
from guitarpro import models as gp

from tabber import fretting
from tabber.export import write_outputs
from tabber.fretting import assign_polyphonic_frets, recover_overlapping_notes
from tabber.models import STANDARD_TUNING, Note


def test_six_open_strings_form_a_valid_chord():
    notes = [Note(0, 1, pitch) for pitch in STANDARD_TUNING]
    assigned = assign_polyphonic_frets(notes, max_span=0)
    assert len(assigned) == 6
    assert {n.string for n in assigned} == set(range(6))
    assert all(n.fret == 0 for n in assigned)


def test_sustained_notes_reserve_their_strings():
    notes = [Note(0, 2, 40), Note(0.5, 1, 64), Note(1, 1.5, 65)]
    assigned = assign_polyphonic_frets(notes)
    assert len(assigned) == len(notes)
    assert assigned[0].string == 5
    assert all(n.string != 5 for n in assigned[1:])
    assert [STANDARD_TUNING[n.string] + n.fret for n in assigned] == [40, 64, 65]


def test_unplayable_seven_voice_chord_fails_without_dropping_notes():
    notes = [Note(0, 1, pitch) for pitch in (40, 45, 50, 55, 59, 64, 67)]
    with pytest.raises(ValueError, match="no notes were dropped"):
        assign_polyphonic_frets(notes)


def test_recovery_reuses_unchanged_beam_without_changing_edits(monkeypatch):
    notes = [Note(i / 4, i / 4 + 0.1, 60 + i % 5) for i in range(65)]
    notes.append(Note(17, 19, 40, 0.1))
    notes.extend(Note(18, 19, pitch) for pitch in STANDARD_TUNING)
    notes.append(Note(18, 19, 67, 0.1))
    priors = [(2, 1, 1, 1, 1, 1)] * len(notes)
    options = {
        "tuning": STANDARD_TUNING,
        "max_span": 5,
        "string_priors": priors,
        "score_grid": (120, 64),
    }
    resumed = []
    restart = fretting._SearchCheckpoints.restart

    def trace(cache, ordered, initial):
        index, states = restart(cache, ordered, initial)
        resumed.append(index)
        return index, states

    monkeypatch.setattr(fretting._SearchCheckpoints, "restart", trace)
    cached = recover_overlapping_notes(notes, **options)
    assert any(index >= 64 for index in resumed)
    assert cached[1][65].end == 18
    assert len(cached[1]) == len(notes) - 1

    def full_search(*args, _checkpoints, **kwargs):
        return assign_polyphonic_frets(*args, **kwargs)

    monkeypatch.setattr(fretting, "assign_polyphonic_frets", full_search)
    assert cached == recover_overlapping_notes(notes, **options)


def test_chord_export_preserves_independent_attacks_and_durations(tmp_path):
    notes = [Note(0, 2.5, 40), Note(0, 0.5, 64), Note(0.5, 1, 65), Note(1.5, 2, 67)]
    assigned = assign_polyphonic_frets(notes)
    write_outputs(assigned, tmp_path / "chords", 120)
    score = guitarpro.parse(str(tmp_path / "chords/tab.gp5"))
    attacks, durations = [], {}
    for measure in score.tracks[0].measures:
        assert sum(b.duration.time for b in measure.voices[0].beats) == 3840
        for beat in measure.voices[0].beats:
            for note in beat.notes:
                pitch = score.tracks[0].strings[note.string - 1].value + note.value
                if note.type == gp.NoteType.normal:
                    attacks.append((beat.start, pitch))
                durations[pitch] = durations.get(pitch, 0) + beat.duration.time
    assert sorted(attacks) == [(960, 40), (960, 64), (1920, 65), (3840, 67)]
    assert durations == {40: 4800, 64: 960, 65: 960, 67: 960}

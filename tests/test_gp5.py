import guitarpro
import pytest
from guitarpro import models as gp

from tabber.export import write_outputs
from tabber.gp5 import build_song, read_gp5, write_gp5
from tabber.models import FrettedNote, Note


def roundtrip(tmp_path, notes, bpm=120):
    path = tmp_path / "score.gp5"
    write_gp5(build_song(notes, bpm), path)
    return guitarpro.parse(str(path))


def test_gp5_roundtrip_preserves_measures_rests_frets_and_ties(tmp_path):
    # Initial eighth rest, a note crossing a bar, then a different string.
    original = [FrettedNote(Note(0.25, 2.25, 64), 0, 0), FrettedNote(Note(2.5, 2.75, 62), 1, 3)]
    song = roundtrip(tmp_path, original)
    track = song.tracks[0]
    assert song.tempo == 120
    assert len(track.measures) == 2
    assert [s.value for s in track.strings] == [64, 59, 55, 50, 45, 40]
    sounded = []
    for measure in track.measures:
        beats = measure.voices[0].beats
        assert sum(b.duration.time for b in beats) == 3840
        for b in beats:
            for n in b.notes:
                sounded.append((b.start, b.duration.time, n.string, n.value, n.type))
    assert track.measures[0].voices[0].beats[0].status == gp.BeatStatus.rest
    onsets = [n for n in sounded if n[-1] == gp.NoteType.normal]
    assert [(n[0], n[2], n[3]) for n in onsets] == [(1440, 1, 0), (5760, 2, 3)]
    assert any(n[-1] == gp.NoteType.tie and n[0] == 4800 for n in sounded)
    assert sum(n[1] for n in sounded if n[2] == 1) == 3840
    assert original[0].note.end == 2.25


def test_repeated_notes_are_separate_attacks(tmp_path):
    notes = [FrettedNote(Note(0, 0.5, 64), 0, 0), FrettedNote(Note(0.5, 1, 64), 0, 0)]
    song = roundtrip(tmp_path, notes)
    attacks = [
        n
        for b in song.tracks[0].measures[0].voices[0].beats
        for n in b.notes
        if n.type == gp.NoteType.normal
    ]
    assert len(attacks) == 2


def test_dotted_duration_and_integer_tempo(tmp_path):
    song = roundtrip(tmp_path, [FrettedNote(Note(0, 0.375, 64), 0, 0)], bpm=120.1)
    beat = song.tracks[0].measures[0].voices[0].beats[0]
    assert song.tempo == 120
    assert beat.duration.isDotted
    assert beat.duration.value == 8


def test_empty_song_is_one_bar_of_rest(tmp_path):
    song = roundtrip(tmp_path, [])
    beats = song.tracks[0].measures[0].voices[0].beats
    assert len(beats) == 1
    assert beats[0].status == gp.BeatStatus.rest
    assert beats[0].duration.time == 3840


@pytest.mark.parametrize(
    "notes",
    [
        [FrettedNote(Note(0, 1, 64), 6, 0)],
        [FrettedNote(Note(0, 1, 64), 0, 2)],
        [FrettedNote(Note(0, 1, 64), 0, 0), FrettedNote(Note(0.5, 1.5, 64), 0, 0)],
        [FrettedNote(Note(0, 0.01, 64), 0, 0), FrettedNote(Note(0.02, 0.03, 64), 0, 0)],
    ],
)
def test_invalid_score_is_rejected_before_writing(tmp_path, notes):
    with pytest.raises(ValueError):
        write_outputs(notes, tmp_path / "invalid", 120)
    assert not (tmp_path / "invalid").exists()


def test_finer_grid_preserves_fast_attacks(tmp_path):
    notes = [FrettedNote(Note(0, 0.04, 64), 0, 0), FrettedNote(Note(0.05, 0.1, 65), 0, 1)]
    with pytest.raises(ValueError, match="collide"):
        build_song(notes, 120)
    write_outputs(notes, tmp_path / "fast", 120, grid=32)
    song = guitarpro.parse(str(tmp_path / "fast/tab.gp5"))
    attacks = [
        (b.start, n.value)
        for b in song.tracks[0].measures[0].voices[0].beats
        for n in b.notes
        if n.type == gp.NoteType.normal
    ]
    assert attacks == [(960, 0), (1080, 1)]


def test_finest_grid_reports_both_conflicting_attacks():
    notes = [
        FrettedNote(Note(0.001, 0.002, 64), 0, 0),
        FrettedNote(Note(0.002, 0.010, 65), 0, 1),
    ]
    with pytest.raises(ValueError, match=r"E4 at 0\.001s and F4 at 0\.002s collide on string 1") as exc:
        build_song(notes, 120, grid=64)
    assert "save notes and MIDI" in str(exc.value)


def test_export_render_failure_preserves_existing_outputs(tmp_path, monkeypatch):
    target = tmp_path / "existing"
    target.mkdir()
    (target / "notes.json").write_text("previous result", encoding="utf-8")

    def fail(*args):
        raise ValueError("Cannot encode score")

    monkeypatch.setattr("tabber.export.write_gp5", fail)
    with pytest.raises(ValueError, match="Cannot encode"):
        write_outputs([FrettedNote(Note(0, 1, 64), 0, 0)], target, 120)
    assert (target / "notes.json").read_text() == "previous result"
    assert sorted(p.name for p in target.iterdir()) == ["notes.json"]


def test_tied_fretted_note_after_an_earlier_open_string_tie(tmp_path):
    # The earlier open-string tied beat equals the partially read later beat in
    # PyGuitarPro 0.11 (start is excluded from equality). Plain parse inherits 0.
    notes = [
        FrettedNote(Note(0, 0.25, 59), 1, 0),
        FrettedNote(Note(0, 0.125, 64), 0, 0),
        FrettedNote(Note(0.5, 1.125, 73), 1, 14),
    ]
    path = tmp_path / "tie-regression.gp5"
    write_gp5(build_song(notes, 120), path)
    score = read_gp5(path)
    tied = [
        (beat.start, n.string, n.value)
        for beat in score.tracks[0].measures[0].voices[0].beats
        for n in beat.notes
        if n.type == gp.NoteType.tie
    ]
    assert tied == [(1200, 2, 0), (2880, 2, 14)]


def test_export_rejects_a_valid_file_that_changed_the_intended_pitch(tmp_path, monkeypatch):
    def wrong_writer(song, stream):
        wrong = build_song([FrettedNote(Note(0, 1, 65), 0, 1)], 120)
        write_gp5(wrong, stream)

    monkeypatch.setattr("tabber.export.write_gp5", wrong_writer)
    target = tmp_path / "corrupt"
    with pytest.raises(ValueError, match="verification"):
        write_outputs([FrettedNote(Note(0, 1, 64), 0, 0)], target, 120)
    assert not target.exists()

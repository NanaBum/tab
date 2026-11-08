import guitarpro
import pytest
from guitarpro import models as gp

from tabber.gp5 import build_song, read_gp5
from tabber.models import FrettedNote, Note
from tabber.playback import measure_playback
from tabber.reference import extract_reference


def headers(count):
    return [gp.MeasureHeader(number=i + 1, start=960 + i * 3840) for i in range(count)]


def indices(source):
    return [row["source_measure_index"] for row in measure_playback(source)]


def test_simple_repeat_and_one_measure_repeat_keep_source_unchanged():
    source = headers(2)
    source[0].isRepeatOpen = True
    source[1].repeatClose = 1
    assert indices(source) == [0, 1, 0, 1]
    assert source[1].repeatClose == 1
    assert [header.start for header in source] == [960, 4800]
    single = headers(1)
    single[0].isRepeatOpen, single[0].repeatClose = True, 2
    assert indices(single) == [0, 0, 0]


def test_nested_plain_repeats_restart_the_inner_pass_each_outer_iteration():
    source = headers(4)
    source[0].isRepeatOpen = source[1].isRepeatOpen = True
    source[2].repeatClose = source[3].repeatClose = 1
    assert indices(source) == [0, 1, 2, 1, 2, 3, 0, 1, 2, 1, 2, 3]


def test_first_and_second_endings_skip_the_other_ending_without_elapsed_time():
    source = headers(3)
    source[0].isRepeatOpen = True
    source[1].repeatClose, source[1].repeatAlternative = 1, 1
    source[2].repeatAlternative = 2
    assert indices(source) == [0, 1, 0, 2]


def test_explicit_masks_can_cover_multiple_measures():
    source = headers(5)
    source[0].isRepeatOpen = True
    source[1].repeatAlternative = source[2].repeatAlternative = 1
    source[2].repeatClose = 1
    source[3].repeatAlternative = source[4].repeatAlternative = 2
    assert indices(source) == [0, 1, 2, 0, 3, 4]


def test_initial_implicit_repeat_start_is_supported_but_later_ones_need_markers():
    source = headers(4)
    source[1].repeatClose = 1
    assert indices(source) == [0, 1, 0, 1, 2, 3]
    source[3].repeatClose = 1
    with pytest.raises(ValueError, match="explicit opening"):
        indices(source)


def test_repeat_expansion_is_bounded_and_unclosed_markers_fail():
    source = headers(2)
    source[0].isRepeatOpen = True
    with pytest.raises(ValueError, match="no closing"):
        indices(source)
    source[1].repeatClose = 8
    with pytest.raises(ValueError, match="measure limit"):
        measure_playback(source, max_measures=10)


@pytest.mark.parametrize(
    "extension,version", [("gp3", (3, 0, 0)), ("gp4", (4, 0, 6)), ("gp5", (5, 1, 0))]
)
def test_repeat_and_tempo_reset_roundtrip_matches_native_tuxguitar_oracle(
    tmp_path, extension, version
):
    song = build_song([FrettedNote(Note(0, 2, 64), 0, 0), FrettedNote(Note(2, 4, 66), 0, 2)], 120)
    song.measureHeaders[0].isRepeatOpen = True
    song.measureHeaders[1].repeatClose = 1
    song.tracks[0].measures[1].voices[0].beats[0].effect.mixTableChange = gp.MixTableChange(
        tempo=gp.MixTableItem(value=60)
    )
    path = tmp_path / f"repeat.{extension}"
    guitarpro.write(song, str(path), version=version)
    parsed = read_gp5(path)
    with pytest.raises(ValueError, match="Unfold"):
        extract_reference(parsed)
    result = extract_reference(parsed, unfold_repeats=True)
    # Independently observed in TuxGuitar's MIDI export of the GP5 fixture.
    assert [(note.start, note.pitch) for note in result.notes] == [
        (0, 64),
        (2, 66),
        (6, 64),
        (8, 66),
    ]
    assert [note.end for note in result.notes] == [2, 6, 8, 12]


@pytest.mark.parametrize(
    "extension,version", [("gp3", (3, 0, 0)), ("gp4", (4, 0, 6)), ("gp5", (5, 1, 0))]
)
def test_first_second_ending_file_roundtrip(tmp_path, extension, version):
    song = build_song([FrettedNote(Note(i * 2, i * 2 + 2, 64 + i), 0, i) for i in range(3)], 120)
    song.measureHeaders[0].isRepeatOpen = True
    song.measureHeaders[1].repeatClose = 1
    song.measureHeaders[1].repeatAlternative = 1
    song.measureHeaders[2].repeatAlternative = 2
    path = tmp_path / f"endings.{extension}"
    guitarpro.write(song, str(path), version=version)
    result = extract_reference(read_gp5(path), unfold_repeats=True)
    assert [(note.start, note.pitch) for note in result.notes] == [
        (0, 64),
        (2, 65),
        (4, 64),
        (6, 66),
    ]


def test_ties_survive_repeat_occurrences_without_creating_extra_attacks():
    song = build_song([FrettedNote(Note(0, 4, 64), 0, 0)], 120)
    song.measureHeaders[0].isRepeatOpen = True
    song.measureHeaders[1].repeatClose = 1
    result = extract_reference(song, unfold_repeats=True)
    assert result.notes == [Note(0, 4, 64), Note(4, 8, 64)]


def test_tempo_and_alternate_endings_are_not_combined_without_verification():
    song = build_song([FrettedNote(Note(i * 2, i * 2 + 2, 64 + i), 0, i) for i in range(3)], 120)
    song.measureHeaders[0].isRepeatOpen = True
    song.measureHeaders[1].repeatClose, song.measureHeaders[1].repeatAlternative = 1, 1
    song.measureHeaders[2].repeatAlternative = 2
    song.tracks[0].measures[1].voices[0].beats[0].effect.mixTableChange = gp.MixTableChange(
        tempo=gp.MixTableItem(value=60)
    )
    with pytest.raises(ValueError, match="further playback verification"):
        extract_reference(song, unfold_repeats=True)


def test_conditional_tie_with_different_branch_pitch_is_not_guessed():
    song = build_song([FrettedNote(Note(0, 2, 64), 0, 0), FrettedNote(Note(2, 6, 65), 0, 1)], 120)
    song.measureHeaders[0].isRepeatOpen = True
    song.measureHeaders[1].repeatClose, song.measureHeaders[1].repeatAlternative = 1, 1
    song.measureHeaders[2].repeatAlternative = 2
    with pytest.raises(ValueError, match="conditional tie"):
        extract_reference(song, unfold_repeats=True)


def test_unlabelled_ending_continuation_is_explicitly_refused():
    source = headers(3)
    source[0].isRepeatOpen = True
    source[1].repeatAlternative = 1
    source[2].repeatClose = 1
    with pytest.raises(ValueError, match="explicit ending mask"):
        indices(source)

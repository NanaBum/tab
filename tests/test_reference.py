import json

import guitarpro
import pytest
from guitarpro import models as gp

from scripts.compare_timed_events import main as compare_main
from scripts.import_reference_tab import main
from tabber.events import load_events
from tabber.gp5 import build_song, read_gp5
from tabber.models import FrettedNote, Note
from tabber.reference import extract_reference


def add_beat(
    track, tick, *, duration=4, string=1, fret=0, voice=0, measure=0, kind=gp.NoteType.normal
):
    target = track.measures[measure].voices[voice]
    beat = gp.Beat(
        target, start=tick, duration=gp.Duration(value=duration), status=gp.BeatStatus.normal
    )
    beat.notes.append(gp.Note(beat, string=string, value=fret, type=kind))
    target.beats.append(beat)
    return beat


def test_reference_keeps_ties_across_mixed_meters_and_independent_voices():
    song = gp.Song(tempo=120)
    first = gp.MeasureHeader(number=1, start=960)
    first.timeSignature.numerator = 3
    second = gp.MeasureHeader(number=2, start=3840)
    second.timeSignature.numerator = 5
    song.measureHeaders = [first, second]
    track = song.tracks[0]
    track.measures = [gp.Measure(track, header) for header in song.measureHeaders]
    add_beat(track, 960, duration=2)
    add_beat(track, 2880, kind=gp.NoteType.tie)
    add_beat(track, 3840, kind=gp.NoteType.tie, measure=1)
    add_beat(track, 960, string=2, voice=1)
    result = extract_reference(song)
    assert result.notes == [Note(0, 2, 64), Note(0, 0.5, 59)]
    assert [event["voice"] for event in result.metadata["source_events"]] == [0, 1]


def test_multitrack_selection_and_global_tempo_change_inside_held_note(tmp_path):
    song = gp.Song(tempo=120)
    change = add_beat(song.tracks[0], 1920)
    change.effect.mixTableChange = gp.MixTableChange(tempo=gp.MixTableItem(value=60))
    second = gp.Track(song, number=2, name="Second guitar")
    song.tracks.append(second)
    add_beat(second, 960, duration=2, fret=3)
    with pytest.raises(ValueError, match="Choose a track"):
        extract_reference(song)
    result = extract_reference(song, track_number=2)
    assert result.notes == [Note(0, 1.5, 67)]
    assert [change["bpm"] for change in result.metadata["tempo_map"]] == [120, 60]
    voice = song.tracks[0].measures[0].voices[0]
    voice.beats.insert(
        0, gp.Beat(voice, start=960, duration=gp.Duration(value=4), status=gp.BeatStatus.rest)
    )
    source = tmp_path / "tempo.gp5"
    guitarpro.write(song, str(source))
    assert extract_reference(read_gp5(source), track_number=2).notes == result.notes


def test_custom_tuning_and_capo_are_applied_without_reassigning_frets():
    song = gp.Song(tempo=120)
    track = song.tracks[0]
    track.strings[0].value = 62
    track.offset = 2
    add_beat(track, 960, fret=3)
    result = extract_reference(song)
    assert result.notes == [Note(0, 0.5, 67)]
    assert result.metadata["source_events"][0]["fret"] == 3
    assert result.metadata["capo"] == 2


@pytest.mark.parametrize(
    "field,value",
    [("repeatClose", 1), ("repeatAlternative", 1), ("tripletFeel", gp.TripletFeel.eighth)],
)
def test_playback_order_and_swing_are_not_silently_flattened(field, value):
    song = gp.Song()
    setattr(song.measureHeaders[0], field, value)
    add_beat(song.tracks[0], 960)
    with pytest.raises(ValueError, match="Unfold|Swing"):
        extract_reference(song)


def test_technique_approximation_requires_opt_in_and_keeps_source_details():
    song = gp.Song()
    add_beat(song.tracks[0], 960).notes[0].effect.palmMute = True
    with pytest.raises(ValueError, match="palmMute"):
        extract_reference(song)
    result = extract_reference(song, allow_approximate_techniques=True)
    assert len(result.notes) == 1
    assert result.metadata["approximate_techniques"] is True
    assert result.metadata["source_events"][0]["technique_details"]["palmMute"] == "True"


def test_gradual_tempo_and_broken_tie_fail_explicitly():
    song = gp.Song()
    beat = add_beat(song.tracks[0], 960)
    beat.effect.mixTableChange = gp.MixTableChange(tempo=gp.MixTableItem(value=90, duration=2))
    with pytest.raises(ValueError, match="Gradual tempo"):
        extract_reference(song)
    beat.effect.mixTableChange = None
    beat.notes[0].type = gp.NoteType.tie
    with pytest.raises(ValueError, match="broken"):
        extract_reference(song)


@pytest.mark.parametrize(
    "extension,version", [("gp3", (3, 0, 0)), ("gp4", (4, 0, 6)), ("gp5", (5, 1, 0))]
)
def test_local_file_import_preserves_source_and_can_feed_timed_comparison(
    tmp_path, monkeypatch, extension, version
):
    source = tmp_path / f"reference.{extension}"
    output = tmp_path / "events.json"
    notes = [FrettedNote(Note(0, 2.5, 40), 5, 0), FrettedNote(Note(0.5, 1, 64), 0, 0)]
    guitarpro.write(build_song(notes, 120), str(source), version=version)
    original = source.read_bytes()
    monkeypatch.setattr("sys.argv", ["import", str(source), "--output", str(output)])
    main()
    assert source.read_bytes() == original
    assert load_events(output) == [note.note for note in notes]
    metadata = json.loads(output.read_text())["metadata"]
    assert metadata["data_permission"] == "Not assessed by this importer"
    assert len(metadata["source_sha256"]) == 64
    report = tmp_path / "comparison.json"
    monkeypatch.setattr("sys.argv", ["compare", str(output), str(output), "--output", str(report)])
    compare_main()
    assert (
        json.loads(report.read_text())["inputs"]["reference"]["reference_metadata"][
            "data_permission"
        ]
        == "Not assessed by this importer"
    )


def test_malformed_tab_produces_an_import_error_without_an_output(tmp_path, monkeypatch):
    source = tmp_path / "bad.gp5"
    source.write_bytes(b"not a Guitar Pro file")
    output = tmp_path / "events.json"
    monkeypatch.setattr("sys.argv", ["import", str(source), "--output", str(output)])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 1
    assert not output.exists()

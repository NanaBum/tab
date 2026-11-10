import json

import mido
import pytest

from scripts.import_midi_reference import main
from tabber.events import load_events
from tabber.media import sha256_file
from tabber.midi_reference import describe_midi, extract_midi_reference
from tabber.models import Note
from tabber.pitch_midi import write_pitch_midi


def source_midi():
    midi = mido.MidiFile(type=1, ticks_per_beat=480)
    tempo, guitar = mido.MidiTrack(), mido.MidiTrack()
    tempo.append(mido.MetaMessage("set_tempo", tempo=1000000, time=480))
    guitar.extend(
        [
            mido.MetaMessage("track_name", name="Guitar"),
            mido.Message("program_change", channel=0, program=27),
            mido.Message("note_on", note=64, velocity=80),
            mido.Message("note_off", note=64, time=960),
        ]
    )
    midi.tracks.extend([tempo, guitar])
    return midi


def test_global_tempo_changes_inside_held_notes_and_velocity_zero_releases():
    midi = source_midi()
    midi.tracks[1][-1] = mido.Message("note_on", note=64, velocity=0, time=960)
    result = extract_midi_reference(midi)
    assert result.notes == [Note(0, 1.5, 64)]
    assert result.metadata["track"] == 2
    assert result.metadata["channel_descriptions"][0]["programs_zero_based"] == [27]
    assert result.metadata["source_events"][0]["end_tick"] == 960


def test_type_zero_mixed_instruments_need_explicit_channels():
    midi = mido.MidiFile(type=0, ticks_per_beat=480)
    midi.tracks.append(
        mido.MidiTrack(
            [
                mido.Message("note_on", note=64, channel=0),
                mido.Message("note_on", note=43, channel=1),
                mido.Message("note_off", note=64, channel=0, time=480),
                mido.Message("note_off", note=43, channel=1),
            ]
        )
    )
    with pytest.raises(ValueError, match="channels explicitly"):
        extract_midi_reference(midi)
    assert extract_midi_reference(midi, channels=(1,)).notes == [Note(0, 0.5, 64)]
    assert len(describe_midi(midi)[0]["channels"]) == 2


def test_multiple_sounding_tracks_need_explicit_selection():
    midi = source_midi()
    midi.tracks.append(
        mido.MidiTrack(
            [
                mido.Message("note_on", note=40, channel=1),
                mido.Message("note_off", note=40, channel=1, time=480),
            ]
        )
    )
    with pytest.raises(ValueError, match="track explicitly"):
        extract_midi_reference(midi)
    assert extract_midi_reference(midi, track_number=2).notes[0].pitch == 64


def test_empty_midi_cannot_be_a_successful_reference():
    midi = mido.MidiFile()
    midi.tracks.append(mido.MidiTrack())
    with pytest.raises(ValueError, match="no sounding"):
        extract_midi_reference(midi)


def test_same_channel_unison_ambiguity_is_not_silently_paired():
    midi = source_midi()
    midi.tracks[1].insert(-1, mido.Message("note_on", note=64, time=10))
    with pytest.raises(ValueError, match="ambiguous releases"):
        extract_midi_reference(midi)


def test_independent_channel_unisons_keep_their_own_release_times(tmp_path):
    notes = [Note(0, 1, 64), Note(0.25, 0.5, 64)]
    write_pitch_midi(notes, tmp_path, 120)
    midi = mido.MidiFile(tmp_path / "notes.mid")
    assert extract_midi_reference(midi, channels=(1, 2)).notes == notes


def test_shared_channel_across_tracks_is_not_silently_assigned_to_one_instrument():
    midi = source_midi()
    midi.tracks.append(
        mido.MidiTrack(
            [mido.Message("note_on", note=43), mido.Message("note_off", note=43, time=480)]
        )
    )
    with pytest.raises(ValueError, match="channel ownership"):
        extract_midi_reference(midi, track_number=2)


@pytest.mark.parametrize("kind", ["pitchwheel", "pedal", "portamento"])
def test_expression_requires_explicit_approximation_and_retains_flags(kind):
    midi = source_midi()
    message = (
        mido.Message("pitchwheel", pitch=4096, time=240)
        if kind == "pitchwheel"
        else mido.Message(
            "control_change", control=64 if kind == "pedal" else 65, value=127, time=240
        )
    )
    midi.tracks[0].insert(0, message)  # Same channel, different physical MIDI track.
    with pytest.raises(ValueError, match="approximate-expression"):
        extract_midi_reference(midi)
    result = extract_midi_reference(midi, allow_approximate_expression=True)
    assert result.metadata["approximate_techniques"] is True
    assert result.metadata["expression_events"][0]["track"] == 1
    assert result.notes[0].pitch == 64


@pytest.mark.parametrize(
    "problem",
    ["dangling", "orphan-release", "zero-duration", "tempo-conflict", "percussion", "type2"],
)
def test_ambiguous_or_unsupported_inputs_fail(problem):
    midi = source_midi()
    if problem == "dangling":
        midi.tracks[1].pop()
    elif problem == "orphan-release":
        midi.tracks[1].pop(2)
    elif problem == "zero-duration":
        midi.tracks[1][-1].time = 0
    elif problem == "tempo-conflict":
        midi.tracks[0].append(mido.MetaMessage("set_tempo", tempo=500000))
    elif problem == "percussion":
        for message in midi.tracks[1]:
            if hasattr(message, "channel"):
                message.channel = 9
    else:
        midi.type = 2
    with pytest.raises(ValueError):
        extract_midi_reference(midi)


def test_cli_saved_roundtrip_preserves_source_and_existing_output_on_failure(tmp_path, monkeypatch):
    source, output = tmp_path / "source.mid", tmp_path / "labels.json"
    midi = source_midi()
    midi.save(source)
    original = source.read_bytes()
    monkeypatch.setattr("sys.argv", ["import_midi_reference", str(source), "--output", str(output)])
    main()
    assert load_events(output) == [Note(0, 1.5, 64)] and source.read_bytes() == original
    saved = output.read_bytes()
    midi.tracks[1].pop()
    midi.save(source)
    with pytest.raises(SystemExit):
        main()
    assert output.read_bytes() == saved


def test_pair_provenance_warnings_and_training_exclusion_survive_label_import(
    tmp_path, monkeypatch
):
    source, output, pair = tmp_path / "score.mid", tmp_path / "labels.json", tmp_path / "pair.json"
    source_midi().save(source)
    payload = {
        "format": "tabber-training-pair",
        "schema_version": 1,
        "song_id": "fixture-song",
        "roles": {"score_midi": "score.mid"},
        "assets": [
            {"path": "score.mid", "sha256": sha256_file(source), "bytes": source.stat().st_size}
        ],
        "tab_warnings": {"midi": ["candidate conversion warning"]},
        "excluded_from_training": True,
    }
    pair.write_text(json.dumps(payload))
    monkeypatch.setattr(
        "sys.argv",
        [
            "import_midi_reference",
            str(source),
            "--pair-manifest",
            str(pair),
            "--output",
            str(output),
        ],
    )
    main()
    metadata = json.loads(output.read_text())["metadata"]
    assert metadata["source_pair"]["excluded_from_training"] is True
    assert metadata["source_pair"]["tab_warnings"] == payload["tab_warnings"]
    before = output.read_bytes()
    payload["assets"][0]["sha256"] = "0" * 64
    pair.write_text(json.dumps(payload))
    with pytest.raises(SystemExit):
        main()
    assert output.read_bytes() == before

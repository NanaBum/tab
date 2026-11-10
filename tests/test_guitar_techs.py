import mido

from tabber.guitar_techs import STRING_NAMES, string_notes


def test_guitar_techs_keeps_unisons_on_shared_channel_separate_across_tempo_change():
    midi = mido.MidiFile(type=1, ticks_per_beat=480)
    for name in reversed(STRING_NAMES):
        midi.add_track(name)
    high_e, b = midi.tracks[-1], midi.tracks[-2]
    high_e.extend(
        [
            mido.Message("note_on", channel=0, note=64, velocity=80, time=240),
            mido.MetaMessage("set_tempo", tempo=1_000_000, time=240),
            mido.Message("note_off", channel=0, note=64, time=480),
        ]
    )
    b.extend(
        [
            mido.Message("note_on", channel=0, note=64, velocity=80, time=240),
            mido.Message("note_off", channel=0, note=64, time=480),
        ]
    )
    notes = string_notes(midi)
    assert [(n["pitch"], n["string"], n["fret"]) for n in notes] == [(64, 0, 0), (64, 1, 5)]
    assert [(n["start"], n["end"]) for n in notes] == [(0.25, 1.5), (0.25, 1.0)]

import itertools
import json

import mido
import numpy as np
import pytest
import soundfile as sf

from tabber.export import write_outputs
from tabber.fretting import assign_frets
from tabber.models import STANDARD_TUNING, Note
from tabber.rhythm import quantize
from tabber.transcribe import transcribe


def test_scale_positions_reproduce_every_pitch():
    pitches = [60, 62, 64, 65, 67, 69, 71, 72]
    notes = [Note(i * 0.5, i * 0.5 + 0.4, p) for i, p in enumerate(pitches)]
    result = assign_frets(notes)
    assert [STANDARD_TUNING[n.string] + n.fret for n in result] == pitches
    assert max(abs(a.fret - b.fret) for a, b in itertools.pairwise(result)) <= 5


def test_fretting_rejects_chords_and_unplayable_notes():
    with pytest.raises(ValueError, match="Overlapping"):
        assign_frets([Note(0, 1, 60), Note(0, 1, 64)])
    with pytest.raises(ValueError, match="playable range"):
        assign_frets([Note(0, 1, 20)])
    assert assign_frets([]) == []


def test_synthetic_audio_to_tab_and_midi(tmp_path):
    rate = 22050
    pitches = [40, 45, 50, 55, 59, 64, 72]
    t = np.arange(int(0.4 * rate)) / rate
    parts = []
    for pitch in pitches:
        f = 440 * 2 ** ((pitch - 69) / 12)
        parts.extend((0.3 * np.sin(2 * np.pi * f * t), np.zeros(int(0.15 * rate))))
    audio = tmp_path / "scale.wav"
    sf.write(audio, np.concatenate(parts), rate)
    notes = transcribe(audio)
    assert [n.pitch for n in notes] == pitches
    output = tmp_path / "result"
    write_outputs(assign_frets(notes), output, 120)
    assert len(json.loads((output / "notes.json").read_text())["notes"]) == len(pitches)
    midi = mido.MidiFile(output / "notes.mid")
    assert [msg.note for msg in midi.tracks[0] if msg.type == "note_on"] == pitches
    assert (output / "tab.txt").read_text().count("|") >= 12


def test_silence_and_short_audio(tmp_path):
    for size in (0, 100, 22050):
        path = tmp_path / f"silence{size}.wav"
        sf.write(path, np.zeros(size), 22050)
        assert transcribe(path) == []


@pytest.mark.parametrize("bpm", [0, -1, float("nan"), float("inf")])
def test_invalid_tempo(bpm):
    with pytest.raises(ValueError):
        quantize(0, bpm)


def test_note_validation():
    with pytest.raises(ValueError):
        Note(0, 0, 60)
    with pytest.raises(ValueError):
        Note(0, float("nan"), 60)
    assert quantize(0.5, 120) == 4

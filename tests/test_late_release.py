import numpy as np
import pytest
import soundfile as sf

from tabber.fretting import assign_polyphonic_frets
from tabber.late_release import repair_late_releases
from tabber.models import STANDARD_TUNING, Note


@pytest.mark.parametrize("rings", [True, False])
def test_wide_chord_retry_requires_audible_pitch_to_fade(tmp_path, rings):
    handoff = 1.0
    notes = [
        Note(0.25, 1.063, 51),
        Note(0.628, 1.023, 66),
        Note(0.630, 1.0003, 59),
        Note(0.631, 1.173, 61),
        Note(handoff, 3.72, 65),
        Note(handoff + 0.00001, 3.68, 58),
        Note(handoff + 0.0003, 3.68, 60),
    ]
    rate = 16000
    time = np.arange(rate * 2) / rate
    pitch = 440 * 2 ** ((61 - 69) / 12)
    end = 1.173 if rings else 0.88
    waveform = 0.2 * np.sin(2 * np.pi * pitch * time) * ((time >= 0.631) & (time < end))
    audio = tmp_path / "chords.wav"
    sf.write(audio, waveform, rate)

    original = assign_polyphonic_frets(notes)
    assert sorted(p.fret for p in original if p.note.start >= handoff) == [1, 1, 13]
    fitted, retained, repairs = repair_late_releases(
        notes, original, audio, tuning=STANDARD_TUNING, max_span=5
    )
    assert [(note.start, note.pitch) for note in retained] == [
        (note.start, note.pitch) for note in notes
    ]
    if rings:
        assert retained == notes
        assert fitted == original
        assert not repairs
    else:
        (repair,) = repairs
        assert repair["source_index"] == 3
        assert repair["chord_span_before"] == 12
        assert repair["chord_span_after"] <= 3
        assert retained[3].end == handoff
        assert notes[3].end == 1.173
        assert all(a.end == b.end for i, (a, b) in enumerate(zip(retained, notes)) if i != 3)

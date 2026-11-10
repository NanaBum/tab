import pytest

from scripts.download_idmt_subset import RangeArchive
from tabber.evaluation import idmt_recording


def annotation(events):
    return (
        "<instrumentRecording><globalParameter><instrumentTuning>40,45,50,55,59,64</instrumentTuning>"
        "</globalParameter><transcription>" + events + "</transcription></instrumentRecording>"
    )


def event(pitch, string, fret, start=0, end=1):
    return (
        f"<event><pitch>{pitch}</pitch><stringNumber>{string}</stringNumber>"
        f"<fretNumber>{fret}</fretNumber><onsetSec>{start}</onsetSec>"
        f"<offsetSec>{end}</offsetSec></event>"
    )


def test_idmt_audit_retains_pitch_targets_and_flags_inconsistent_positions():
    result = idmt_recording(annotation(event(45, 1, 5) + event(62, 2, 5)))
    assert [note.pitch for note in result.notes] == [45, 62]
    assert result.positions == [(5, 5), None]
    assert result.inconsistent_position_indices == [1]


def test_idmt_chords_keep_simultaneous_attacks_and_independent_releases():
    result = idmt_recording(annotation(event(64, 6, 0, 0.5, 1) + event(40, 1, 0, 0.5, 2)))
    assert [(note.start, note.end) for note in result.notes] == [(0.5, 1), (0.5, 2)]
    assert result.positions == [(0, 0), (5, 0)]


def test_idmt_accepts_the_space_delimited_tuning_in_lick_annotations():
    source = annotation(event(45, 2, 0)).replace("40,45,50,55,59,64", "40  45  50  55  59  64")
    result = idmt_recording(source)
    assert result.positions == [(4, 0)]


def test_idmt_invalid_timing_does_not_silently_disappear():
    with pytest.raises(ValueError, match="event 0"):
        idmt_recording(annotation(event(64, 6, 0, 1, 0)))


def test_subset_download_refuses_a_server_that_ignores_ranges(monkeypatch):
    class FullDownload:
        status = 200

        def __init__(self):
            self.headers = {}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self, *args):
            raise AssertionError("Must not read an unrequested full archive")

    monkeypatch.setattr("urllib.request.urlopen", lambda *args, **kwargs: FullDownload())
    with pytest.raises(ValueError, match="full download refused"):
        RangeArchive().read(22)


def test_subset_download_budget_refuses_unbounded_reads():
    with pytest.raises(ValueError, match="budget"):
        RangeArchive().read()

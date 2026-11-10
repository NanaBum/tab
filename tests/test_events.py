import json

import pytest

from tabber.events import load_events, save_events
from tabber.models import Note


def test_event_file_preserves_original_times_and_can_be_edited(tmp_path):
    path = tmp_path / "notes.json"
    original = [Note(0.013, 0.367, 64, 0.87)]
    save_events(original, path, {"backend": "basic-pitch"})
    assert load_events(path) == original
    payload = json.loads(path.read_text())
    payload["notes"][0]["pitch"] = 65
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert load_events(path)[0].pitch == 65


@pytest.mark.parametrize(
    "payload",
    [
        {},
        [],
        {"format": "tabber-note-events", "schema_version": 2, "notes": []},
        {"format": "tabber-note-events", "schema_version": 1, "notes": [{}]},
        {
            "format": "tabber-note-events",
            "schema_version": 1,
            "notes": [{"start": 1, "end": 0, "pitch": 60}],
        },
    ],
)
def test_invalid_event_data_has_a_useful_error(tmp_path, payload):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError):
        load_events(path)

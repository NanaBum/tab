"""Editable detected-note interchange, separate from fingering and score rhythm."""

import json
from dataclasses import asdict
from pathlib import Path

from .models import Note


def save_events(notes: list[Note], path: Path, metadata: dict | None = None) -> None:
    payload = {
        "schema_version": 1,
        "format": "tabber-note-events",
        "metadata": metadata or {},
        "notes": [asdict(n) for n in notes],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def load_events(path: Path) -> list[Note]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        if payload.get("format") != "tabber-note-events" or payload.get("schema_version") != 1:
            raise ValueError("Use a version 1 tabber-note-events file, such as detected-notes.json")
        notes = payload["notes"]
        if not isinstance(notes, list):
            raise TypeError("The notes field must be a list")
        result = []
        for index, values in enumerate(notes, start=1):
            try:
                result.append(Note(**values))
            except (KeyError, TypeError, ValueError) as error:
                raise ValueError(f"Invalid note {index}: {error}") from error
        return sorted(result, key=lambda n: n.start)
    except (KeyError, TypeError, AttributeError, json.JSONDecodeError) as error:
        raise ValueError(f"Invalid note-event file: {error}") from error

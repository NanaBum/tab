"""Read supported local timed-note formats without changing their timing."""

import json
import xml.etree.ElementTree as ET

from .evaluation import idmt_recording
from .events import load_events
from .models import Note


def read_reference_metadata(path):
    """Keep source-side caveats as well as the manifest author's review notes."""
    if path.suffix.lower() == ".xml":
        recording = idmt_recording(path.read_text(encoding="utf-8-sig"))
        return {
            "source_metadata": recording.metadata,
            "inconsistent_position_indices": recording.inconsistent_position_indices,
        }
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    metadata = payload.get("metadata", {})
    if not isinstance(metadata, dict):
        raise TypeError("Reference metadata must be an object")
    return metadata


def read_notes(path):
    if path.suffix.lower() == ".xml":
        try:
            return idmt_recording(path.read_text(encoding="utf-8-sig")).notes
        except ET.ParseError as error:
            raise ValueError(f"Invalid IDMT XML: {error}") from error
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise TypeError("Expected a note-file object")
    if payload.get("format") == "tabber-note-events":
        return load_events(path)
    if payload.get("string_order") in {"high E to low E", "string 1 to string 6"} and isinstance(
        payload.get("notes"), list
    ):
        return [Note(**entry["note"]) for entry in payload["notes"]]
    raise ValueError("Use detected-note JSON, an exported notes.json, or IDMT annotation XML")

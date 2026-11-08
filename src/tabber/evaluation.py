"""Note-event evaluation and lightweight GuitarSet JAMS reading.

Metrics use one-to-one maximum matching, exact semitone pitches, 50 ms onset
tolerance, and optional offsets within max(50 ms, 20% of reference duration).
They do not measure perceived playability or prove string identification.
"""

import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass

import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import maximum_bipartite_matching

from .models import STANDARD_TUNING, FrettedNote, Note


@dataclass(frozen=True)
class IDMTRecording:
    notes: list[Note]
    positions: list[tuple[int, int] | None]
    metadata: dict[str, str]
    inconsistent_position_indices: list[int]


def idmt_recording(xml: str) -> IDMTRecording:
    """Read IDMT note targets, auditing pitch/string/fret consistency separately.

    Source strings are 1-based low E first. Some published entries have positions
    inconsistent with their MIDI pitch; retain that pitch and exclude only their
    position from conditional string/fret scoring, with explicit indices.
    """
    root = ET.fromstring(xml)
    if root.tag != "instrumentRecording":
        raise ValueError("Expected an IDMT instrumentRecording annotation")
    global_parameters = root.find("globalParameter")
    metadata = (
        {child.tag: child.text or "" for child in global_parameters}
        if global_parameters is not None
        else {}
    )
    tuning = tuple(
        int(value.strip())
        for value in metadata.get("instrumentTuning", "").split(",")
        if value.strip()
    )
    if tuning != tuple(reversed(STANDARD_TUNING)):
        raise ValueError("IDMT evaluation currently requires declared standard tuning")
    notes, positions, inconsistent = [], [], []
    for index, event in enumerate(root.findall("./transcription/event")):
        try:
            note = Note(
                float(event.findtext("onsetSec")),
                float(event.findtext("offsetSec")),
                int(event.findtext("pitch")),
            )
        except (TypeError, ValueError) as error:
            raise ValueError(f"Invalid IDMT pitch/timing at event {index}") from error
        notes.append(note)
        position = None
        try:
            string = 6 - int(event.findtext("stringNumber"))
            fret = int(event.findtext("fretNumber"))
            if 0 <= string < 6 and 0 <= fret <= 24 and STANDARD_TUNING[string] + fret == note.pitch:
                position = (string, fret)
        except (TypeError, ValueError):
            pass
        positions.append(position)
        if position is None:
            inconsistent.append(index)
    if not notes:
        raise ValueError("IDMT annotation contains no note events")
    return IDMTRecording(notes, positions, metadata, inconsistent)


@dataclass(frozen=True)
class Scores:
    reference_notes: int
    predicted_notes: int
    matched_notes: int
    precision: float
    recall: float
    f1: float


def match_notes(
    reference: list[Note], predicted: list[Note], *, onset_tolerance=0.05, offsets=False
) -> list[tuple[int, int]]:
    if not math.isfinite(onset_tolerance) or onset_tolerance < 0:
        raise ValueError("Onset tolerance must be finite and nonnegative")
    if not reference or not predicted:
        return []
    valid = np.array(
        [
            [
                r.pitch == p.pitch
                and abs(r.start - p.start) <= onset_tolerance + 1e-9
                and (not offsets or abs(r.end - p.end) <= max(0.05, 0.2 * (r.end - r.start)) + 1e-9)
                for p in predicted
            ]
            for r in reference
        ],
        dtype=bool,
    )
    matches = maximum_bipartite_matching(csr_matrix(valid), perm_type="column")
    return [(i, int(j)) for i, j in enumerate(matches) if j >= 0]


def score_notes(reference: list[Note], predicted: list[Note], **kwargs) -> Scores:
    count = len(match_notes(reference, predicted, **kwargs))
    precision = count / len(predicted) if predicted else 0.0
    recall = count / len(reference) if reference else 0.0
    f1 = 2 * count / (len(reference) + len(predicted)) if reference or predicted else 0.0
    return Scores(len(reference), len(predicted), count, precision, recall, f1)


def guitarset_notes(jams: dict, *, end: float | None = None) -> list[FrettedNote]:
    """Read note_midi annotations; GuitarSet string 0 is low E, ours is high E.

    Entries use observation time relative to the excerpt. annotation.time is the
    position in the original recording and must not be added to the observation.
    Fractional MIDI values are rounded to the nearest semitone for this metric.
    """
    notes = []
    for annotation in jams["annotations"]:
        if annotation["namespace"] != "note_midi":
            continue
        string = 5 - int(annotation["annotation_metadata"]["data_source"])
        if not 0 <= string < 6:
            raise ValueError("GuitarSet string index is outside 0-5")
        for observation in annotation["data"]:
            start = float(observation["time"])
            stop = start + float(observation["duration"])
            if end is not None:
                if start >= end:
                    continue
                stop = min(stop, end)
            if stop <= max(0, start):
                continue
            pitch = int(float(observation["value"]) + 0.5)
            note = Note(max(0, start), stop, pitch)
            notes.append(FrettedNote(note, string, pitch - STANDARD_TUNING[string]))
    return sorted(notes, key=lambda n: (n.note.start, n.string))

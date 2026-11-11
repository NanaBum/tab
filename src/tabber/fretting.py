"""Dynamic programming over playable positions for a single melodic voice."""

import itertools
import math
from dataclasses import replace

from .models import STANDARD_TUNING, FrettedNote, Note
from .rhythm import score_interval


class StringAssignmentConflict(ValueError):
    def __init__(self, note, sounding, event_number, tuning, max_fret):
        pitches = sorted([note.pitch, *(prior.pitch for prior in sounding)])
        if _can_share_strings(pitches, tuning, max_fret):
            reason = "The search could not assign the overlapping notes."
        else:
            joined = ", ".join(map(str, pitches))
            reason = f"Overlapping MIDI pitches {joined} cannot use distinct strings in this tuning and fret range."
        super().__init__(
            f"No fingering at {note.start:.3f}s for event {event_number} "
            f"(MIDI pitch {note.pitch}). {reason} Review attacks and releases; no notes were dropped."
        )
        self.note = note
        self.sounding = sounding


def assign_frets(notes: list[Note], tuning=STANDARD_TUNING, max_fret=24) -> list[FrettedNote]:
    if max_fret < 0 or not tuning:
        raise ValueError("Provide a tuning and nonnegative maximum fret")
    notes = sorted(notes, key=lambda n: n.start)
    if any(b.start < a.end - 1e-6 for a, b in itertools.pairwise(notes)):
        raise ValueError(
            "Overlapping notes need polyphonic fingering; choose --fretting polyphonic"
        )
    if not notes:
        return []
    positions = [
        [
            (s, n.pitch - open_pitch)
            for s, open_pitch in enumerate(tuning)
            if 0 <= n.pitch - open_pitch <= max_fret
        ]
        for n in notes
    ]
    for note, candidates in zip(notes, positions):
        if not candidates:
            raise ValueError(
                f"MIDI pitch {note.pitch} at {note.start:.3f}s is outside this guitar's playable range "
                f"({min(tuning)}-{max(tuning) + max_fret}); no notes were dropped"
            )
    costs = [f * 0.05 for _, f in positions[0]]
    parents = []
    for previous, current in itertools.pairwise(positions):
        new_costs, back = [], []
        for string, fret in current:
            transitions = [
                cost
                + abs(string - ps) * 0.5
                + (abs(fret - pf) if fret and pf else 0.75)
                + fret * 0.05
                for cost, (ps, pf) in zip(costs, previous)
            ]
            best = min(range(len(transitions)), key=transitions.__getitem__)
            new_costs.append(transitions[best])
            back.append(best)
        parents.append(back)
        costs = new_costs
    index = min(range(len(costs)), key=costs.__getitem__)
    indices = [index]
    for back in reversed(parents):
        index = back[index]
        indices.append(index)
    return [
        FrettedNote(n, *candidates[i])
        for n, candidates, i in zip(notes, positions, reversed(indices))
    ]


def _can_share_strings(pitches, tuning, max_fret):
    # Assigning the lowest eligible string leaves all higher choices available.
    available = iter(sorted(tuning))
    for pitch in sorted(pitches):
        open_pitch = next((value for value in available if value >= pitch - max_fret), None)
        if open_pitch is None or open_pitch > pitch:
            return False
    return True


def assign_polyphonic_frets(
    notes: list[Note],
    tuning=STANDARD_TUNING,
    max_fret=24,
    max_span=5,
    beam_width=128,
    string_priors=None,
    prior_weight=2.0,
    *,
    score_grid: tuple[int, int] | None = None,
) -> list[FrettedNote]:
    """Beam-search positions while reserving strings for sustained notes.

    Preserves every detected note. This is an approximate ergonomic heuristic,
    not recovery of the guitarist's actual fingers or a guarantee of playability.
    The preferred span (the legacy max_span parameter) affects cost only.
    Optional (integer tempo, grid) constraints also check the saved score.
    """
    if not tuning or max_fret < 0 or max_span < 0 or beam_width < 1:
        raise ValueError("Provide tuning and positive search limits")
    if not math.isfinite(prior_weight) or prior_weight < 0:
        raise ValueError("String-prior weight must be finite and nonnegative")
    priors = {}
    if string_priors is not None:
        if len(string_priors) != len(notes):
            raise ValueError("Provide one string-prior row per note")
        for note, row in zip(notes, string_priors):
            if (
                len(row) != len(tuning)
                or not all(math.isfinite(p) and p >= 0 for p in row)
                or sum(row) <= 0
            ):
                raise ValueError(
                    "String priors must be finite, nonnegative rows with positive sums"
                )
            total = sum(row)
            if max(row) - min(row) > 1e-12:
                priors[id(note)] = tuple(p / total for p in row)
    ordered = sorted(notes, key=lambda n: (n.start, -n.pitch))
    cells = {id(note): score_interval(note, *score_grid) for note in ordered} if score_grid else {}
    # cost, complete history, active positions, last hand position, last string
    states = [(0.0, (), (), 0.0, 0)]
    for index, note in enumerate(ordered):
        candidates = [
            (s, note.pitch - p) for s, p in enumerate(tuning) if 0 <= note.pitch - p <= max_fret
        ]
        if not candidates:
            raise ValueError(
                f"MIDI pitch {note.pitch} at {note.start:.3f}s is outside this guitar's playable range "
                f"({min(tuning)}-{max(tuning) + max_fret}); no notes were dropped"
            )
        expanded = {}
        for cost, history, active, hand, last_string in states:
            sounding = tuple(n for n in active if n.note.end > note.start + 1e-6)
            reserved = sounding
            on_grid = ()
            if cells:
                start_cell = cells[id(note)][0]
                on_grid = tuple(n for n in active if cells[id(n.note)][1] > start_cell)
                reserved = tuple(dict.fromkeys(sounding + on_grid))
            used = {n.string for n in reserved}
            for string, fret in candidates:
                if string in used:
                    continue
                fretted = FrettedNote(note, string, fret)
                current = reserved + (fretted,)
                frets = sorted(n.fret for n in sounding + (fretted,) if n.fret)
                span = frets[-1] - frets[0] if frets else 0
                grid_span = max((abs(fret - n.fret) for n in on_grid if fret and n.fret), default=0)
                excess = max(0, span - max_span, grid_span - max_span)
                position = frets[len(frets) // 2] if frets else hand
                movement = abs(position - hand) if hand and position else 0
                new_cost = cost + movement + span * 0.3 + fret * 0.04
                new_cost += excess * 1.5
                new_cost += abs(string - last_string) * 0.15
                if id(note) in priors:
                    new_cost -= prior_weight * math.log(max(1e-8, priors[id(note)][string]))
                key = (
                    tuple(
                        sorted(
                            (n.string, n.fret, n.note.end, cells[id(n.note)][1] if cells else 0)
                            for n in current
                        )
                    ),
                    position,
                    string,
                )
                state = (new_cost, history + (fretted,), current, position, string)
                if key not in expanded or new_cost < expanded[key][0]:
                    expanded[key] = state
        if not expanded:
            sounding = [prior for prior in ordered[:index] if prior.end > note.start + 1e-6]
            raise StringAssignmentConflict(note, sounding, index + 1, tuning, max_fret)
        states = sorted(expanded.values(), key=lambda state: state[0])[:beam_width]
    return list(states[0][1]) if ordered else []


def recover_overlapping_notes(notes, *, tuning, max_span, string_priors=None):
    """Refit after shortening or omitting notes at the first failed attack."""
    retained = dict(enumerate(notes))
    while True:
        options = {"tuning": tuning, "max_span": max_span}
        if string_priors is not None:
            options["string_priors"] = [string_priors[index] for index in retained]
        try:
            assigned = assign_polyphonic_frets(list(retained.values()), **options)
        except StringAssignmentConflict as conflict:
            involved = {id(note) for note in (*conflict.sounding, conflict.note)}
            group = [(index, note) for index, note in retained.items() if id(note) in involved]
            if not _can_share_strings([note.pitch for _, note in group], tuning, 24):
                group = [
                    (index, note)
                    for index, note in group
                    if _can_share_strings(
                        [other.pitch for other_index, other in group if index != other_index],
                        tuning,
                        24,
                    )
                ]
            edits = []
            for index, note in group:
                confidence = max(note.confidence, 0.05)
                if note.start + 1e-6 < conflict.note.start:
                    end = conflict.note.start
                    fraction = (note.end - end) / (note.end - note.start)
                    edits.append((confidence * fraction, index, end))
                else:
                    edits.append((confidence + 0.05, index, None))
            _, index, end = min(edits)
            if end is None:
                del retained[index]
            else:
                retained[index] = replace(retained[index], end=end)
        else:
            return assigned, retained

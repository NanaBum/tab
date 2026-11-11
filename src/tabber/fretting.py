"""Dynamic programming over playable positions for a single melodic voice."""

import itertools
import math

from .models import STANDARD_TUNING, FrettedNote, Note
from .rhythm import score_interval


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
                if span > max_span:
                    continue
                if fret and any(n.fret and abs(fret - n.fret) > max_span for n in on_grid):
                    continue
                position = frets[len(frets) // 2] if frets else hand
                movement = abs(position - hand) if hand and position else 0
                new_cost = cost + movement + span * 0.3 + fret * 0.04
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
            raise ValueError(
                f"No fingering at {note.start:.3f}s for event {index + 1} (MIDI pitch {note.pitch}): sustained strings "
                f"or the {max_span}-fret span limit conflict. Review detections; no notes were dropped."
            )
        states = sorted(expanded.values(), key=lambda state: state[0])[:beam_width]
    return list(states[0][1]) if ordered else []

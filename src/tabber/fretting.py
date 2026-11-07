"""Dynamic programming over playable positions for a single melodic voice."""

import itertools

from .models import STANDARD_TUNING, FrettedNote, Note


def assign_frets(notes: list[Note], tuning=STANDARD_TUNING, max_fret=24) -> list[FrettedNote]:
    if max_fret < 0 or not tuning:
        raise ValueError("Provide a tuning and nonnegative maximum fret")
    notes = sorted(notes, key=lambda n: n.start)
    if any(b.start < a.end - 1e-6 for a, b in itertools.pairwise(notes)):
        raise ValueError(
            "Overlapping notes need chord-aware fingering, which is not implemented yet"
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
            raise ValueError(f"MIDI pitch {note.pitch} is outside this guitar's playable range")
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

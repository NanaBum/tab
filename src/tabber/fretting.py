"""Dynamic programming over playable positions for a single melodic voice."""

import itertools
import math
from collections import deque
from dataclasses import replace

from .models import STANDARD_TUNING, FrettedNote, Note
from .rhythm import score_interval

CHORD_ATTACK_SECONDS = 0.045
CHORD_SUSTAIN_SECONDS = 0.06
CHORD_CONTEXT_SECONDS = 1.5


class UnplayablePitch(ValueError):
    def __init__(self, note, tuning, max_fret):
        super().__init__(
            f"MIDI pitch {note.pitch} at {note.start:.3f}s cannot be played on a string "
            f"in the selected tuning at frets 0-{max_fret} "
            f"(overall playable range {min(tuning)}-{max(tuning) + max_fret}); "
            "no notes were dropped"
        )


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


def fret_positions(pitch, tuning, max_fret=24):
    """List physical string and fret choices for one MIDI pitch."""
    return [
        (string, pitch - open_pitch)
        for string, open_pitch in enumerate(tuning)
        if 0 <= pitch - open_pitch <= max_fret
    ]


def _position_costs(pitch, tuning, max_fret):
    positions = fret_positions(pitch, tuning, max_fret)
    # Open notes leave the fretting hand free, but fret zero itself earns no discount.
    open_cost = min((fret for _, fret in positions if fret), default=0)
    return [
        (string, fret, fret or open_cost)
        for string, fret in sorted(positions, key=lambda position: position[1] == 0)
    ]


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
    positions = [_position_costs(n.pitch, tuning, max_fret) for n in notes]
    for note, candidates in zip(notes, positions):
        if not candidates:
            raise UnplayablePitch(note, tuning, max_fret)
    costs = [position_cost * 0.05 for _, _, position_cost in positions[0]]
    parents = []
    for previous, current in itertools.pairwise(positions):
        new_costs, back = [], []
        for string, fret, position_cost in current:
            transitions = [
                cost
                + abs(string - ps) * 0.5
                + (abs(fret - pf) if fret and pf else 0.75)
                + position_cost * 0.05
                for cost, (ps, pf, _) in zip(costs, previous)
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
        FrettedNote(n, *candidates[i][:2])
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


def _chord_context(ordered):
    """Use earlier attacks only so overlap recovery can reuse a search prefix."""
    group = []
    group_start = last_chord = -math.inf
    recent_groups = deque(maxlen=3)
    context = []
    for note in ordered:
        if note.start - group_start > CHORD_ATTACK_SECONDS:
            if group:
                last_attack = group[-1].start
                ringing = {
                    prior.pitch for prior in group if prior.end - last_attack >= CHORD_SUSTAIN_SECONDS
                }
                chord = len(ringing) >= 2
                recent_groups.append(chord)
                if chord:
                    last_chord = group_start
            group = []
            group_start = note.start
        group.append(note)
        chord_phrase = (
            group_start - last_chord <= CHORD_CONTEXT_SECONDS
            and 2 * sum(recent_groups) >= len(recent_groups)
        )
        weight = 0.45 if chord_phrase else 0.20
        context.append((group_start, weight))
    return context


class _SearchCheckpoints:
    """Keep beam states at intervals while retrying one recovery search."""

    def __init__(self):
        self.ordered = []
        self.states = {}

    def restart(self, ordered, initial):
        prefix = 0
        for previous, current in zip(self.ordered, ordered):
            if previous is not current:
                break
            prefix += 1
        index = max((index for index in self.states if index <= prefix), default=0)
        states = self.states.get(index, initial)
        self.states = {i: beam for i, beam in self.states.items() if i <= index}
        self.ordered = ordered
        return index, states


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
    _checkpoints: _SearchCheckpoints | None = None,
) -> list[FrettedNote]:
    """Beam-search positions while reserving strings for sustained notes.

    Preserves every detected note. This is an approximate ergonomic heuristic,
    not recovery of the guitarist's actual fingers or a guarantee of playability.
    The preferred span (the legacy max_span parameter) affects cost only.
    Optional (integer tempo, grid) constraints also check the saved score.
    Close, sustained attacks get a small preference for adjacent string shapes.
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
    positions = [_position_costs(n.pitch, tuning, max_fret) for n in ordered]
    chord_context = _chord_context(ordered)
    for note, candidates in zip(ordered, positions, strict=True):
        if not candidates:
            raise UnplayablePitch(note, tuning, max_fret)
    cells = {id(note): score_interval(note, *score_grid) for note in ordered} if score_grid else {}
    # Each history links the latest assignment to its previous history.
    states = [(0.0, None, (), 0.0, None)]
    start = 0
    if _checkpoints is not None:
        start, states = _checkpoints.restart(ordered, states)
    for index in range(start, len(ordered)):
        note, candidates = ordered[index], positions[index]
        group_start, chord_weight = chord_context[index]
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
            chord_strings = (
                [
                    n.string
                    for n in sounding
                    if n.note.start >= group_start
                    and n.note.pitch != note.pitch
                    and n.note.end - note.start >= CHORD_SUSTAIN_SECONDS
                ]
                if note.end - note.start >= CHORD_SUSTAIN_SECONDS
                else []
            )
            if chord_strings:
                chord_low, chord_high = min(chord_strings), max(chord_strings)
            for string, fret, position_cost in candidates:
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
                new_cost = cost + movement + span * 0.3 + position_cost * 0.04
                new_cost += excess * 1.5
                if last_string is not None:
                    new_cost += abs(string - last_string) * 0.15
                if chord_strings:
                    new_gaps = max(chord_low - string - 1, string - chord_high - 1, 0)
                    new_cost += chord_weight * new_gaps
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
                if key not in expanded or new_cost < expanded[key][0]:
                    expanded[key] = (new_cost, (fretted, history), current, position, string)
        if not expanded:
            sounding = [
                prior
                for prior in ordered[:index]
                if prior.end > note.start + 1e-6
                or (cells and cells[id(prior)][1] > cells[id(note)][0])
            ]
            raise StringAssignmentConflict(note, sounding, index + 1, tuning, max_fret)
        states = sorted(expanded.values(), key=lambda state: state[0])[:beam_width]
        if _checkpoints is not None and (index + 1) % 32 == 0:
            _checkpoints.states[index + 1] = states
    assignments = []
    history = states[0][1]
    while history is not None:
        fretted, history = history
        assignments.append(fretted)
    assignments.reverse()
    return assignments


def recover_overlapping_notes(notes, *, tuning, max_span, string_priors=None, score_grid=None):
    """Refit after shortening or omitting notes at the first failed attack."""
    retained = dict(enumerate(notes))
    checkpoints = _SearchCheckpoints()
    while True:
        options = {
            "tuning": tuning,
            "max_span": max_span,
            "score_grid": score_grid,
            "_checkpoints": checkpoints,
        }
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
                end = conflict.note.start
                if score_grid:
                    tempo, grid = score_grid
                    start_cell = score_interval(note, tempo, grid)[0]
                    attack_cell = score_interval(conflict.note, tempo, grid)[0]
                    if start_cell < attack_cell:
                        # At the midpoint the score rounds up to the following cell.
                        boundary = (attack_cell + 0.5) * 240 / (tempo * grid) - 1e-8
                        end = min(end, boundary)
                    else:
                        end = note.start
                if note.start + 1e-6 < end < note.end:
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

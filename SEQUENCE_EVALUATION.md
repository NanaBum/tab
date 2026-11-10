# Comparing a short recording with a supplied string/fret list

A user can provide the ordered positions they played without marking exact
onsets and endings. This supports a useful pitch-sequence check, but not the
timed F1 metrics used for GuitarSet or an assessment of rhythm accuracy.

The new `scripts/compare_reference_sequence.py` reads a reference JSON list and
an exported Tabber `notes.json`. The reference is standard tuning with string
0 = high E, through 5 = low E; frets are 0–24. For example:

```json
[
  {"string": 5, "fret": 0},
  {"string": 5, "fret": 3},
  {"string": 4, "fret": 0}
]
```

The assistant can prepare that file from a plain-language list. The user does
not need to learn JSON or write a formal tab. A reference file containing
different tuning must not be silently interpreted as standard tuning.

```powershell
uv run python scripts/compare_reference_sequence.py runs/reference.json runs/my-song/notes.json --output runs/my-song/comparison.json
```

## What the comparison means

- Convert reference and generated positions to MIDI pitches, then align their
  sequences using minimum edit distance: wrong pitch, missing note and extra note
  each cost one. Exact pitch matches cost zero. Among equal-cost alignments,
  prefer more exact pitch matches, then use deterministic operation order.
- Report raw edit count, each error count and edit count divided by the longer
  sequence length. Lower is better. This is not timed note F1 or a percentage
  of the complete tab that is correct.
- Separately report reference string/fret agreement among aligned exact-pitch
  matches. An alternate fingering can sound right. This conditional measure
  excludes missing, extra and wrong-pitch notes and is not overall tab accuracy.
- Never use reference string/fret agreement to select between pitch-alignment
  ties. Flag multiple optimal pitch alignments; repeated notes can make the
  association of exact reference fingerings uncertain.
- Order predictions by onset, then descending pitch, then string. Report
  simultaneous adjacent attacks and adjacent overlapping sustain pairs instead
  of discarding them. This can expose erroneous extra detections. It does not
  establish a valid alignment for a reference chord performance; an ordered
  single-note example is the intended use.

No note times are changed, notes are not merged, and the source files are not
edited. The check does not train or tune a model. The dynamic-programming table
is limited to one million cells; split very long comparisons into phrases.
If neither sequence has notes the edit count is zero, but there is no conditional
fingering accuracy to report. If all reference notes are missing, report that
explicitly. An empty detection file is not evidence of a successful transcription.

Regressions cover insertion, deletion, substitution, repeated attacks, alternate
fingerings, empty inputs, reference validation, ambiguous alignment independent
of fingering, and an exported-file comparison that preserves the source.

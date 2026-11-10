# Local Guitar Pro reference import

This imports a permitted local GP3, GP4 or GP5 file into timed note-event JSON
for inspection and comparison. It does not download tabs, verify music rights,
align a recording automatically or train a model. Generated tablature and rhythm
behavior are unchanged.

## Inspect and choose a track

```powershell
uv run python scripts/import_reference_tab.py path/to/reference.gp5 --list-tracks
uv run python scripts/import_reference_tab.py path/to/reference.gp5 --track 2 --output runs/reference-events.json
```

Track numbers are one-based positions in the listed score. Multi-track files
require an explicit selection; the importer does not guess which guitar matches
the recording. Percussion tracks are refused. A single pitched track can be
selected automatically. Source string numbering, fret positions, tuning and capo
are retained in metadata rather than replaced with our fingering search.

Note times are derived from score ticks, time signatures and the global tempo
map. Instant tempo changes on other tracks are included, including changes
inside a held note. Tied segments become one attack with a continuous duration.
Independent voices and simultaneous chord notes remain separate events. The
timeline begins at score tick 960, mapped to zero seconds. These are **notated,
metronomic times**, not verified attack/release times in a recording.

The source tab remains unchanged. The output contains a source hash and track
information, with `reference_status` marked as a candidate and `data_permission`
explicitly unassessed. File import does not make a reference accurate or usable
under any particular license.

## Score features requiring further work

Repeats and alternate endings are refused by default. To expand supported repeat
structures into playback order, explicitly request:

```powershell
uv run python scripts/import_reference_tab.py path/to/reference.gp5 --track 1 --unfold-repeats --max-playback-measures 10000 --output runs/reference-events.json
```

This handles simple repeats, nested plain repeats and explicit nonnested ending
bitmasks. The first closing repeat may imply the score beginning; later repeats
need an opening marker. Every played measure retains its source measure and pass
provenance. Skipped endings consume no time. Instant tempo changes are replayed,
including restoration of the source-entry tempo when a repeat starts again.

Nested repeats with alternate endings, unlabeled ending continuations, ambiguous
repeat structures, tempo changes combined with alternate endings, navigation
jumps, swing/triplet-feel playback and gradual tempo ramps are still refused.
Conditional ties with different pitches on different playback branches also fail
rather than guessing their meaning. Expansion is bounded by the requested limit
(10,000 played measures by default). Broken
ties, invalid string/fret positions and conflicting tempo declarations also fail
explicitly. It does not silently choose a repeat count or flatten a tempo ramp.

Performance techniques are also refused by default. For **candidate base-note
inspection only**, they can be retained with an explicit approximation flag:

```powershell
uv run python scripts/import_reference_tab.py path/to/reference.gp5 --track 1 --allow-approximate-techniques --output runs/candidate-reference.json
```

That mode preserves base fret pitches and written durations, with per-event
technique flags/details. It does not expand grace notes, trills, tremolo attacks,
bends, harmonics or twelve-string doubling into their performed pitches/timings.
Let-ring, staccato, palm muting, legato, vibrato, strokes and duration overrides
can also make playback differ from those base symbols. Keep these references
flagged for review rather than using them as verified performance ground truth.

## Compare with saved detections

```powershell
uv run python scripts/compare_timed_events.py runs/reference-events.json runs/transcription/detected-notes.json --max-shift 5 --output runs/reference-comparison.json
```

The comparison retains the imported reference status, permission status and
technique flags in its report. It reports both original timing metrics and a
reference-assisted single-global-shift diagnostic; the original events are
unchanged. A global shift cannot fix tempo drift or a different arrangement.
See [GLOBAL_ALIGNMENT.md](GLOBAL_ALIGNMENT.md).

For comparisons with a recording, select the score track explicitly and check
that its playback lines up with the recorded performance.

## Local evidence

- GP3, GP4 and GP5 serialization/import tests preserve source bytes and expected
  tied events; imported metadata reaches the comparison report.
- Multi-track selection, tempo changes inside a held note (including a saved GP5
  round trip), mixed meters, independent voices, capo and alternate tuning pass.
- Repeat/swing rejection, technique opt-in, gradual tempo refusal, broken ties
  and malformed-file failure are checked explicitly.
- GP3/GP4/GP5 repeat and ending serialization checks cover playback order, tempo
  resets and ties. A generated two-bar repeat was also exported to MIDI by the
  installed TuxGuitar 2.1: all four imported pitch/onset pairs matched its playback
  at 0, 2, 6 and 8 seconds. This checks one simple repeat/tempo example, not all
  third-party repeat notation or release behavior. Evidence is in
  [repeat-native-check.json](reports/repeat-native-check.json).
- All 92 saved generated GP5 outputs were imported with the same 2,858 canonical
  note events, pitches and score times. This is structural readback, not accuracy
  against audio or arbitrary third-party score coverage.
- The [checked-in structural audit](reports/reference-import-audit.json) includes
  86 public-source/synthetic development outputs; private recording files are
  excluded. The complete local audit remains outside the source repository.

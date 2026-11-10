# Recovering a failed draft without listening again

Two optional controls address different causes of failure. Both are off in the
desktop by default; the normal five-fret span and unfiltered detections remain
unchanged. Rebuild saved detections to try a setting without rerunning ML.

## Notes outside the instrument range

**Exclude notes outside selected tuning / 24 frets** adds `--guitar-range`.
In default standard tuning it retains MIDI pitches 40 through 88 inclusive.
With explicit `--tuning drop-d`, it retains 38 through 88 instead. Bounds follow
the selected six-string tuning and 24 frets, capped at MIDI 127. It can exclude
low noise or another instrument, but cannot identify every false note or distinguish
two fingerings. For unusual tunings the bounding interval can contain unplayable
gaps; fretting still fails explicitly rather than dropping those notes. See
[TUNING.md](TUNING.md) before changing this setting.

```powershell
uv run tabber --events runs/failed/diagnostics/detected-TIMESTAMP.json --guitar-range --bpm 120 --grid 32 --output runs/range-review
```

Every run saves its unfiltered detected events in `diagnostics/detected-*.json`
before fretting. These events are after the backend's normal decoding/sensitivity,
not raw neural-network activations. When range filtering is requested, it also
saves `diagnostics/range-filter-*.json` with every excluded note and its zero-based
index into the source event file, plus `diagnostics/selected-*.json` with retained
notes. The final `detected-notes.json` contains the events actually used for the
successful tab, with links to that audit. Original source files are unchanged.

The app and command line report how many notes were excluded, including when
export subsequently fails. If all notes are excluded, conversion fails explicitly
and preserves the raw diagnostics. Filtering never removes extra in-range notes
to force a playable chord. A seven-note simultaneous chord still fails rather
than losing one of its notes. An existing tab is preserved on these failures.

## Overlap or fret-span conflicts

**Allow wider fret stretches (7 frets)** adds `--max-span 7`. This changes only
the allowed difference between simultaneous non-open frets. It retains every
pitch, attack and release. Open strings are excluded from the span calculation.
The CLI accepts span limits from 0 through 24 in polyphonic mode; default is 5.
Wider permitted stretches still require musical and ergonomic review, and the
bounded search can still fail. There is no automatic fallback to a larger span.

```powershell
uv run tabber --events runs/failed/diagnostics/detected-TIMESTAMP.json --max-span 7 --bpm 120 --grid 32 --output runs/wider-review
```

This can address a span conflict but cannot fix an out-of-range pitch. Neither
control corrects bad detection timing, recovers techniques or identifies the
guitarist's actual fingering. Saved-note rebuilding reassigns fingerings and does
not preserve edits made in TuxGuitar.

## Evidence and correction

The GAPS smoke check's failure at `00_BN1-129-Eb_comp` was at **event 39, MIDI
pitch 62**, not a MIDI-39 detection. The earlier write-up confused the event
ordinal with pitch; that explanation and PR #15's description were corrected.
All 57 detected pitches were in range. The original five-fret result remains
recorded rather than being replaced by the more favorable setting.

The [exact constraint audit](reports/gaps-fretting-audit.json) proved those fixed
detections infeasible with a five-fret span and feasible with seven under our
declared string-reservation assumptions. Rebuilding with seven exported all 57
events; saved event times and pitches matched the source exactly, and the GP5
was reopened and verified. This is a recovery example, not an accuracy gain.

Local checks also cover inclusive range boundaries, weak saved notes, indexed
exclusions, all-excluded failure, retained infeasible chords, prior-tab preservation,
GUI command routing and notices on failure. The desktop controls were visually
checked with both new options unchecked. No ML defaults changed.

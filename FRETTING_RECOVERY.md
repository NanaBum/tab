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
If the app lists overlapping pitches that need distinct strings, their timing
and pitch already rule out an assignment in the selected tuning and fret range.
Review the detected attacks and releases around the reported time before rebuilding.

```powershell
uv run tabber --events runs/failed/diagnostics/detected-TIMESTAMP.json --max-span 7 --bpm 120 --grid 32 --output runs/wider-review
```

This can address a span conflict but cannot fix an out-of-range pitch. Neither
control corrects bad detection timing, recovers techniques or identifies the
guitarist's actual fingering. Saved-note rebuilding reassigns fingerings and does
not preserve edits made in TuxGuitar.

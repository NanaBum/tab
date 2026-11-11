# Recovering a failed draft without listening again

Rebuild saved detections to try different export settings without rerunning ML.

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
notes. The final `detected-notes.json` contains the selected detections before
overlap recovery, with links to the audits. Original source files are unchanged.

The app and command line report how many notes were excluded, including when
export subsequently fails. If all notes are excluded, conversion fails explicitly
and preserves the raw diagnostics.

## Overlapping notes

Tabber prefers compact fingerings and permits wider spans. Open strings are
excluded from the span calculation. The CLI accepts `--preferred-span` from
0 through 24 (default 5), with `--max-span` as a compatibility alias.

When the initial polyphonic assignment fails on an overlap, Tabber can shorten
an earlier release to the conflicting attack or omit a conflicting detection.
The decision weighs the fraction of a release lost and the detector's confidence.
The tab and its MIDI use the resulting notes. The original detections stay in
the saved events, and `diagnostics/overlap-recovery-*.json` lists every change.
Use `--strict-overlaps` for editable exports that keep detected note lengths
and counts even when a string conflict prevents export.
With **Try a finer grid if notes collide**, the app tries the available grids
before adjusting a collision that remains at 1/64. The audit records that grid.

```powershell
uv run tabber --events runs/failed/diagnostics/detected-TIMESTAMP.json --bpm 120 --grid 32 --output runs/overlap-review
```

Use the chosen tuning to represent the guitar's open pitches. Saved-note
rebuilding reassigns fingerings independently of edits made in TuxGuitar.

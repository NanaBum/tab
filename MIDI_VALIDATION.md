# Independent MIDI string voices

Two guitar strings can play the same pitch while starting and stopping at
different times. The earlier MIDI export put every note on channel zero. An
independent reconstruction test found two active notes with the same channel and
pitch, which does not distinguish which string's note each release belongs to.

MIDI now uses channels 0–5 for strings high E through low E. Every channel receives
the same guitar program (24, zero-based General MIDI). The conventional percussion
channel is avoided. One file/track still contains the complete performance.
This changes MIDI voice routing, not the detected pitches, selected fingering,
GP5 notes, or original timings stored in JSON.

The event resolution is 480 ticks per quarter note. Starts and ends round to the
nearest tick; durations are at least one tick. This prevents a very short note
from becoming a same-tick release followed by an attack that never releases.
Notes on one string that cannot fit this resolution are rejected before output
files are replaced. At an adjacent release/attack boundary, releases come first.
MIDI tempo itself uses integer microseconds per quarter note, so it also has
finite precision. MIDI is an approximation of the original second timestamps.

## Checks

- A playable unison (B-string fret 5 and open high E) retains independent attacks
  and releases, even though the pitches match.
- Very short notes have a positive duration and keep their original JSON times.
- Repeated notes on one string release before the next attack.
- The independent MIDI decoder rejects missing releases and ambiguous simultaneous
  notes on a single string channel.
- On cached first-ten-second detections for all 360 GuitarSet clips, all 353
  complete fingerings exported MIDI with exactly the expected 15,167 tick-level
  events, guitar programs and tempo. There were no MIDI audit failures. The seven
  pre-existing fingering failures remained explicit; no notes were removed.

The corpus check uses a 1/32 GP5 grid so all 353 complete fingerings can pass the
other-format export stage. This is a serialization check, not evidence of pitch
accuracy or that any particular synthesizer sounds like the recorded guitar.
No player was opened or audio played automatically. Dataset limitations in
MODEL_PROVENANCE.md still apply.

```powershell
uv run python scripts/validate_midi_exports.py runs/eval-ml-all.json
```

The check uses cached predictions and the downloaded annotations, with temporary
local exports removed on completion. It needs no ML imports, network, or paid
computing. Aggregate results are in `reports/midi-serialization.json`.

# Diagnosing seven fingering failures

The 360-excerpt development check had seven complete-fingering failures. Increasing
beam width from 128 through 512, 2048, and 8192 did not resolve any of them.

An independent exact binary constraint model then checked the same fixed note
timings and pitches. It assigns one string/fret position to each note, forbids
simultaneous notes from sharing a string, and constrains simultaneous non-open
frets to the stated span. Strings use standard tuning and frets 0–24. There is
no movement objective or permission to drop/shorten a note.

The solver proved all seven infeasible under the default five-fret span. Four
became feasible with a seven-fret span; three remained infeasible. This does not
prove the recording is physically unplayable: detected pitches/durations may be
wrong, the guitarist may use techniques outside this model, and the span is an
ergonomic simplification. It establishes that these seven failures were not
resolved merely by keeping more beam-search candidates.

The default span and detected notes were left unchanged. Automatically shortening
sustains, discarding notes, or widening the permitted stretch would require a
separate, explicitly evaluated musical policy. Saved detections permit review.

Reproduce locally with cached predictions:

```powershell
uv run python scripts/audit_fretting_constraints.py runs/eval-ml-all.json
```

The audit uses SciPy/HiGHS already in the core environment, with a ten-second
per-instance solver limit. Limit/unknown status is not reported as an infeasibility
proof. Regressions cover a playable C chord and incompatible simultaneous notes
that both require the low E string. No ML inference or network is needed.

# Timing after export to a readable score

Saving a correct GP5 representation is different from preserving audio timing.
The score must use discrete note values. This audit measures the actual reopened
GP5 events, converted from ticks to seconds using the saved integer tempo, against
both the original detections and GuitarSet reference notes.

## Fixed development protocol

Use the cached Basic Pitch detections from the first ten seconds of all 360
GuitarSet excerpts, with unchanged fingering constraints and confidence settings.
Use the annotated nominal tempo, rounded as required by GP5. Test each supported
grid independently. No pitch model training, threshold tuning, note deletion,
onset correction, beat alignment, or automatic tempo estimation occurs.

Seven excerpts fail fingering before scoring. Of the remaining 353, two have
collisions on the 1/16 grid; 1/32 and 1/64 accept all 353. Compare grid accuracy
on the **same 351 excerpts** that successfully export on every grid:

| Representation | Pitch/onset F1 | F1 also checking endings | Score segments |
| --- | ---: | ---: | ---: |
| Original detections, before score rounding | 74.5% | 51.7% | — |
| Saved GP5, 1/16 grid | 66.4% | 41.5% | 17,215 |
| Saved GP5, 1/32 grid | 73.1% | 49.3% | 27,019 |
| Saved GP5, 1/64 grid | 74.3% | 51.2% | 49,920 |

Metrics use the existing one-to-one matching policy in EVALUATION.md. Score
segments count beats in the GP5 voice, including rests and tied continuations,
not unique note attacks. They provide a complexity indicator, not a validated
measure of readability. Finer grids retain performance timing better but can
produce much more fragmented notation. No grid repairs incorrect detections.

Across each grid's successful clips, the 95th percentile absolute movement of
note starts from their detected times was 60.1 ms on 1/16, 34.4 ms on 1/32, and
17.3 ms on 1/64. These are movement amounts, not errors against ground truth.
The per-grid cohorts differ by two excerpts; use the common-cohort table for
accuracy comparisons. Full aggregate counts and failures are in
`reports/score-timing.json`; per-track details remain under ignored `runs/`.

## What this changes

Every normal export now records `score_timing` in `notes.json`, computed from the
reopened score: note count, saved tempo, maximum movement of starts/endings, and
the number of starts moved by more than 50 ms. The CLI and desktop app show a
timing notice if that count is nonzero. A finer grid may help; the app can rebuild
saved detections without listening again. Original note times are unchanged.

The default remains 1/16 pending musical review. The warning threshold matches
the onset-evaluation tolerance; it is not a scientifically established threshold
of audibility or a guarantee that smaller movements are harmless. At 1/64 the
notice asks the user to review tempo/rhythm rather than suggesting an unavailable
finer grid. No detections or defaults are automatically adjusted.

Grid origin is audio time zero. We do not yet identify the downbeat, initial beat
phase, changing tempo, swing or triplets. Nominal BPM does not establish correct
metrical alignment. These remain development checks: Basic Pitch's recording-level
training overlap is unresolved (MODEL_PROVENANCE.md). Human listening and a new
recording are still needed before judging practical tab quality.

## Reproduce

```powershell
uv run python scripts/audit_score_timing.py runs/eval-ml-all.json
```

This reads the already-downloaded annotation archive and cached detections. It
serializes and reopens each successful score, verifies its note events, and
compares the decoded times with reference notes. No ML imports, downloads, paid
services, or GPU are needed. Regression checks cover tick-to-second conversion,
cross-measure ties, short-note extension, chord timing movement, and warning
delivery without changing saved detections.

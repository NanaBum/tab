# A single global time shift for note comparisons

The local comparison tool preserves the original timing scores and also reports
what happens after one bounded time translation of the complete prediction.
This implements the proposed start-offset check without changing transcription
defaults, tempo, pitches, durations or source files.

```powershell
uv run python scripts/compare_timed_events.py reference.json predicted-detected-notes.json --max-shift 5 --step 0.01 --output runs/timed-comparison.json
```

Inputs currently support `tabber-note-events` JSON, this project's exported
`notes.json` (its original detected times, not the quantized GP5 times), and IDMT
annotation XML. General Guitar Pro/Songsterr import and automatic audio-to-score
alignment are still separate work; this tool does not fetch music or establish
dataset-use permission. It requires actual timed reference events, not just an
untimed list of frets.

## How to interpret the report

- `raw` contains pitch/attack F1 and release-aware F1 before alignment.
- `shifted` contains the same metrics after one translation. A negative
  `prediction_shift_seconds` moves predictions earlier; a positive value moves
  them later. Attacks and releases move together.
- The default search is within plus/minus five seconds on a 10 ms grid. The
  requested bounds and zero are included, even if a bound is not a grid multiple.
  At most 10,001 candidate shifts are allowed.
- Selection maximizes same-pitch attack matches within the supplied tolerance
  (default 50 ms), then minimizes absolute onset residual for the sorted matching,
  then prefers the smallest absolute shift. This is a finite-grid result, not
  an exact continuous optimum or minimum-error matching claim.
- Separated equally good shifts are flagged as ambiguous, as can happen for
  repeated riffs. A winning shift at the requested boundary is flagged too.

Every reference and prediction remains in the counts. Duplicate detections do
not earn repeated credit for one reference. Negative shifted times are handled
by moving both comparison timelines to a common nonnegative origin; early noise
is not clipped away. Durations, wrong notes and unmatched notes remain intact.
There is no local time warping, tempo scaling, section reordering or note deletion.

The shifted result is explicitly **reference-assisted**: the same reference
selects and scores the offset. It is useful as a diagnostic, but does not replace
the original timing benchmark or an independently calibrated alignment. A global
shift cannot resolve tempo drift, the wrong recording version, omitted sections,
multiple guitar parts or incorrect tabs. An untimed reference cannot verify rhythm.

## Existing electric-guitar examples

All eight previously fixed IDMT pieces/licks were compared for each unchanged
model using a plus/minus one-second search and a 10 ms step. No ML inference was
rerun. The [saved report](reports/idmt-global-shift.json) retains raw and shifted
scores, note counts, per-track shifts and source hashes.

| Model | Original pitch/attack F1 | Shifted diagnostic | Original release-aware F1 | Shifted diagnostic |
| --- | ---: | ---: | ---: | ---: |
| Experimental guitar-GAPS | 86.8% | 91.8% | 67.3% | 71.7% |
| Basic Pitch | 80.5% | 82.2% | 60.1% | 64.7% |

These are comparisons of the same detections, not improved model outputs. The
selected guitar-model shifts ranged from -40 to +10 ms; Basic Pitch shifts ranged
from -20 to 0 ms. They could reflect detection latency, reference timing or a
combination; this experiment cannot distinguish those causes. The existing
reference-label and checkpoint training-overlap caveats still apply.

For example, reproduce one track with:

```powershell
.venv/Scripts/python.exe scripts/compare_timed_events.py data/idmt/dataset2/annotation/AR_Lick1_KN.xml runs/idmt-licks-guitar-gaps/AR_Lick1_KN/detected-notes.json --max-shift 1 --step 0.01 --output runs/lick-global-shift.json
```

Apply the same command to each track named in the report, using the saved events
from the corresponding IDMT evaluator run. Aggregate F1 is twice the sum of
matched events divided by the sum of reference and predicted events. Reproduction
of those detections is documented in [IDMT_VALIDATION.md](IDMT_VALIDATION.md).

## Matching full-song event lists

The underlying one-to-one matcher now builds only same-pitch, nearby-onset
candidate edges rather than a dense array of every reference/prediction pair.
Release-aware matching retains the same optional end-time condition. It fails
explicitly above two million candidate edges to avoid runaway duplicate data.
Small random cases were checked against an independent dense matching oracle;
a 5,000-event comparison and alternative release assignments also passed.

Tests additionally cover known shifts in both directions, retained early noise,
repeated-pattern ambiguity, unchanged source bytes, real exported note-file
reading, input-overwrite refusal, tempo drift and invalid search limits.

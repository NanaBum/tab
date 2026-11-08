# Simple detector versus ML on the fixed electric examples

The deterministic autocorrelation detector was evaluated on the same eleven
recordings already used for the two ML methods: five electric pieces, three
picked licks and three muted counterparts. All settings were fixed. No new
audio, model training or ML inference was needed. This adds a control comparison;
it does not change the desktop default or select thresholds using the answers.

## Original timing results

There are 224 reference events across the eleven recordings. Counts are summed
before computing micro F1; individual track F1 values are not averaged.

| Method | Detections | Pitch/attack matches | Pitch/attack F1 | With release timing |
| --- | ---: | ---: | ---: | ---: |
| Simple detector | 143 | 91 | 49.6% | 26.7% |
| Basic Pitch | 253 | 190 | 79.7% | 57.4% |
| Experimental guitar-GAPS | 219 | 192 | 86.7% | 63.7% |

Pitch must match exactly and attacks within 50 ms; release-aware matches also
require releases within max(50 ms, 20% reference duration). These are note-event
scores, not percentages of a correct tab or musical quality ratings.

| Fixed condition | Simple detector | Basic Pitch | Guitar-GAPS |
| --- | ---: | ---: | ---: |
| Five pieces, 90 reference events | 38.3% | 82.8% | 85.2% |
| Three picked licks, 67 events | 49.6% | 77.7% | 88.9% |
| Three muted licks, 67 events | 64.2% | 77.6% | 86.4% |

The second table reports pitch/attack F1 at original timings. The baseline's
monophonic assumptions and note grouping are significant limits on these mixed
examples. Its requested confidence is 0.5, with the existing internal 0.65 floor;
standard tuning keeps the original 75 Hz search band. See [TUNING.md](TUNING.md)
for the separate explicit low-tuning extension.

## Keep individual failures visible

On `AR_Lick6_MN`, the simple detector produced nine detections and matched six of
ten reference attacks. Guitar-GAPS produced/matched four; Basic Pitch one. Thus
neither aggregate ranking nor detection count predicts which method will do
best on every recording. The baseline still has three unmatched detections and
four unmatched reference attacks on this example. No output was hand-corrected.

All eleven new baseline outputs exported every detection and passed GP5 readback.
The 33-pair manifest comparison (eleven recordings, three methods) reproduced
every saved per-recording raw metric exactly. It retained related picked/muted
performances and mono/poly arrangements under shared song groups. Complete local
reports and manifest are under ignored `runs/baseline-electric-control/`; the
[public summary](reports/electric-baseline-control.json) contains aggregates,
per-track metrics and source hashes, without audio or full note sequences.

The report also preserves a reference-fitted single-shift diagnostic: aggregate
pitch/attack F1 becomes 55.0%, 81.3% and 91.6% respectively. These offsets are
chosen using each reference and are not independently calibrated improvements.
Original timing results above remain the primary comparison. No source notes
are moved or deleted. See [GLOBAL_ALIGNMENT.md](GLOBAL_ALIGNMENT.md).

## Reproduce the new control

```powershell
uv run python scripts/evaluate_idmt_subset.py --selection pieces --backend baseline --output runs/baseline-electric-control/pieces
uv run python scripts/evaluate_idmt_subset.py --selection licks --backend baseline --output runs/baseline-electric-control/licks
uv run python scripts/evaluate_idmt_subset.py --selection muted --backend baseline --output runs/baseline-electric-control/muted
```

Selection downloads, original ML reproduction commands and attribution are in
[IDMT_VALIDATION.md](IDMT_VALIDATION.md). All examples remain clean isolated
electric guitar, not distortion or full-band mixes. Eleven source string/fret
entries contradict their supplied pitch: pitches/timings remain unchanged, and
only those positions are excluded from conditional fingering scoring. Exact ML
checkpoint training overlap remains unresolved. Related performances are not
independent songs, and these are development results, not an unseen-song benchmark.

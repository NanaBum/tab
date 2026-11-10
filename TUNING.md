# Explicit guitar tuning

The app offers `standard`, `drop-d`, `eb-standard` and `d-standard`. Standard is
still selected on startup. Choose the tuning actually used in the recording;
the program does not infer it. The command line also accepts six comma-separated
MIDI open-string pitches, in physical string order 1 through 6 (thin to thick):

| Preset | MIDI open pitches, strings 1–6 |
| --- | --- |
| standard | 64, 59, 55, 50, 45, 40 |
| drop-d | 64, 59, 55, 50, 45, 38 |
| eb-standard | 63, 58, 54, 49, 44, 39 |
| d-standard | 62, 57, 53, 48, 43, 38 |

```powershell
uv run tabber riff.wav --backend basic-pitch --tuning drop-d --bpm 120 --output runs/drop-d
uv run tabber --events runs/earlier/detected-notes.json --tuning 64,59,55,50,45,36 --bpm 120 --output runs/custom-tuning
```

Rebuilding saved notes requires an explicit tuning choice again; it defaults to
standard rather than guessing from an earlier file. The original event file
remains unchanged. Existing manual TuxGuitar edits are not carried over by replay.

This changes the available string/fret positions, optional range-filter bounds,
GP5 string declarations and text labels. It does **not** transpose, add or remove
detected notes, retune audio, or change the ML model. Range filtering remains a
separate explicit option, saving raw events and every exclusion with selected
tuning metadata. The normal five-fret span also remains unchanged. Core export
still supports six strings and frets 0–24, without capo or microtonal pitches.

Saved GP5 files are parsed back and checked against the requested tuning and
every intended attack/tie. Original pitches remain in MIDI and JSON. JSON records
`tuning_midi` and physical string order; alternate-tuning exports use
`string_order: string 1 to string 6`, while standard retains its legacy label.
The timed-note readers accept both forms. The short untimed standard-tuning
position-list comparator remains standard-only; use timed events for other tunings.
The experimental string-tone model is also refused for nonstandard tuning,
because its training/evaluation assumptions have not been checked there.

## What is verified

All four presets preserve six simultaneous held open strings, including ties
across a bar, through fretting, GP5 save/readback, MIDI and reference reimport.
An actual saved-note CLI rebuild placed MIDI 38 on string 6 fret 0 and retained
all seven known synthetic events. The optional range audit keeps low D (38) and
reports every excluded event. The desktop selector and complete layout were
visually checked with standard tuning selected and all four choices present.

These are routing and file checks, not proof of real alternate-tuned guitar
accuracy. A seven-tone synthetic audio trial exposed a detection limitation:
the simple baseline and Basic Pitch both missed low D and exported the remaining
six notes at their original settings. The baseline's fixed 75 Hz lower search
bound excluded low D at approximately 73.42 Hz; Basic Pitch's cause is not
established. This initial result is retained in the earlier routing report.

The simple detector now uses an explicit tuning's lowest open pitch to extend
its search band when necessary, with half a semitone of margin. Standard and
E-flat standard retain exactly the original 75 Hz floor; Drop D and D standard
use approximately 71.3 Hz. Low custom tunings also get an analysis window long
enough for four cycles (at least the original 80 ms). It remains a monophonic
autocorrelation baseline, with unchanged confidence and note-duration thresholds.
This is not pitch transposition, tuning inference or an extra range filter.
The CLI prints the extended band and records it in detection metadata.

On the same unmodified synthetic audio, explicit Drop D now detects/exports all
seven events, including string 6 fret 0. Default baseline events on all 11 saved
real electric recordings were identical to the prior implementation, including
timings and confidence. Both ML models remain unchanged; the Basic Pitch miss
is not repaired by selecting a tuning. Real alternate-tuned recordings and broader
model evaluation remain further work.

[drop-d-routing-check.json](reports/drop-d-routing-check.json) keeps the audio
detection result separate from the successful known-event rebuild.
[baseline-tuning-check.json](reports/baseline-tuning-check.json) records the later
tuning-aware baseline check and the default-output regression comparison.

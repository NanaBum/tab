# Explicit guitar tuning

The app offers six- and seven-string presets. Standard is selected on startup.
Choose the tuning used in the recording. You can also enter six or seven
comma-separated MIDI open-string pitches in the app or command line, ordered
from the thinnest string to the thickest.

| Preset | MIDI open pitches, thin to thick |
| --- | --- |
| standard | 64, 59, 55, 50, 45, 40 |
| drop-d | 64, 59, 55, 50, 45, 38 |
| drop-c-sharp | 63, 58, 54, 49, 44, 37 |
| eb-standard | 63, 58, 54, 49, 44, 39 |
| d-standard | 62, 57, 53, 48, 43, 38 |
| seven-string-standard | 64, 59, 55, 50, 45, 40, 35 |
| seven-string-drop-a | 64, 59, 55, 50, 45, 40, 33 |

```powershell
uv run tabber riff.wav --backend basic-pitch --tuning drop-d --bpm 120 --output runs/drop-d
uv run tabber --events runs/earlier/detected-notes.json --tuning 64,59,55,50,45,36 --bpm 120 --output runs/custom-tuning
```

Rebuilding saved notes restores the tuning recorded in the event file. Select
another preset in the app or pass `--tuning` to override it. With older files
that have no saved tuning, review the desktop selection before exporting. The
command line uses standard tuning for those files when `--tuning` is omitted.

This changes the available string/fret positions, optional range-filter bounds,
GP5 string declarations and text labels. It does **not** transpose, add or remove
detected notes, retune audio, or change the ML model. Range filtering remains a
separate explicit option, saving raw events and every exclusion with selected
tuning metadata. GP5 export supports six or seven strings and frets 0–24. For capoed
recordings, supplying the effective open pitches gives fret numbers relative to
the capo. GP5 output does not mark a capo position.

Saved GP5 files are parsed back and checked against the requested tuning and
every intended attack/tie. Original detections remain in the saved event JSON and
can be auditioned with notes-only MIDI. JSON records
`tuning_midi` and physical string order. Alternate tunings use a numbered
string order, and six-string standard retains its legacy label.
The timed-note readers accept both forms. The short untimed standard-tuning
position-list comparator remains standard-only; use timed events for other tunings.
The experimental string-tone model is also refused for nonstandard tuning,
because its training/evaluation assumptions have not been checked there.

## What is verified

The preset checks preserve all simultaneous held open strings, including ties
across a bar, through fretting, GP5 save/readback, MIDI and reference reimport.
An actual saved-note CLI rebuild placed MIDI 38 on string 6 fret 0 and retained
all seven known synthetic events. The optional range audit keeps low D (38) and
reports every excluded event.

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

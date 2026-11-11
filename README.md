# Tabber

A local, open-source app for turning guitar recordings into editable tabs. Exports include GP5 scores for TuxGuitar 2.1, MIDI playback, text tabs, and JSON
with original note
timings and suggested string/fret positions. The lightweight default detector is
monophonic; optional local Basic Pitch ML can detect chords and overlapping notes.
Fingering and transcription remain drafts requiring musical review.

An optional [guitar-specific model](GUITAR_MODEL.md) is also available in its own
CPU environment. Explicit [alternate tuning](TUNING.md) is available in the app and command line;
standard tuning remains the default. This changes fret mapping, not detected pitches.

## Quick start

### Windows desktop app

Run `uv sync --locked` from the repository folder, then double-click
**Start Tabber.cmd**. Choose an audio file, enter its tempo if known, and click
Create guitar tab. Use the simple melody detector for single-note audio or set
up the optional Basic Pitch environment below to select **Machine learning**.
Each conversion gets its own results folder. Open the editable GP5 in TuxGuitar
to play and correct it.
The app runs locally, offers note sensitivity and rhythm detail, and saves a log
when a conversion fails. It does not download dependencies or upload audio.

Use **Stop conversion** to stop a long run. Its log and any saved diagnostics
remain in that run's results folder; partial outputs are not a completed tab.
Wait for the stopped message before starting another run or closing the app.
See [CANCELLATION.md](CANCELLATION.md) for behavior and verification limits.

To inspect note detection independently of fingering, select **Save notes and
MIDI only (no tab)**. Use **Open MIDI** to audition the detected pitches and
timings; no guitar positions or score grid are applied. The normal editable-tab
mode remains the default. See [NOTES_ONLY.md](NOTES_ONLY.md).

To change tempo, time signature, or rhythm detail after listening once, choose **Rebuild saved
notes** under Method, then choose `detected-notes.json` from the earlier results
folder (or a timestamped detected file under `diagnostics/` after a fingering
failure). Choosing a saved notes file restores its BPM, guitar tuning, time signature, and rhythm
detail when available. **Use saved detections** also selects the unfiltered notes
and turns off separation. You can change these settings before creating a new tab.
The command line restores them when you omit `--bpm`, `--tuning`, `--meter`, and `--grid`.
Sensitivity does not filter saved input. Range exclusions and overlap recovery
are recorded alongside the original detections.
It assigns fingerings again and does not carry over edits made in TuxGuitar.

If overlapping detections cannot fit on distinct strings, the app can shorten
a sustain or omit a less certain note while keeping an audit and the original
detections. The [range filter](FRETTING_RECOVERY.md) can separately exclude
out-of-range detections when requested.

The desktop app needs Tkinter in the Python installation. The terminal setup
below also works without Tkinter.

### Terminal setup

Install Git and [uv](https://docs.astral.sh/uv/), then open a terminal in this folder:

```powershell
uv sync --locked
uv run python scripts/make_demo.py
uv run tabber runs/demo.wav --output runs/demo --bpm 120
```

Open `runs/demo/tab.gp5` in TuxGuitar (File > Open), then play or edit it and save
as `.tg` if desired. `tab.txt` is a plain-text preview. `notes.mid` provides playback in a MIDI player or DAW;
`notes.json` preserves detected timing, pitch, confidence, and fingering.
MIDI uses one channel per guitar string so overlapping unisons have independent
releases. Times round to 480 ticks per quarter note, with a minimum one-tick
duration.
`detected-notes.json` is a separate editable note-event file, before fingering and
score quantization. To rebuild an edited detection without rerunning the audio:

```powershell
uv run tabber --events runs/demo/detected-notes.json --output runs/edited --bpm 120
```

Edit pitch, start, end, or confidence values in this event file; time units are
seconds. It uses `format: tabber-note-events` and `schema_version: 1`. Rebuilding
assigns fingerings again. It does not preserve manual TuxGuitar edits. Every audio
run also saves timestamped detections under `diagnostics/` before trying to assign
frets, so difficult outputs can be inspected without running ML again.
For your own audio:

```powershell
uv run tabber "C:/path/to/guitar.wav" --output runs/my-song --bpm 100
```

Use WAV or FLAC first. Format support depends on the installed libsndfile.
Optional local codec support adds M4A/AAC and other FFmpeg-readable audio without
altering the original file. Input measurements and notices help diagnose quiet,
possibly clipped, or cancelling stereo audio. See [AUDIO_INPUT.md](AUDIO_INPUT.md)
for the small separate decoder setup and the heuristic checks. Gain is not
changed automatically.
Supply a known quarter-note tempo, tap the beat in the app, or explicitly choose
`--bpm auto` (type `auto` in the app). Automatic tempo is provisional and needs the
ML environment. It analyzes at most the first 60 seconds and may follow half-time,
double-time, or other rhythmic groupings. It does not identify the downbeat or
changing tempo. The app keeps manual BPM as the default.
One text-tab cell is a sixteenth note by default. Dashes mean no new onset, not a measured
rest; exact durations are available in MIDI and JSON. GP5 defaults to 4/4 measures and
snaps starts and ends to sixteenth notes, with at least one cell per note. Gaps
become rests, and sustained notes split into tied durations across measures.
Set a known **Time signature** in the app or use `--meter 6/8` on the command
line. The setting applies to the entire tab, starting at the beginning of the
input. Tempo is still expressed in quarter-note BPM.
GP5 tempo is rounded to the nearest integer BPM (1-999). Original timings remain
unchanged in JSON and are approximated at MIDI tick resolution. If notes land
on the same string and score cell, polyphonic export tries another fingering
using the chosen tuning and grid. An unresolved collision prompts
you to choose a finer grid. For faster notes choose `--grid 32` or `--grid 64`
(divisions per whole note).
**Try a finer grid if notes collide** (`--retry-finer-grid`) is optional.
It tries the selected grid first and uses the next finer grid only when a
score collision prevents export. If a collision remains at 1/64, it can use
audited overlap recovery. The app reports and saves the grid it used.
Exports record score-timing movement in `notes.json` and show a notice if any
note starts moved by over 50 ms. A finer grid can preserve timing better but
make notation busier. Saved detections can be rebuilt without another ML pass.
Triplets, swing, meter changes, and expressive techniques are not yet represented.
Choose a six- or seven-string tuning preset in the app, or enter six or seven
comma-separated MIDI open-string pitches, from the thinnest string to the
thickest. The same values work with `--tuning`. Supply the tuning used in the
recording. See [TUNING.md](TUNING.md).

## Transcription limits

The simple melody detector can confuse harmonics with the notes being played and
may merge repeated notes. The optional models can detect overlapping pitches.
Review the resulting tab by ear, especially for distorted guitar or full-band
recordings. Tabber suggests playable string and fret positions based on the
detected notes and the selected tuning.

## Optional ML environments

The core uses Python 3.13 with lightweight dependencies. Keep the older ML stack in
a separate Python 3.11 environment to avoid changing the core lockfile:

```powershell
uv venv .venv-ml --python 3.11
uv pip sync --python .venv-ml/Scripts/python.exe requirements/ml-windows-py311.txt
.venv-ml/Scripts/tabber.exe guitar.wav --backend basic-pitch --output runs/ml --bpm 120
```

The lock above is for Windows/Python 3.11 and was installed and tested locally.
Its model weights are included with Basic Pitch; inference runs on the CPU with no
per-track service fee. ML needs hundreds of MB of installed dependencies. Keep
NumPy below 2 and setuptools below 81 for the older TensorFlow/resampy stack.
`requirements/ml.in` is the source for that lock. For other platforms resolve
that source in a separate Python 3.11 environment and use its `bin` executables;
those platforms have not been tested here.

`--min-confidence 0.5` is the default explicit event-confidence filter. Increase
it to reduce weak detections or lower it to retain more notes. Confidence scores
are model outputs, not calibrated probabilities. Original detected timings are
preserved in JSON/MIDI; GP5 timing is quantized to the chosen grid.

### Optional source separation

Demucs is isolated from both the core and the transcription ML environment:

```powershell
uv venv .venv-separation --python 3.11
uv pip sync --python .venv-separation/Scripts/python.exe requirements/separation-windows-py311.txt
.venv-ml/Scripts/python.exe -m tabber mixed-audio.wav --backend basic-pitch --separate --output runs/separated --bpm 120
```

This is a tested Windows/Python 3.11 CPU-only lock with PyTorch wheels from the
official PyTorch CPU index. The first run downloads about 52 MB of `htdemucs_6s`
weights into ignored `models/torch/`; subsequent inference can work offline.
The wrapper uses four CPU threads, no shift averaging, and seven-second segments.
It decodes through soundfile and materializes a temporary stereo WAV, avoiding a
mono expansion bug in Demucs 4.0.1 with modern PyTorch. The original is unchanged.
Formats unsupported by soundfile still need external conversion to WAV/FLAC.

The desktop app offers an experimental separation checkbox when this environment
exists. Leave it off for isolated guitar. Source separation can add artifacts or
remove guitar content, and the archived upstream model is not a guarantee for
arbitrary full songs.

## Development

```powershell
uv sync --locked
uv run pytest
uv run ruff check .
```

See AGENTS.md for conventions. The pipeline lives in `src/tabber/`, with separate
modules for separation, transcription, fingering, timing, and export. Use a branch
for each change and review before merging. The default branch carries locally
verified snapshots.

Tabber checks each saved GP5 against the intended score events.

Hosted CI is manual-only. Run the checks above locally.

## License

Tabber's source code and documentation are available under the [MIT License](LICENSE).
Installed dependencies and optional model weights have their own terms.

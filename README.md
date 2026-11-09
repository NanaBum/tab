# Tabber

A local audio-to-guitar-tab research prototype. Clean guitar audio becomes editable
GP5 scores for TuxGuitar 2.1, MIDI playback, text tabs, and JSON with original note
timings and suggested string/fret positions. The lightweight default detector is
monophonic; optional local Basic Pitch ML can detect chords and overlapping notes.
Fingering and transcription remain drafts requiring musical review.

An optional [guitar-specific model](GUITAR_MODEL.md) is also available in its own
CPU environment. It is experimental and keeps the existing defaults unchanged.
The [clean electric-guitar comparison](IDMT_VALIDATION.md) tests both models on
five additional recordings and documents inconsistencies in their reference tabs.
It also includes a separate three-lick comparison on another electric guitar.
A [simple-detector control](BASELINE_CONTROL.md) compares all eleven fixed
electric recordings with both ML methods, retaining individual failure cases.
For timed references, the [global-offset comparison](GLOBAL_ALIGNMENT.md) reports
both original scores and a bounded, reference-assisted start-shift diagnostic.
The [local Guitar Pro reference importer](REFERENCE_IMPORT.md) can prepare
candidate timed references with explicit track selection and score-feature checks.
Local [audio download and source-pair collection](MEDIA_COLLECTION.md) tools can
prepare explicit Songsterr/YouTube pairs with original audio, MP3, tab revision
identity and hashes. Packaging is separate from alignment and model training.
The [MIDI reference importer](MIDI_REFERENCES.md) can select source channels from
those bundles and preserve their playback timing as candidate note labels.
Explicit [alternate tuning](TUNING.md) is available in the app and command line;
standard tuning remains the default. This changes fret mapping, not detected pitches.

## Quick start

### On this Windows computer

Double-click **Start Tabber.cmd**. Choose an audio file, use Machine learning,
enter its tempo if known, and click Create guitar tab. Each conversion gets its
own results folder. Open the editable GP5 in TuxGuitar to play and correct it.
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

To change tempo or rhythm detail after listening once, choose **Rebuild saved
notes** under Method, then choose `detected-notes.json` from the earlier results
folder (or a timestamped detected file under `diagnostics/` after a fingering
failure). Enter a numeric BPM or tap it, leave separation off, and create a new
tab. Rebuilding keeps every saved note unless you explicitly select the optional
instrument-range filter; sensitivity does not filter saved input.
It assigns fingerings again and does not carry over edits made in TuxGuitar.

If export fails, [recovery controls](FRETTING_RECOVERY.md) can explicitly exclude
out-of-range detections with an audit, or allow a wider simultaneous fret span.
They are separate choices and remain off by default in the app.

The core and ML environments are already set up on the development computer.
For a fresh clone, follow the commands below; `uv sync` sets up the core app and
the separate ML recipe below enables Machine learning. Tkinter must be available
in the Python installation. The simple detector remains available without ML.

### Terminal setup

Install Git and [uv](https://docs.astral.sh/uv/), then open a terminal in this folder:

```powershell
uv sync
uv run python scripts/make_demo.py
uv run tabber runs/demo.wav --output runs/demo --bpm 120
```

Open `runs/demo/tab.gp5` in TuxGuitar (File > Open), then play or edit it and save
as `.tg` if desired. `tab.txt` is a plain-text preview. `notes.mid` provides playback in a MIDI player or DAW;
`notes.json` preserves detected timing, pitch, confidence, and fingering.
MIDI uses one channel per guitar string so overlapping unisons have independent
releases. Times round to 480 ticks per quarter note, with a minimum one-tick
duration. See [MIDI_VALIDATION.md](MIDI_VALIDATION.md) for the checks and limits.
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
rest; exact durations are available in MIDI and JSON. GP5 uses 4/4 measures and
snaps starts and ends to sixteenth notes, with at least one cell per note. Gaps
become rests, and sustained notes split into tied durations across measures.
GP5 tempo is rounded to the nearest integer BPM (1-999). Original timings remain
unchanged in JSON and are approximated at MIDI tick resolution. Grid collisions are rejected instead of discarding
notes. For faster notes choose `--grid 32` or `--grid 64` (divisions per whole note).
Exports record score-timing movement in `notes.json` and show a notice if any
note starts moved by over 50 ms. A finer grid can preserve timing better but
make notation busier. See [SCORE_TIMING.md](SCORE_TIMING.md) for the measured
tradeoff; saved detections can be rebuilt without another ML pass.
Triplets, swing, other meters, and expressive techniques are not yet represented.
Choose standard, Drop D, E-flat standard or D standard in the app; the command
line also accepts six explicit MIDI open-string pitches. Tuning is supplied by
the user and is not recognized automatically. See [TUNING.md](TUNING.md).

## What works and what remains

- Implemented: autocorrelation melody baseline, optional locally tested Basic
  Pitch, polyphonic fingering search that preserves sustained strings, 4/4 GP5
  with chords/rests/ties, MIDI/JSON/text, synthetic demo, and real-audio evaluation.
- Separate environments: lightweight core Python 3.13 and tested ML Python 3.11.
- Optional locally tested stage: Demucs guitar separation in its own CPU environment.
- Remaining: reliable beat/downbeat alignment, string identification on new guitars, expressive
  techniques, MusicXML export, and broader real-world musical review.

An optional, locally trained string-tone experiment is now available through
`--string-model`. It is off by default and has only been evaluated within the
GuitarSet domain. See [STRING_EXPERIMENT.md](STRING_EXPERIMENT.md) for the fixed
performer split, limitations, and training/reproduction commands. Weights are not
committed; they remain under ignored `models/`.

The baseline can confuse harmonics and octaves. Frame boundaries introduce timing
error, and adjacent repeated notes may merge. Fingering optimizes a simple movement
cost; it does not recover which string was actually played. The default fingering
search supports overlaps, up to six strings and a five-fret span; it rejects
conflicting detections rather than dropping notes. For strict melodic dynamic
programming choose `--fretting melodic`. Synthetic tests verify plumbing; real-audio
development results and their limitations are documented in [EVALUATION.md](EVALUATION.md).

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
arbitrary full songs. See [SEPARATION.md](SEPARATION.md) for the controlled test.

References: [Basic Pitch](https://github.com/spotify/basic-pitch),
[Demucs](https://github.com/facebookresearch/demucs).

## GuitarSet

[Original GuitarSet v1.1.0](https://zenodo.org/records/3371780) includes aligned
guitar audio and annotations. Review its license and citation requirements before
use. No datasets or weights are committed.

```powershell
uv run python scripts/download_guitarset.py
# Optional: also download the approximately 657 MB microphone recordings
uv run python scripts/download_guitarset.py --include-audio
```

The default downloads only the approximately 39 MB annotations. Archives are
checksum-verified and left for manual extraction under ignored `data/guitarset/`.
Do not mix excerpts from the same performer across train and test without documenting
the split; report pitch, onset, and string/fret accuracy separately.

## Development

```powershell
uv sync --locked
uv run pytest
uv run ruff check .
```

See AGENTS.md for conventions. The pipeline lives in `src/tabber/`, with separate
modules for separation, transcription, fingering, timing, and export. Use a branch
for each change and review before merging. Keep audio, data, weights, and secrets
outside Git. No project license has been selected yet.

[VALIDATION_STATUS.md](VALIDATION_STATUS.md) maps the working features to their
evidence and remaining acceptance checks. [INSTALL_VALIDATION.md](INSTALL_VALIDATION.md)
records a clean core installation outside the development checkout.

Each GP5 export is reopened and compared with its intended quantized note events
before output files are replaced. See [EXPORT_VALIDATION.md](EXPORT_VALIDATION.md)
for the corpus check and the tied-note reader workaround. This does not replace
checking the transcription musically in TuxGuitar.

The pretrained model's GuitarSet use and unresolved recording-level overlap are
documented in [MODEL_PROVENANCE.md](MODEL_PROVENANCE.md). Dataset results are
development checks, not proof of accuracy on a new guitar.

For a short single-note recording with a supplied string/fret sequence but no
reference timestamps, [SEQUENCE_EVALUATION.md](SEQUENCE_EVALUATION.md) describes
an offline sequence comparison. It reports wrong, missing and extra pitches,
plus conditional fingering agreement; it does not score rhythm.

Hosted CI is manual-only for now because GitHub reported an account billing block.
Run the checks above locally; pushes and pull requests do not start hosted jobs.

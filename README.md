# Tabber

A local audio-to-guitar-tab research prototype. Clean guitar audio becomes editable
GP5 scores for TuxGuitar 2.1, MIDI playback, text tabs, and JSON with original note
timings and suggested string/fret positions. The lightweight default detector is
monophonic; optional local Basic Pitch ML can detect chords and overlapping notes.
Fingering and transcription remain drafts requiring musical review.

## Quick start

### On this Windows computer

Double-click **Start Tabber.cmd**. Choose an audio file, use Machine learning,
enter its tempo if known, and click Create guitar tab. Each conversion gets its
own results folder. Open the editable GP5 in TuxGuitar to play and correct it.
The app runs locally, offers note sensitivity and rhythm detail, and saves a log
when a conversion fails. It does not download dependencies or upload audio.

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
Tempo is supplied by you; automatic tempo estimation is not implemented.
One text-tab cell is a sixteenth note by default. Dashes mean no new onset, not a measured
rest; exact durations are available in MIDI and JSON. GP5 uses 4/4 measures and
snaps starts and ends to sixteenth notes, with at least one cell per note. Gaps
become rests, and sustained notes split into tied durations across measures.
GP5 tempo is rounded to the nearest integer BPM (1-999). Original timings remain
unchanged in MIDI and JSON. Grid collisions are rejected instead of discarding
notes. For faster notes choose `--grid 32` or `--grid 64` (divisions per whole note).
Triplets, swing, other meters, and expressive techniques are not yet
represented. Standard tuning only in
the command line; the fretting function accepts other tunings.

## What works and what remains

- Implemented: autocorrelation melody baseline, optional locally tested Basic
  Pitch, polyphonic fingering search that preserves sustained strings, 4/4 GP5
  with chords/rests/ties, MIDI/JSON/text, synthetic demo, and real-audio evaluation.
- Separate environments: lightweight core Python 3.13 and tested ML Python 3.11.
- Optional untested adapter: Demucs guitar separation.
- Remaining: automatic tempo, timbre-based string identification, expressive
  techniques, MusicXML export, and broader real-world musical review.

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

Demucs is not part of the tested ML lock. Its adapter uses `htdemucs_6s` with
`--separate`, but requires a separately installed Demucs environment, FFmpeg for
some formats, and a first-use weight download. Upstream is archived. This path
has not yet been tested; do not assume mixed-band audio is solved.

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

Hosted CI is manual-only for now because GitHub reported an account billing block.
Run the checks above locally; pushes and pull requests do not start hosted jobs.

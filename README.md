# Tabber

A local audio-to-guitar-tab research prototype. The first working path takes a
clean **single-note guitar melody** and writes text tablature, MIDI, and JSON with
note timings and suggested string/fret positions, plus editable GP5 scores for
TuxGuitar 2.1. This is an early baseline,
not an accurate full-song or chord transcriber.

## Quick start

Install Git and [uv](https://docs.astral.sh/uv/), then open a terminal in this folder:

```powershell
uv sync
uv run python scripts/make_demo.py
uv run tabber runs/demo.wav --output runs/demo --bpm 120
```

Open `runs/demo/tab.gp5` in TuxGuitar (File > Open), then play or edit it and save
as `.tg` if desired. `tab.txt` is a plain-text preview. `notes.mid` provides playback in a MIDI player or DAW;
`notes.json` preserves detected timing, pitch, confidence, and fingering.
For your own audio:

```powershell
uv run tabber "C:/path/to/guitar.wav" --output runs/my-song --bpm 100
```

Use WAV or FLAC first. Format support depends on the installed libsndfile.
Tempo is supplied by you; automatic tempo estimation is not implemented.
One text-tab cell is a sixteenth note. Dashes mean no new onset, not a measured
rest; exact durations are available in MIDI and JSON. GP5 uses 4/4 measures and
snaps starts and ends to sixteenth notes, with at least one cell per note. Gaps
become rests, and sustained notes split into tied durations across measures.
GP5 tempo is rounded to the nearest integer BPM (1-999). Original timings remain
unchanged in MIDI and JSON. Grid collisions are rejected instead of discarding
notes. Triplets, swing, other meters, and expressive techniques are not yet
represented. Standard tuning only in
the command line; the fretting function accepts other tunings.

## What works and what remains

- Implemented: autocorrelation melody baseline, dynamic-programming melodic
  fingering, supplied-tempo grid, text/JSON/MIDI/GP5 export, synthetic demo, tests.
- Optional adapters: Basic Pitch pitch detection and Demucs guitar separation.
  These are not installed or validated by the core setup.
- Remaining: chord-aware fingering, repeated-note onset detection, real GuitarSet
  evaluation, automatic tempo, expressive techniques, MusicXML export, UI.

The baseline can confuse harmonics and octaves. Frame boundaries introduce timing
error, and adjacent repeated notes may merge. Fingering optimizes a simple movement
cost; it does not recover which string was actually played. Overlapping notes are
rejected explicitly until chord-aware assignment exists. Synthetic tests verify
plumbing and basic pitch recovery, not real-world accuracy.

## Optional ML environments

The core uses Python 3.13 with lightweight dependencies. Keep the older ML stack in
a separate Python 3.11 environment to avoid changing the core lockfile:

```powershell
uv venv .venv-ml --python 3.11
uv pip install --python .venv-ml/Scripts/python.exe -e . basic-pitch demucs
.venv-ml/Scripts/tabber.exe guitar.wav --backend basic-pitch --output runs/ml
```

On Linux/macOS use `.venv-ml/bin/python` and `.venv-ml/bin/tabber` instead.
These optional packages may require platform-specific dependency fixes. Demucs
also needs FFmpeg for some input formats and downloads model weights on first use.
To request separation, add `--separate`; it uses the experimental `htdemucs_6s`
model's guitar stem. Demucs upstream is archived. Chord output from Basic Pitch
still requires the planned chord-aware fingering stage.

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

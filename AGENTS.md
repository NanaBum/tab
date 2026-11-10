# Project instructions

Goal: a local audio-to-guitar-tab app. Never imply that a
synthetic test establishes accuracy on real recordings.

Setup: `uv sync`. Checks: `uv run pytest` and `uv run ruff check .`.
Demo: `uv run python scripts/make_demo.py`, then
`uv run tabber runs/demo.wav --output runs/demo --bpm 120`.

Pipeline: separate.py -> transcribe.py -> fretting.py -> rhythm.py -> export.py.
gp5.py builds editable 4/4 scores on a sixteenth-note grid; test saved files by
parsing them again and verifying attacks, ties, rests, tuning, and bar lengths.
Core records live in models.py. All times are seconds; pitches are MIDI integers.
String 0 is physical string 1 (normally high E); standard tuning defaults to
(64, 59, 55, 50, 45, 40). Explicit tuning must flow through fretting, range audits,
GP5 validation and JSON/text labeling. Never infer tuning or transpose detections.
Frets are zero-based (0 means open). Always preserve the original event timings.
Prioritize note and timing accuracy. Use the existing fretting solver for tab export. Notes-only output must bypass fretting
and score-grid snapping, preserve all delivered events, and keep range exclusion
explicit.

Keep data/, models/, runs/, audio, weights and credentials out of Git.
Use branches for changes; never force-push. Preserve existing remote work.
Periodically merge locally verified working snapshots into `main` for public use.
Review the diff for private data and check the documented install and demo first.
Add meaningful tests for changes to transcription, timing, or fingering behavior.
Keep heavy ML dependencies optional and document their separate environments.
Use local computing for now. Do not start paid cloud jobs or increase spending
limits. Hosted CI is manual-only until the user chooses to use it.
The baseline detector is monophonic; the ML/fingering/GP5 path supports overlaps.
Never silently drop notes to make a fingering or export succeed. Confidence
thresholding must be explicit and documented. Polyphonic fingering is heuristic.
Opt-in instrument-range filtering must preserve unfiltered events and an indexed
exclusion audit. Keep it off by default; never silently widen the five-fret span.
Core tests must not import TensorFlow. Keep ML pins in requirements/ml.in and the
Windows/Python 3.11 lock separate from uv.lock. These paths are tested locally.

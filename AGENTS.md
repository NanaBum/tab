# Project instructions

Goal: a local, measurable audio-to-guitar-tab research prototype. Never imply that a
synthetic test establishes accuracy on real recordings.

Setup: `uv sync`. Checks: `uv run pytest` and `uv run ruff check .`.
Demo: `uv run python scripts/make_demo.py`, then
`uv run tabber runs/demo.wav --output runs/demo --bpm 120`.

Pipeline: separate.py -> transcribe.py -> fretting.py -> rhythm.py -> export.py.
Core records live in models.py. All times are seconds; pitches are MIDI integers.
String 0 is high E; standard tuning is (64, 59, 55, 50, 45, 40).
Frets are zero-based (0 means open). Always preserve the original event timings.

Keep data/, models/, runs/, audio, weights and credentials out of Git.
Use branches for changes; never force-push. Preserve existing remote work.
Add meaningful tests for changes to transcription, timing, or fingering behavior.
Keep heavy ML dependencies optional and document their separate environments.
The baseline is monophonic; do not silently drop overlapping notes.
Do not train models or download large datasets without explaining size and purpose.

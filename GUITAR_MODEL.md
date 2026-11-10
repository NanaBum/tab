# Optional guitar-specific model

The experimental `guitar-gaps` backend runs a published guitar transcription
checkpoint locally on CPU. It predicts pitches, attacks and releases, then uses
the existing fingering and export stages. It does not directly predict strings,
frets, bends or a native TuxGuitar file. GP5 opens in TuxGuitar for editing.
Basic Pitch remains the desktop default; the simple detector remains the CLI default.

## Reproduce on Windows / Python 3.11

```powershell
uv venv .venv-guitar --python 3.11
uv pip sync --python .venv-guitar/Scripts/python.exe requirements/guitar-windows-py311.txt
.venv-guitar/Scripts/python.exe scripts/download_guitar_model.py
.venv-guitar/Scripts/python.exe -m tabber path/to/riff.wav --backend guitar-gaps --bpm 120 --grid 32 --output runs/guitar-test
```

The explicit download is 99,256,753 bytes (about 99 MB). Inference never downloads
weights automatically or uploads recordings. Dependencies, audio and weights stay
outside Git. The desktop offers **Guitar model (experimental)** when its separate
environment and checkpoint exist. No training or fine-tuning is performed.

`--onset-threshold` defaults to the author's 0.3; lower values admit weaker
attacks. Desktop More notes/Balanced/Fewer notes use 0.2/0.3/0.5. Other decoding
thresholds retain author defaults: offset 0.3, frame 0.1, pedal offset 0.2.
Every decoded note is retained, including false detections. Unplayable notes
cause an explicit export failure with saved diagnostics rather than silent removal.

This model's saved `confidence` is a nearby peak onset regression activation,
not a calibrated probability or the same quantity as Basic Pitch confidence.
`--min-confidence` values other than the neutral CLI default are rejected for
this backend. Use the attack threshold rather than comparing scores across models.

## Identity and loading

- Published weights: [xavriley/midi-transcription-models](https://huggingface.co/xavriley/midi-transcription-models),
  revision `b7bec65a2b860aca72856b0feef58b5df407b777`.
- File: `guitar-gaps-paper-version-12200_iterations.pth`.
- SHA-256: `94a7c936ec9fde83686d29007dc256274384e832739cadece39e92cee3b69a7e`.
- Architecture/postprocessor dependency: [author's pinned fork](https://github.com/xavriley/piano_transcription_inference/tree/7568dc7f78b625e40cf9776e2806d164006610e3)
  of Kong's piano transcription implementation, using the guitar-trained weights.

Loading verifies the exact checksum before importing optional model code and
uses PyTorch's restricted `weights_only` loader, a scoped set of numeric NumPy
constructors for the checkpoint's sampler state, and strict model-key matching.
Input is converted to 16 kHz mono. Half-overlapping ten-second windows are
stitched using the upstream policy, then cropped in **frames** to the recording
duration before decoding. Original source audio is unchanged.

## Adjusting attack timing

To audition an earlier attack without running the detector again, rebuild
from its saved detections into a fresh folder:

```powershell
uv run tabber --events runs/original/detected-notes.json --attack-lead-ms 20 --bpm 120 --grid 64 --output runs/earlier-attacks
```

The option advances attacks by up to the requested amount and keeps release
times. Each attack stops at the most recent prior release to avoid adding
overlaps. Original detections remain in `detected-notes.json`. The adjusted
events and counts are in `diagnostics/`. The chosen grid can still put
different attacks in the same cell, so compare using a finer grid if export
reports a collision.

An audible guitar stem can still produce weak attack scores. If the guitar
model returns no notes, try Basic Pitch on the same input. Lower attack
thresholds may add spurious detections.

For an opt-in second attempt, add `--guitar-retry-empty` to a
`--backend guitar-gaps` command. This retries at half input level only
if the first pass returns zero notes. The retry uses the same attack
threshold and guitar audio, including a separated stem if requested.
The original recording and first-pass diagnostics are preserved.

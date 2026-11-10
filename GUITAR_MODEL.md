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

## Evaluation limits

The initial fixed six-solo/six-accompaniment smoke check (first ten seconds,
performer round-robin) is saved in [reports/gaps-smoke.json](reports/gaps-smoke.json).
Pitch/onset F1 was 94.7% solo and 95.4% accompaniment; including release timing
gave 88.2% and 78.7%. Eleven clips exported all detections. The remaining clip
failed at the 39th event (MIDI pitch 62) under the five-fret span constraint;
all its pitches were in range and no note was dropped. A later exact constraint
audit proved the fixed detections infeasible with a five-fret span and feasible
with seven. The earlier wording incorrectly called this a MIDI-39 detection.
The [recovery workflow](FRETTING_RECOVERY.md) documents the exact audit and a
later successful seven-fret rebuild, preserving all 57 detections.
These small checks do not establish performance on other recordings.

With the existing GuitarSet archives, reproduce each mode using:

```powershell
.venv-guitar/Scripts/python.exe scripts/evaluate_guitarset.py --backend guitar-gaps --mode solo --limit 6 --seconds 10 --grid 32 --export-tabs --output runs/gaps-six-solo.json
.venv-guitar/Scripts/python.exe scripts/evaluate_guitarset.py --backend guitar-gaps --mode comp --limit 6 --seconds 10 --grid 32 --export-tabs --output runs/gaps-six-comp.json
```

A favorable result on a development riff is not proof of general accuracy on
electric guitars, distortion or full bands. Training-recording overlap for this
checkpoint has not been established. GuitarSet checks are development checks,
not an independent held-out benchmark. Timing, sustain, string assignment and
playability remain separate from an ordered pitch-sequence match. No private
recording or reference sequence is included in this repository.

## Attack sensitivity on electric guitar

Run `scripts/sweep_guitar_onsets.py` in the optional guitar environment to
compare several attack thresholds on the fixed 11-clip IDMT development set.
It runs the network once per clip and reports missed and extra pitch/onset
events for each threshold.

| Attack threshold | Missed | Extra |
| --- | ---: | ---: |
| 0.18 | 30 | 31 |
| 0.24 | 31 | 29 |
| 0.30 (default) | 32 | 27 |
| 0.36 | 32 | 26 |
| 0.42 | 32 | 24 |

The stricter 0.42 setting removed three extra events with the same match
count on this set. The more sensitive 0.18 setting recovered two attacks in
the difficult muted lick and added four extras across other clips. The
default scores and source hashes match the earlier runs on all 11 clips.
This is development evidence. Use `--onset-threshold` to try a setting for a
particular recording. See [the complete sweep](reports/gaps-onset-sweep.json).

A separate `scripts/evaluate_guitar_pitch_evidence.py` run tests a small
learned filter with each phrase group held out in turn. It uses onset,
same-pitch frame support, octave competition, and duration. The filter
missed more attacks than the fixed-threshold control. The
[development report](reports/gaps-pitch-evidence-check.json) also records
an earlier-attack timing comparison on electric and acoustic recordings.

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
reports a collision. On the electric development set, this capped 20 ms
adjustment increased onset matches from 192 to 199 and onset-plus-release
matches from 141 to 145. One piece lost two onset matches.

An audible guitar stem can still produce weak attack scores. If the guitar
model returns no notes, try Basic Pitch on the same input. Lower attack
thresholds may add spurious detections.

For an opt-in second attempt, add `--guitar-retry-empty` to a
`--backend guitar-gaps` command. This retries at half input level only
if the first pass returns zero notes. The retry uses the same attack
threshold and guitar audio, including a separated stem if requested.
The original recording and first-pass diagnostics are preserved.

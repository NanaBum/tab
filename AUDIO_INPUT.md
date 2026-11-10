# Local audio input checks and optional codecs

The CLI now prepares audio before tempo estimation, source separation, or pitch
detection. Supported soundfile formats are used directly without copying or
changing them. Unsupported formats, including the tested M4A/AAC input, can be
decoded locally into a new floating-point WAV under the run's diagnostics folder.
The source is never overwritten. The desktop chooser includes M4A and AAC.

## Optional decoder setup

Windows/Python 3.13, separate from the core, transcription and separation packages:

```powershell
uv venv .venv-audio --python 3.13
uv pip sync --python .venv-audio/Scripts/python.exe requirements/audio-windows-py313.txt
```

The hash-locked package is imageio-ffmpeg 0.8.1. Its Windows wheel is about
37 MiB and contains the decoder executable. Setup downloads it once; conversion
does not upload audio or install packages automatically. The environment is
already set up on the development computer. Core/ML dependency locks are unchanged.

Discovery checks an explicit `TABBER_FFMPEG` executable path, FFmpeg on PATH,
imageio-ffmpeg in the current environment, then the project's `.venv-audio`.
The last option lets either the core or ML interpreter use the small codec
environment. Outside a project checkout, install imageio-ffmpeg in the active
environment or supply FFmpeg through the other supported options. Missing codec
support produces a setup message. A failed conversion removes its partial WAV.
FFmpeg reads only local file/pipe protocols and selects the first audio stream.

## Measurements and notices

Read the prepared recording in bounded blocks and record duration, rate, channel
count, peak, RMS, mono RMS and the count of samples near full scale. Reject empty
files and non-finite sample values before ML. Normal finite silence is retained
as a low-level input, not turned into invented notes.

Save timestamped `audio-*.json` measurements under diagnostics before inference.
Also include them in detected-event metadata. Notices identify these heuristic
concerns:

- Peak below 0.01 (about -40 dBFS): very low recording level.
- More than 0.1% of samples with magnitude at least 0.999: check possible clipping.
- Multiple channels whose mono RMS is below 10% of channel RMS: check cancellation.

These are diagnostic thresholds, not validated audio-quality classifiers.
They do not establish why a recording is quiet or prove it is unusable. Notices
do not change gain, select a channel, remove noise, trim, discard notes, or tune
the model. The app displays them with successful results and failure messages.
Saved-note rebuilds skip all audio preparation and input measurements.

## Validation

Core regressions cover preserving supported inputs without needing a codec,
decoding to a separate file, cleaning up a failed decode, quiet stereo
cancellation over multiple blocks, non-finite audio, and keeping diagnostics
when transcription detects no notes. An actual app worker decoded a local M4A,
preserved its SHA-256 identity, saved input checks, and displayed a low-level
notice alongside the transcription failure. This proves input handling; it
does not establish transcription accuracy or recovery of quiet guitar audio.

The codec lock was synchronized and its installed dependencies checked locally.
No private recording or reference notes are included in the repository.

# Clean core installation check

The source milestone at local commit `68bd31d` was built into a source archive
and wheel using `uv build`. The wheel was installed without an editable checkout
into a fresh Python 3.13.1 environment. Core dependencies came from an export of
the existing `uv.lock`; installation used the local cache in offline mode.

The program was then run from a separate working directory. Its imported package
path was under the fresh environment's `site-packages`, and TensorFlow was absent.
This avoids accidentally testing the original editable development environment.

## Evidence

- Wheel: 33,557 bytes, with 17 package Python modules and normal distribution
  metadata. No recordings, datasets, weights, environments or private references
  were included.
- A generated eight-note C-major scale was transcribed by the installed baseline
  detector. All expected pitches were detected in order.
- The installed CLI exported GP5, MIDI, JSON and text on a 1/32 grid. Reopened GP5
  events matched all eight intended notes; MIDI retained all eight attacks.
- Rebuilding the saved events on a 1/64 grid preserved their original detections
  and produced another verified eight-note GP5 and MIDI file.
- `reports/install-smoke.json` records the wheel hash, interpreter, module count,
  expected pitches and result counts without machine-specific file paths.

This checks core packaging and CLI operation on Windows/Python 3.13. It does not
establish real-guitar accuracy, install optional ML/separation/codecs into the
fresh environment, validate another operating system, or verify TuxGuitar's UI.
The desktop launcher and automatic discovery of the separate project environments
are designed for a source checkout. An installed package needs its optional
dependencies/executables configured separately.

## Reproduction outline

From the repository, build and export locked core requirements:

```powershell
uv build
uv export --locked --no-dev --no-emit-project --output-file core-requirements.txt
```

Use a fresh environment outside the source checkout, synchronize that requirements
file, then install `dist/tabber-0.1.0-py3-none-any.whl` with `--no-deps`. Run from
another directory so imports cannot silently use local source. Create the
synthetic recording with `scripts/make_demo.py`, then use the installed interpreter
for `python -m tabber` and the saved-event rebuild described in README.md.
The offline flag works only when the necessary dependencies are already cached.

No core runtime code was changed for this check. The synthetic result is an
installation smoke test, not evidence that a difficult real recording works.

# GP5 serialization validation

Every normal export now serializes GP5 to memory, reopens it, and verifies that
the intended quantized attacks, durations, string/fret positions, tempo, tuning,
meter, and measure lengths survived before replacing any existing output files.
This verifies the file representation, not whether audio detection was correct,
the fingerings feel comfortable, or TuxGuitar playback sounds right.

## Corpus check

Using cached Basic Pitch detections from the first ten seconds of all 360
GuitarSet excerpts:

- Seven excerpts could not satisfy fingering constraints. They remained explicit
  failures; notes were not dropped to force an export.
- All 353 complete fingerings could be exported and reopened with exactly matching
  quantized note events. There were zero remaining serialization mismatches.
- The coarsest of the supported 1/16, 1/32, and 1/64 grids that accepted each clip
  was used. This is not a guarantee that every future clip will fit those grids.

The check initially found four mismatches in PyGuitarPro's *reader*. GP5 ties do
not store their own fret; they continue the preceding note on the same string.
PyGuitarPro 0.11 uses value-based list lookup for a partially read beat, while its
beat equality excludes the start time. Some later tied beats can therefore match
an earlier open-string tied beat and inherit fret zero incorrectly.

`read_gp5` reconstructs tied frets using chronological string history, without
patching the dependency globally or altering the exported music. A minimal
regression covers an open-string tie followed by a tied fretted note. The
serializer itself was not found to change those notes.

Additional deterministic generated-score checks cover six strings, independent
sustains, repeated attacks, multiple measures, all three grids, and integer or
fractional supplied tempo. A negative regression confirms an otherwise valid
file with changed pitch is rejected before output writing. Wrong tuning is also
rejected. The source audio and unquantized detected-note files stay separate.

## Reproduce

After producing a GuitarSet evaluation file with saved predictions:

```powershell
uv run python scripts/validate_gp5_exports.py runs/eval-ml-all.json
```

This uses cached detections and in-memory GP5 files; it needs no ML imports,
weights, network, or paid computing. Summary results are in
`reports/gp5-serialization.json`; detailed local results remain under ignored runs/.

TuxGuitar 2.1 visual/audio acceptance still requires the user because application
control was denied. File checks do not replace that musical review.

# Validation and remaining acceptance checks

This records the source milestone through PR #13 and the subsequent clean-install
check. It does not claim that the final guitar-transcription product is complete.

| Requirement | Inspected evidence | Status and practical limit |
| --- | --- | --- |
| Local pretrained ML path | Separate pinned Python 3.11 environment; EVALUATION.md and reports/guitarset-development.json | Working; evaluated on real GuitarSet audio. Exact pretrained training overlap is unresolved, so results are development checks. |
| Measurable comparison | Pitch/onset and offset matching; string/fret agreement; SEQUENCE_EVALUATION.md | Implemented. Untimed user references cannot establish rhythm accuracy; conditional fingering agreement is separate from overall note accuracy. |
| Editable guitar score | EXPORT_VALIDATION.md; reports/gp5-serialization.json | 353 successful fingerings round-tripped with matching quantized notes; seven explicit fingering failures. Human TuxGuitar acceptance remains pending. |
| Score timing | SCORE_TIMING.md; reports/score-timing.json | Actual reopened scores compared at all supported grids. Finer grids preserve timing better but fragment notation. Beat/downbeat alignment and expressive rhythm remain unresolved. |
| MIDI playback data | MIDI_VALIDATION.md; reports/midi-serialization.json | Independent string channels and releases verified, including overlapping unisons. Player sound and realism are not measured. |
| Optional string-tone model | STRING_EXPERIMENT.md; fixed split and rotating-performer reports | Experimental, off by default. Same recording domain and oracle-note checks do not establish new-guitar accuracy. |
| Optional source separation | SEPARATION.md; controlled-mixture report | Local CPU path works. Arbitrary real full bands remain unvalidated. |
| Local app and input | GUI worker checks; AUDIO_INPUT.md; 93 local tests | Core/ML workers, saved-note replay and real M4A preparation exercised. Input notices are heuristic; they do not repair inaudible recordings. |
| Reproducible core installation | INSTALL_VALIDATION.md; reports/install-smoke.json | Fresh installed wheel worked outside the source checkout without TensorFlow. Optional environments and other platforms were not part of this check. |
| User action list and handoff | Parent outputs/Your-to-do-list.md and Progress.md; DEVELOPMENT_STATE.md | Maintained locally. A usable replacement recording and TuxGuitar review still need the user. |
| Reviewable repository changes | Open stacked PRs #1–#13, inspected through the GitHub connection | Published and unmerged. Main is still bootstrap; inspect the current development branch for complete code. |
| Local/free computing boundary | Manual-only workflow; local environments and run outputs | No hosted test jobs were started, spending limits changed or paid transcription/compute services used. |

## What needs new evidence

A user recording must contain clearly audible guitar before it can give a fair
personal-instrument accuracy check. Keep model adaptation and any manual
corrections separate from the uncorrected result. Do not produce a supposed ML
tab by copying the supplied answer when detection fails.

TuxGuitar visual/playback acceptance requires the user's check or newly approved
app access. Earlier denied app access was not bypassed. The provided demos and
round-trip checks support that review but do not replace it.

Further musical policy changes (automatically shortening sustains, deleting
notes, relaxing stretch constraints or changing rhythm defaults) need explicit
evaluation. Passing existing format checks alone would not justify them.

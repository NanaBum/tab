# Tempo controls and their limits

Known quarter-note BPM remains the preferred input. The desktop app also has a
Tap tempo button: tap at least four times with the beat; it uses a median over
recent intervals and resets after a pause. Rapid accidental double taps are
ignored. Tap tempo is useful when you can hear the beat but do not know its BPM.

`--bpm auto`, or typing `auto` into the app, requests an optional local librosa
tempo estimate. It uses a 256-sample hop at 22,050 Hz and analyzes at most the first
60 seconds. Audio shorter than two seconds or silent/non-finite audio is rejected.
The app runs this through the ML environment even when the simple note detector
is chosen. No cloud or paid API is used.

The estimate is printed and saved in detected-note metadata. It does not establish
a downbeat, meter, changing tempo, or the intended beat grouping. Notes retain
their original seconds in JSON/MIDI; score durations use the chosen BPM/grid.
Saved events have no audio to estimate from, so rebuilding with --events requires
an explicit BPM.

## Development check

The first ten seconds of all 360 GuitarSet microphone excerpts were compared to
their nominal annotated tempos. This is a corpus development check, not a promise
for arbitrary music or a study of perceptual beat accuracy.

| Excerpts | Within 5% of nominal BPM | Within 5%, allowing half/double time |
| --- | ---: | ---: |
| 180 solo | 102 (56.7%) | 123 (68.3%) |
| 180 accompaniment | 94 (52.2%) | 106 (58.9%) |
| All 360 | 196 (54.4%) | 229 (63.6%) |

Every clip produced an estimate, but many did not match the annotated beat
grouping. For that reason, automatic tempo was kept optional and manual BPM stayed
the default. The synthetic 120 BPM melody was estimated at 120.2 BPM and exported
successfully through ML to GP5. It is a plumbing check, not evidence that every
song's tempo will be correct.

Reproduce with the downloaded archives and ML environment:

```powershell
.venv-ml/Scripts/python.exe scripts/evaluate_tempo.py
.venv-ml/Scripts/python.exe -m tabber guitar.wav --backend basic-pitch --bpm auto --output runs/auto-tempo
```

GuitarSet source and attribution: Xi et al., ISMIR 2018, GuitarSet v1.1.0,
https://zenodo.org/records/3371780, CC BY 4.0. The method uses librosa's dynamic
programming beat tracker: https://librosa.org/doc/0.11.0/generated/librosa.beat.beat_track.html

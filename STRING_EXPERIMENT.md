# Experimental string identification

The same pitch can be played on several strings. This optional local experiment
uses tone features to provide soft string preferences to the existing fingering
search. It never changes pitches or drops notes. It is off by default and is not
exposed as the normal desktop-app method.

## Model and evaluation protocol

- Source: GuitarSet v1.1.0 microphone audio, CC BY 4.0; Xi et al., ISMIR 2018.
  https://zenodo.org/records/3371780
- Fixed performer split, chosen before fitting: train 01–04, validation 05, test 00.
- Isolated solo-note windows start 30 ms after the annotated onset and contain at
  most 150 ms of audio. Windows shorter than 60 ms or overlapping another reference
  note are excluded. This yields 8,752 train, 1,964 validation, and 1,326 test notes.
- Features: one-hot known pitch plus 39 tone features (MFCC means/variation,
  normalized harmonic strengths, and a pitch-relative spectral centroid).
- StandardScaler fits only training notes. Multinomial logistic regression uses
  fixed C=1 and max_iter=2000. The comparison uses only the pitch features.
- Candidate strings outside frets 0–24 are masked. No hyperparameters were tuned
  on the held-out performer. This is one exploratory split, not a statistical study.

| Classifier | Validation string accuracy | Held-out performer string accuracy |
| --- | ---: | ---: |
| Pitch only | 72.1% | 62.1% |
| Pitch and tone | 76.8% | 82.1% |

Those figures use **oracle pitch, onset, and duration**. They do not describe
audio-to-tab accuracy, chord separation, or generalization to other guitars,
pickups, distortion, or microphones. Rare strings are imbalanced; full confusion
matrices and balanced accuracy are in reports/string-classification.json.

## Using it with detected notes

Inference applies tone preferences only to sufficiently long windows without other
detected notes. Mixed/short windows receive no preference and retain the original
ergonomic heuristic. The beam-search cost uses fixed prior weight 2. GP5 output
still follows the selected score grid. The file contains numeric arrays loaded
without pickle; weights and feature caches stay under ignored models/.

On the first 10 seconds of the 30 held-out-performer solo clips, the initial
end-to-end check improved exact string/fret agreement from 513/952 (53.9%) to
678/952 (71.2%) among pitch/onset matches in 29 complete fingerings. One clip
remained unplayable under the constraints. Pitch/onset F1 stayed 86.4% because
the pitch detector was unchanged. This is a conditional fingering measure; it
does not count missed/extra notes as correct, and is not overall tab accuracy.
Basic Pitch's own training overlap with GuitarSet has not been audited.

## Reproduce locally

Use the tested ML environment and downloaded GuitarSet archives:

```powershell
.venv-ml/Scripts/python.exe scripts/train_string_model.py
.venv-ml/Scripts/python.exe -m tabber guitar.wav --backend basic-pitch --string-model models/string-timbre-v1.npz --output runs/string-test --bpm 120
.venv-ml/Scripts/python.exe scripts/evaluate_guitarset.py --backend basic-pitch --mode solo --performer 00 --limit 30 --seconds 10 --string-model models/string-timbre-v1.npz --output runs/string-evaluation.json
```

Training took about 24 seconds on the development laptop, including feature
extraction. This is a run observation, not a standardized speed claim. No GPU,
paid compute, or additional dataset download was used. Test on the user's own
recordings before recommending this model or enabling it by default.

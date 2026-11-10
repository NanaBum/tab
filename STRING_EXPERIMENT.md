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
ergonomic heuristic. Both the melodic dynamic program and the polyphonic beam
search use fixed prior weight 2. To choose melodic fingering, pass
`--fretting melodic` with standard-tuned audio and `--string-model`. The model
uses isolated note windows in either mode. GP5 output
still follows the selected score grid. The file contains numeric arrays loaded
without pickle; weights and feature caches stay under ignored models/.

In a single IDMT electric-lick check, the melodic solver matched 11 of 13
annotated string/fret positions with its normal costs and 12 of 13 with the
saved timbre model. Both GP5 files contained the same 13 detected notes.
This checks the integration on one recording.

On the first 10 seconds of the 30 held-out-performer solo clips, the initial
end-to-end check improved exact string/fret agreement from 513/952 (53.9%) to
678/952 (71.2%) among pitch/onset matches in 29 complete fingerings. One clip
remained unplayable under the constraints. Pitch/onset F1 stayed 86.4% because
the pitch detector was unchanged. This is a conditional fingering measure; it
does not count missed/extra notes as correct, and is not overall tab accuracy.
Basic Pitch's own training overlap with GuitarSet has not been audited.

## Rotating-performer audit

The fixed model/features were also audited across six rotations. Each performer
was tested once, the preceding performer was held for validation, and the other
four supplied training notes. Scaling remained training-only and the parameters
were not tuned per test fold. This is exploratory cross-validation in the same
recording domain; it does not create a new-guitar test set or independent studies.

| Test performer | Pitch-only string accuracy | Pitch and tone |
| --- | ---: | ---: |
| 00 | 62.1% | 82.1% |
| 01 | 58.0% | 78.0% |
| 02 | 67.7% | 78.3% |
| 03 | 62.4% | 64.8% |
| 04 | 54.7% | 73.3% |
| 05 | 67.8% | 76.2% |
| Mean across performers | 62.1% | 75.4% |

Tone helped every rotation, but its held-out accuracy ranged from 64.8% to 82.1%.
The best initial performer should not be presented as typical accuracy. Pooled
note accuracy was 75.1% versus 61.8%; that weights performers by their different
note counts. All figures still use isolated notes with oracle pitch/timing.

The audit also records an open-versus-fretted diagnostic restricted to pitches
that can be either an open string or fretted elsewhere. It excludes low E, whose
string is forced, to avoid a misleading easy case. Those metrics are derived
from string decisions and are not a separately trained binary classifier.
The subset is imbalanced: held-out performers had only 0–47 reference open notes
among 177–450 eligible notes. Performer 05 had no positive open examples; its
reported binary F1 is zero by the configured convention, not a measured failure
to recognize positive examples. These results do not establish a reliable
open-versus-fretted classifier. Balanced same-pitch recordings are still needed.

Detailed fixed-protocol results are in reports/string-cross-validation.json.
Reproduce with `scripts/crossvalidate_string_model.py` after feature extraction.
The audit does not replace or overwrite the original optional inference model.

## Collected song labels

The GP7 importer can preserve written string/fret positions without changing
the existing pitch/onset references. Keep the new `-positions.json` files
beside those references. To count candidates in a verified excerpt package,
run `scripts/audit_string_label_windows.py PLAN MANIFEST --root SOURCE_ROOT
--output NEW_REPORT.json`. The audit rechecks the source references, alignment
evidence, and excerpt hashes. It keeps standard-tuned, capo-free positions
within the model's pitch range, and checks that no other selected guitar
note overlaps the feature window, including notes sustained into the excerpt.

The first audit found 101 candidates across the training partition and zero
in validation or test. These are score-derived candidates. The check cannot
establish whether an individual guitar is audible in a mixed recording or
whether the performer used the written position. Use a separate, independently
labeled evaluation set to assess a trained classifier.

## Reproduce locally

### Independent electric-guitar check

The saved GuitarSet model was tested on 11 labeled IDMT electric recordings
using their annotated pitch, onset, and duration. This isolates fingering
from note detection. On 80 isolated notes playable on multiple strings, the
classifier picked the right string 31 times using timbre and 33 times with
its timbre inputs held at their training means.

| Fingering cost | Correct among 80 ambiguous isolated notes | Correct among 198 consistent positions |
| --- | ---: | ---: |
| Ergonomic solver alone | 50 | 134 |
| Solver and pitch component | 36 | 119 |
| Solver and pitch plus timbre | 31 | 119 |

Ten recordings completed all three assignments. One contained an annotated
MIDI pitch below standard tuning and was excluded from solver totals. The
pitch-component comparison is an ablation of the same model. No weights
or costs were fit on IDMT. Keep this model experimental for electric guitar.

```powershell
.venv-ml/Scripts/python.exe scripts/evaluate_idmt_string_priors.py --data data/idmt --weights models/string-timbre-v1.npz --output runs/idmt-string-priors.json
```

### Original GuitarSet evaluation

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

# Clean electric-guitar development check

All five complete recordings in IDMT-SMT-Guitar subset 3 were evaluated with
unchanged model defaults: Basic Pitch confidence 0.5 and guitar-GAPS attack
threshold 0.3. The source XML identifies an **Ibanez RG 2820**, neck pickup and
standard tuning. These are clean electric recordings, including simultaneous
notes and ringing sustain. They are not distorted rock riffs or full-band mixes.

| Model | Reference notes | Detections | Pitch/attack matches | Pitch/attack F1 | With release timing |
| --- | ---: | ---: | ---: | ---: | ---: |
| Basic Pitch | 90 | 96 | 77 | 82.8% | 71.0% |
| Experimental guitar-GAPS | 90 | 93 | 78 | 85.2% | 67.8% |

Pitch must match exactly, attacks within 50 ms. The release-aware score also
requires releases within max(50 ms, 20% reference duration). Each reference and
prediction is matched at most once. These are event F1 scores, not percentages
of a correctly written tab. Both methods exported every detection on all five
recordings, with saved GP5 files reopened and verified. Export used provisional
120 BPM and a 1/32 grid for format checks, not a verified musical rhythm score.

The guitar model is slightly better for attacks in this small check, but worse
for releases. Basic Pitch remains the desktop default. Source training overlap
for the exact checkpoints is unresolved, so this is a development comparison.

## Annotation audit

Eleven of the 90 source entries have string/fret values inconsistent with their
declared MIDI pitch under the declared tuning. The reader records their indices,
retains every supplied pitch/timing target, and excludes only the inconsistent
positions from conditional string/fret agreement. It does not guess which field
is wrong or silently repair the answer. This uncertainty also limits the pitch
scores. Simultaneous notes and independent releases are retained.

The evaluator saves unmatched event details locally for inspection; the checked-in
summary contains aggregate scores, per-track counts, integrity hashes and audit
indices, without audio, source XML or complete note sequences.

## Additional picked electric licks

The next fixed selection uses `AR_Lick1_KN`, `AR_Lick6_KN` and `AR_Lick12_KN`
from the archive's dataset2 folder. Their XML identifies an Aristides 010,
Christian Kehling as performer/composer, picked excitation (`PK`), and normal
expression (`NO`). These are natural picked licks, not isolated test tones or
distorted/full-band audio. The selection was fixed before running either model.
All 67 source pitch/string/fret entries agree under the declared standard tuning.
The reader accepts the space-separated tuning declaration used by these files
as well as the comma-separated declaration in the earlier pieces.

| Model | Reference notes | Detections | Pitch/attack matches | Pitch/attack F1 | With release timing |
| --- | ---: | ---: | ---: | ---: | ---: |
| Basic Pitch | 67 | 90 | 61 | 77.7% | 47.1% |
| Experimental guitar-GAPS | 67 | 68 | 60 | 88.9% | 66.7% |

Both methods exported every detection on all three licks, without reference-based
note corrections. Guitar-GAPS made fewer extra detections overall, while Basic
Pitch matched one more reference attack. Guitar-GAPS matched the listed string
and fret on 44 of its 60 pitch/attack matches; this conditional measure is not
whole-tab accuracy. The summary is [reports/idmt-lick-comparison.json](reports/idmt-lick-comparison.json).
Default thresholds and model choices remain unchanged. These development results
do not establish general performance on other guitars, distortion or bands.

## Muted counterparts

A second fixed selection uses `AR_Lick1_MN`, `AR_Lick6_MN` and `AR_Lick12_MN`.
Each annotation labels every event `MU` (muted excitation) and `NO` (normal
expression), on the same Aristides 010. Their 67 pitch sequences match the
corresponding picked performances; these are separate recordings with their own
attack/release times. All source string/fret positions agree with supplied pitches.
These related performances belong in the same song groups in any future split.

| Model | Detections | Pitch/attack matches | Pitch/attack F1 | With release timing |
| --- | ---: | ---: | ---: | ---: |
| Basic Pitch | 67 | 52 / 67 | 77.6% | 50.7% |
| Experimental guitar-GAPS | 58 | 54 / 67 | 86.4% | 54.4% |

The aggregate hides an important failure: on the ten-note `AR_Lick6_MN`, Basic
Pitch detected/matched one event and guitar-GAPS detected/matched four. A fitted
single start shift did not recover those missing attacks. On `AR_Lick1_MN`, the
guitar model exported 13 detections with 12 raw pitch/attack matches; after a
reference-fitted -40 ms shift all 13 matched. The latter is an alignment diagnostic,
not an independent accuracy improvement. Per-track raw/shifted results and source
identities are in [reports/idmt-muted-comparison.json](reports/idmt-muted-comparison.json).

All six model/recording combinations exported every detected event and reopened
their GP5 outputs successfully. This establishes file validity, not a complete
transcription: missing detections remain missing. Guitar-GAPS matched the listed
fingering on 36 of its 54 raw pitch/attack matches; Basic Pitch on 33 of 52.
Release behavior and fingering remain limitations. A local listenable example is
at `Demos/Electric-muted-lick/` beside the other user-facing demos.

```powershell
.venv/Scripts/python.exe scripts/download_idmt_subset.py --selection muted
.venv-guitar/Scripts/python.exe scripts/evaluate_idmt_subset.py --selection muted
.venv-ml/Scripts/python.exe scripts/evaluate_idmt_subset.py --selection muted --backend basic-pitch
```

Initial selective retrieval transferred 4,357,796 bytes. A cached checksum check
transferred only the 703,197-byte archive directory. Files are under ignored
`data/idmt/muted/`, separately from the picked selection. No thresholds, gain,
model weights, fingering constraints or rhythmic preferences were changed. These
are muted clean-electric development recordings, not distorted or full-band audio;
training overlap for the checkpoints is still unresolved.

```powershell
.venv/Scripts/python.exe scripts/download_idmt_subset.py --selection licks
.venv-guitar/Scripts/python.exe scripts/evaluate_idmt_subset.py --selection licks
.venv-ml/Scripts/python.exe scripts/evaluate_idmt_subset.py --selection licks --backend basic-pitch
```

The six fixed lick files require about 4.74 MB including the archive directory.
Fresh and cached retrievals passed. Each selection has a separate default data
folder and each backend/selection has a separate default result folder.

## Reproduce

```powershell
.venv/Scripts/python.exe scripts/download_idmt_subset.py
.venv-guitar/Scripts/python.exe scripts/evaluate_idmt_subset.py --backend guitar-gaps --output runs/idmt-guitar-gaps
.venv-ml/Scripts/python.exe scripts/evaluate_idmt_subset.py --backend basic-pitch --output runs/idmt-basic-pitch
```

The downloader uses exact HTTP byte ranges to retrieve ten fixed files, about
4.86 MB including the ZIP directory, from the 1.33 GB archive. A server that
ignores ranges is rejected before reading its body. ZIP members are CRC-checked
on retrieval and matched against locally pinned SHA-256 values. Those hashes
identify the observed subset; the publisher's **whole-archive MD5 was not verified**.
A fresh retrieval and a cached checksum verification both completed locally.
No automatic fallback downloads the full archive. All data stays in ignored data/.

## Sources and use

[Fraunhofer's dataset page](https://www.idmt.fraunhofer.de/en/publications/datasets/guitar.html)
describes the recordings, annotations and evaluation use under CC BY-NC-ND 4.0.
Authors: Christian Kehling, Andreas Männchen and Arndt Eppler, Fraunhofer IDMT.
[Original release and archive](https://zenodo.org/records/7544110).
This project uses it only for local evaluation, without training or publishing
the audio or generated score files.

The [GAPS paper, section 4.1](https://arxiv.org/html/2408.08653v1#S4.SS1)
describes GAPS-only and GAPS-plus-GuitarSet variants and optional piano-model
initialization. GAPS itself contains classical nylon-string performances. The
[pinned model card](https://huggingface.co/xavriley/midi-transcription-models/blob/b7bec65a2b860aca72856b0feef58b5df407b777/README.md)
links the guitar papers but does not map this checkpoint to a precise training
manifest. Its filename alone cannot establish a zero-shot or unseen-data test.

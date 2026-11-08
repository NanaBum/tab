# Pretrained-model and evaluation-split audit

The later experimental GAPS guitar checkpoint has separate identity, loading and
evaluation caveats in [GUITAR_MODEL.md](GUITAR_MODEL.md). Its training-recording
overlap is unresolved; do not treat GuitarSet scores as independent validation.
The later [clean electric-guitar comparison](IDMT_VALIDATION.md) records the
paper's distinction between GAPS-only and GAPS-plus-GuitarSet variants. The pinned
model card does not identify which training manifest produced this checkpoint.

Audited November 7, 2026. The development runs used Basic Pitch 0.4.0 with
TensorFlow 2.14.0 and the package's ICASSP-2022 TensorFlow model. This project
did not train or fine-tune that pitch model. The small optional string-tone
classifier is a separate model, with its own documented performer splits.

## What the primary sources establish

The [original paper, section 4 and table 1](https://arxiv.org/abs/2203.09893)
explicitly includes GuitarSet in training and evaluation. It lists 648 training
and 72 test tracks and describes a random validation subset from training data.
Those published counts are not a list of recording IDs, and should not be used
to infer which of our 360 microphone excerpts were unseen.

The [0.4.0 training-data guide](https://github.com/spotify/basic-pitch/blob/v0.4.0/basic_pitch/data/README.md)
describes tooling for datasets used by the original model. The
[GuitarSet generator](https://github.com/spotify/basic-pitch/blob/v0.4.0/basic_pitch/data/datasets/guitarset.py#L115-L138)
shuffles track IDs before assigning splits. Its seed is optional; the
[command-line defaults](https://github.com/spotify/basic-pitch/blob/v0.4.0/basic_pitch/data/commandline.py#L61-L85)
use 80% training, 10% validation, and no fixed seed. These are generation defaults,
not evidence that the shipped model used a particular regenerated split.

An inspection of the complete v0.4.0 Git tree found the generator and dataset
tests, but no track-ID split manifest tied to the shipped weights. The
[release README](https://github.com/spotify/basic-pitch/blob/v0.4.0/README.md)
also warns that the software has evolved beyond the paper. Re-running today's
random splitter, choosing a seed ourselves, or holding out one performer from
our string classifier cannot establish that Basic Pitch never saw those notes.

**Conclusion:** GuitarSet training use is confirmed; exact recording overlap for
the installed weights remains unresolved. Keep all our GuitarSet pitch-detection
scores labeled development checks. Do not describe the string experiment's
end-to-end pitch detections as unseen-performer accuracy for Basic Pitch.

## Local model identity

The TensorFlow model files used locally have these SHA-256 digests. These identify
the files for reproduction; hashes do not reveal their training examples.

| File under `basic_pitch/saved_models/icassp_2022/nmp/` | Bytes | SHA-256 |
| --- | ---: | --- |
| `saved_model.pb` | 1084140 | `eaa25c91c431c91100c416a2c018663f4c635f28fa19529c4ff5e14c18aa29c9` |
| `variables/variables.data-00000-of-00001` | 219309 | `f5d12cd7245fecea0c956c963751f3519c263615ea954b5948d5e8c9c3376f9b` |
| `variables/variables.index` | 4794 | `356aa1a00095cf2dba17386144e8b289cb04195ae090aa7f324312b08220115e` |

No weights or recordings are committed. The pinned environment is in
`requirements/ml-windows-py311.txt`.

## Next evidence needed

An author-provided track manifest tied to these weights could resolve historical
overlap. Independently recorded, labeled examples from the user's guitar provide
a practical new-recording check without that dependency. Keep them reserved for
evaluation before adapting models to them, or explicitly separate calibration and
evaluation takes. A handful of examples is a useful acceptance check, not a
statistically broad benchmark. No public issue or message was sent to the authors.

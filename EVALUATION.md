# Local development evaluation

These are engineering checks, not held-out accuracy claims. A primary-source
audit confirms that Basic Pitch used GuitarSet for training, but could not tie
recording IDs to the installed weights. See [MODEL_PROVENANCE.md](MODEL_PROVENANCE.md)
for the evidence and model hashes. Do not advertise these scores as performance
on unseen musicians or recordings.

## Initial smoke checks — November 7, 2026

The first 10 seconds of BN1-129-Eb solo recordings from performers 00–05:

| Detector | Pitch/onset F1 | Pitch/onset/offset F1 | Matched onsets / reference |
| --- | ---: | ---: | ---: |
| Autocorrelation baseline | 59.6% | 33.6% | 87 / 153 |
| Basic Pitch 0.4.0, confidence >= 0.5 | 88.3% | 76.0% | 136 / 153 |

The corresponding six chord-accompaniment excerpts with Basic Pitch: pitch/onset
F1 78.7%, pitch/onset/offset F1 56.2% (283 matched onsets / 362 references).
All twelve ML outputs received a complete fingering and exported on all three
supported grids in a separate check. This does not establish comfortable playing.

## Broader development check — all 360 excerpts

The same fixed settings were then run on the first 10 seconds of every excerpt
(180 solo and 180 accompaniment). Neither detector was trained or tuned in this
project. These still are not verified held-out results.

| Excerpts | Baseline pitch/onset F1 | ML pitch/onset F1 | Baseline with offsets | ML with offsets |
| --- | ---: | ---: | ---: | ---: |
| 180 solo | 64.8% | 85.7% | 34.2% | 68.3% |
| 180 accompaniment | 13.4% | 69.9% | 3.2% | 44.7% |
| All 360 | 31.4% | 74.4% | 14.1% | 51.5% |

ML matched 13,319 of 20,261 reference onsets with 15,522 predictions. The complete
fingering search succeeded on 353/360 clips. Among matched onsets in those successful
clips, exact reference string/fret agreement was 59.1% (43.4% for solo, 67.0% for
accompaniment). That conditional figure excludes the seven unsuccessful fingerings
and should not be presented as overall tab accuracy. Alternate fingerings can play
the same pitch correctly; exact-string recognition remains a separate problem.

Detailed aggregate counts are in [reports/guitarset-development.json](reports/guitarset-development.json).
Inference plus initial model loading took about 69 seconds for ML and 114 seconds
for the baseline in this particular run. These timings exclude archive reading,
fingering search, export, and other script work, and are not standardized speed
benchmarks. No audio or note-level reference annotations are included in the report.

## Metric details

- GuitarSet v1.1.0 microphone audio, Zenodo record 3371780, CC BY 4.0.
- Score pitches after rounding annotated fractional MIDI to semitones.
- Maximum-cardinality one-to-one matching, equal semitone pitch and onset error
  <= 50 ms. Offset-aware matching additionally requires end error within
  max(50 ms, 20% of reference duration).
- Micro F1 pools true matches, predictions, and references, rather than averaging
  track percentages. Strings/frets are measured separately among matched onsets.
- Clips start at excerpt time zero. Notes at the right boundary are clipped.
  GuitarSet annotations already use excerpt-relative observation times.
- Basic Pitch uses the default model/note thresholds, followed by an explicit
  >= 0.5 event confidence filter. No model training or dataset-specific tuning.
- All inference and checks run on the user's laptop, without a transcription API
  or paid cloud compute.

## Reproduce

Download the checksum-verified archives using `scripts/download_guitarset.py`.
Then run these from the repository folder (use the separate ML Python for ML):

```powershell
uv run python scripts/evaluate_guitarset.py --backend baseline --limit 6 --seconds 10 --output runs/eval-baseline.json
.venv-ml/Scripts/python.exe scripts/evaluate_guitarset.py --backend basic-pitch --limit 6 --seconds 10 --export-tabs --output runs/eval-ml.json
```

For the chord check add `--mode comp`. For every excerpt use `--mode all --limit 360`.
Results and raw predicted events stay under ignored `runs/`; no audio is committed.

## Sources and attribution

- Q. Xi, R. M. Bittner, J. Pauwels, X. Ye, and J. P. Bello. GuitarSet: A Dataset
  for Guitar Transcription. ISMIR 2018.
  https://zenodo.org/records/3371780
- Spotify Basic Pitch: https://github.com/spotify/basic-pitch
- Training-data tooling: https://github.com/spotify/basic-pitch/tree/main/basic_pitch/data

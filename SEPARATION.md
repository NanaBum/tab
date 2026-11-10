# Local source-separation smoke test

The optional Demucs stage now runs locally and feeds its guitar stem into Basic
Pitch and GP5 export. It remains off by default.

## Controlled mixture

The first ten seconds of GuitarSet `03_BN1-129-Eb_solo` were mixed with generated
bass and drum sounds at a fixed 0.5-second pulse. The generator uses random seed 0.
This is deliberately simple and is **not a real full-band benchmark**.

The pitch detector was Basic Pitch 0.4.0 with confidence >= 0.5 in every condition.
The separator was Demucs 4.0.1 `htdemucs_6s`, CPU, shifts=0, segment=7 seconds.
Reference notes use the same one-to-one 50 ms onset matching as EVALUATION.md.

| Condition | Pitch/onset F1 | With offsets | SI-SDR against clean guitar |
| --- | ---: | ---: | ---: |
| Clean guitar | 92.6% | 81.5% | Reference |
| Generated mixture | 60.0% | 47.5% | -0.26 dB |
| Separated guitar stem | 90.9% | 80.0% | 18.27 dB |

The separated clip produced 26 note detections and successfully exported to GP5,
MIDI, JSON, and text. The original guitar had 29 annotated reference notes in the
window; a machine output with fewer notes is not a perfect transcription.
SI-SDR is a waveform comparison after scale alignment, not a listening-quality
rating. Its improvement here does not establish performance on real bands,
distorted guitar, vocals, or other recording conditions.

## Reproduce

### Electric guitar with controlled backing levels

Two labeled IDMT electric-guitar excerpts were mixed with the same generated
bass/drum pattern. Within each excerpt, the guitar level stayed fixed across
conditions. Backing levels were set by RMS and all conditions shared one gain
to avoid clipping. GAPS used its default onset threshold and 50 ms matching.

| Condition | Picked lick matches / detections (13 attacks) | Polyphonic piece matches / detections (19 attacks) |
| --- | ---: | ---: |
| Clean guitar | 12 / 13 | 15 / 18 |
| Backing only | 0 / 22 | 0 / 24 |
| Guitar 6 dB louder | 12 / 35 | 15 / 49 |
| Equal guitar and backing RMS | 11 / 36 | 15 / 56 |
| Guitar 6 dB quieter | 9 / 38 | 14 / 59 |
| Separated, equal RMS mix | 1 / 3 | 14 / 18 |
| Separated, quieter guitar mix | 2 / 3 | 14 / 25 |

The guitar-free control shows that GAPS can report attacks from accompaniment.
Separation reduced unmatched attacks on the polyphonic excerpt. On the picked
lick, it also removed most matches. Waveform similarity at equal RMS moved
from −0.03 to −7.34 dB for the lick and from −0.15 to 12.80 dB for the
polyphonic excerpt. This comparison uses two recordings and generated backing.

With the guitar model, separation environment, and IDMT examples installed,
run the following for the event files and a report with input hashes.

```powershell
.venv-guitar/Scripts/python.exe scripts/evaluate_guitar_mix_levels.py --output runs/gaps-controlled-mixture-levels
```

Basic Pitch was also run on all 14 byte-verified inputs from that experiment.
The models agreed on all 46 detections in the two guitar-free controls.
Agreement alone did not distinguish guitar from the generated accompaniment.
On the equal-RMS picked-lick stem, Basic Pitch matched 3 attacks from 8
detections and GAPS matched 1 from 3. On the polyphonic stem both matched 14
from 18. Combining the detections on the equal-RMS mixes added unmatched
events without recovering any more score attacks than GAPS alone.

```powershell
.venv-ml/Scripts/python.exe scripts/compare_controlled_mix_detectors.py runs/gaps-controlled-mixture-levels --output runs/controlled-mix-detector-comparison
```

### Original Basic Pitch smoke test

After the separate ML and separation environments and GuitarSet archives exist:

```powershell
.venv-ml/Scripts/python.exe scripts/evaluate_separation_demo.py
```

This extracts the fixed excerpt, creates the controlled mixture, runs separation
and note detection, and saves the comparison under ignored `runs/`. The mixture
generator can also accept a user-supplied guitar WAV:

```powershell
uv run python scripts/make_mixture_demo.py guitar.wav
```

Weights and all audio stay outside Git. A mono-input regression check verifies the
temporary input is physically stereo and that the original audio is unchanged.
Silent audio is rejected before invoking the model.

## Attribution

GuitarSet v1.1.0: Qingyang Xi, Rachel M. Bittner, Johan Pauwels, Xuzhou Ye, and
Juan P. Bello, *GuitarSet: A Dataset for Guitar Transcription*, ISMIR 2018.
https://zenodo.org/records/3371780 — CC BY 4.0.

Changes: excerpted to ten seconds, normalized with a common mixture gain, mixed
with generated accompaniment, then processed by Demucs and Basic Pitch. Results
are not the reference tabs and are not endorsed by the dataset authors.

Demucs source and license: https://github.com/facebookresearch/demucs

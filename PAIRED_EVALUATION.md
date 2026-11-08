# Reproducible local audio/tab-pair evaluation

Use a manifest to compare a declared collection of existing predictions with
timed references. It identifies the exact audio, reference and prediction bytes,
their sources, and supplied permission/review notes. It does not download songs,
run a model, train anything or establish a license. The audio file is hashed for
identity; this runner scores note events rather than analyzing the audio again.

```powershell
uv run python scripts/evaluate_pairs.py runs/my-pairs/manifest.json --max-shift 5 --output runs/my-pairs/report.json
```

Paths in the manifest are relative to the manifest's directory; absolute local
paths also work. Keep manifests containing private paths or recordings under
ignored `runs/` or `data/`. Import a local Guitar Pro reference to timed JSON
first with [REFERENCE_IMPORT.md](REFERENCE_IMPORT.md). Timed note JSON, exported
`notes.json` and IDMT XML are accepted by the same reader used for single-file
comparisons. A bare untimed fret list is not a timed reference.

## Manifest format

```json
{
  "format": "tabber-evaluation-pairs",
  "schema_version": 1,
  "metadata": {"scope": "Local development collection; not held-out accuracy"},
  "pairs": [{
    "pair_id": "song-a/take-1/model-v1",
    "song_id": "song-a",
    "split": "development",
    "model_id": "model-v1-fixed-settings",
    "model_provenance": "Exact checkpoint identity, version and threshold settings",
    "reference_quality": "candidate",
    "alignment_review": "candidate",
    "audio": {
      "path": "guitar.wav",
      "sha256": "REPLACE_WITH_64_LOWERCASE_HEX_DIGITS",
      "source": "Recording version and source identity",
      "permission_note": "Record applicable permission and its evidence; pending if unresolved"
    },
    "reference": {
      "path": "reference-events.json",
      "sha256": "REPLACE_WITH_64_LOWERCASE_HEX_DIGITS",
      "source": "Tab revision, chosen track and imported-reference identity",
      "permission_note": "Record applicable reference permission and its evidence"
    },
    "prediction": {
      "path": "detected-notes.json",
      "sha256": "REPLACE_WITH_64_LOWERCASE_HEX_DIGITS",
      "source": "Unedited local model output",
      "permission_note": "Record the applicable data/model-use scope"
    }
  }]
}
```

Compute each hash from its exact file bytes, for example with PowerShell
`(Get-FileHash path/to/file -Algorithm SHA256).Hash.ToLower()`.
Review fields accept `candidate` or `reviewed`; they are declarations, not
automatic verification of correctness. Additional pair fields can record label
audits, recording conditions and review notes; the report retains the full entry.
Likewise permission notes preserve evidence without granting permission or
turning an unresolved source into authorized training data.

## Splits and results

Splits are `train`, `validation`, `test` or `development`. Assign all takes,
arrangements, covers and excerpts of one underlying song the same `song_id`.
The runner refuses a song ID across splits, ignoring capitalization and outer
spaces. It also catches byte-identical audio or references across splits under
different names. It cannot recognize unidentified covers, re-encoded audio or
musically equivalent tabs; those still need provenance review. It cannot detect
whether a pretrained checkpoint already saw a song. Naming a split `test` alone
does not establish an independent benchmark.

All declared pairs must pass file/hash and schema checks. An invalid pair fails
the run rather than silently reducing the evaluation set. One model ID must have
one provenance/settings description. Aggregates stay separate by model ID and
split, summing matched/reference/predicted counts before computing micro F1.
They do not average track F1 or combine competing models into one score.

Each pair includes original timing scores and a reference-assisted fitted global
shift, with ambiguity/boundary flags. Pitch/onset and release-aware metrics remain
separate; no notes are removed. See [GLOBAL_ALIGNMENT.md](GLOBAL_ALIGNMENT.md).
Candidate labels and unreviewed alignment remain visible even when scores look
good. The tool does not measure fingering or perceived musical quality.

## Evidence

The runner reproduced every raw and shifted matched-note count and F1 from our
existing fixed eight-electric-recording comparison, for both models (16 pairs).
It reused the exact saved audio, annotations and predictions without new model
inference. [paired-manifest-check.json](reports/paired-manifest-check.json) records
the aggregate comparison. These remain development results with candidate
references and unresolved checkpoint-training overlap. Private/local manifests
and full reports remain outside Git.

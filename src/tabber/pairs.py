"""Reproducible local paired evaluation; no collection, inference or training."""

import hashlib
import json
import re
from pathlib import Path

from .alignment import compare_with_global_shift
from .note_files import read_notes, read_reference_metadata


def file_hash(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _text(row, key):
    value = row.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Missing nonempty text field: {key}")
    return value.strip()


def inspect_manifest(path):
    """Check every asset and split before evaluating any pair; fail rather than skip."""
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict) or payload.get("format") != "tabber-evaluation-pairs":
        raise ValueError("Expected a tabber-evaluation-pairs manifest")
    if payload.get("schema_version") != 1:
        raise ValueError("Expected manifest schema version 1")
    rows = payload.get("pairs")
    if not isinstance(rows, list) or not 1 <= len(rows) <= 10000:
        raise ValueError("Manifest must contain 1 to 10,000 pairs")
    seen_ids, groups, assets, checked, models = set(), {}, {}, [], {}
    for row in rows:
        if not isinstance(row, dict):
            raise TypeError("Each pair must be an object")
        identity = _text(row, "pair_id")
        if identity in seen_ids:
            raise ValueError(f"Duplicate pair_id: {identity}")
        seen_ids.add(identity)
        song = _text(row, "song_id").casefold()
        split = _text(row, "split")
        if split not in {"train", "validation", "test", "development"}:
            raise ValueError(f"Invalid split for {identity}")
        if song in groups and groups[song] != split:
            raise ValueError(f"Song appears in different splits: {song}")
        groups[song] = split
        model = _text(row, "model_id")
        provenance = _text(row, "model_provenance")
        if model in models and models[model] != provenance:
            raise ValueError("One model_id must identify the same model and settings")
        models[model] = provenance
        for field in ("reference_quality", "alignment_review"):
            if row.get(field) not in {"candidate", "reviewed"}:
                raise ValueError(f"{identity}: {field} must be candidate or reviewed")
        paths = {}
        for kind in ("audio", "reference", "prediction"):
            asset = row.get(kind)
            if not isinstance(asset, dict):
                raise TypeError(f"{identity}: missing {kind} asset")
            asset_path = (path.parent / _text(asset, "path")).resolve()
            digest = _text(asset, "sha256")
            if not re.fullmatch(r"[0-9a-f]{64}", digest):
                raise ValueError(f"{identity}: invalid {kind} SHA256")
            _text(asset, "source")
            _text(asset, "permission_note")
            if not asset_path.is_file() or file_hash(asset_path) != digest:
                raise ValueError(f"{identity}: missing or changed {kind} asset")
            # Byte-identical source audio/labels must not cross splits, even if
            # filenames or manually supplied song IDs differ. Predictions are
            # excluded: an empty model output can recur on unrelated recordings.
            if kind != "prediction":
                key = (kind, digest)
                if key in assets and assets[key] != split:
                    raise ValueError(f"Identical {kind} appears in different splits")
                assets[key] = split
            paths[kind] = asset_path
        checked.append((row, paths))
    return payload, checked


def evaluate_manifest(path: Path, *, max_shift=5.0, step=0.01, onset_tolerance=0.05):
    payload, checked = inspect_manifest(path)
    pairs, aggregate = [], {}
    for row, paths in checked:
        result = compare_with_global_shift(
            read_notes(paths["reference"]),
            read_notes(paths["prediction"]),
            max_shift=max_shift,
            step=step,
            onset_tolerance=onset_tolerance,
        )
        pairs.append(
            {
                "manifest_entry": row,
                "reference_metadata": read_reference_metadata(paths["reference"]),
                "comparison": result,
            }
        )
        key = (row["split"], row["model_id"])
        totals = aggregate.setdefault(key, {"pairs": 0, "raw": {}, "shifted": {}})
        totals["pairs"] += 1
        for timing in ("raw", "shifted"):
            for metric in ("onsets", "onsets_offsets"):
                counts = totals[timing].setdefault(
                    metric,
                    {
                        "reference_notes": 0,
                        "predicted_notes": 0,
                        "matched_notes": 0,
                    },
                )
                for name in counts:
                    counts[name] += result[timing][metric][name]
    for totals in aggregate.values():
        for timing in ("raw", "shifted"):
            for counts in totals[timing].values():
                r, p, m = (
                    counts[k] for k in ("reference_notes", "predicted_notes", "matched_notes")
                )
                counts.update(
                    precision=m / p if p else 0,
                    recall=m / r if r else 0,
                    f1=2 * m / (p + r) if p + r else 0,
                )
    return {
        "format": "tabber-paired-evaluation",
        "schema_version": 1,
        "manifest_sha256": file_hash(path),
        "pairs": pairs,
        "aggregates": [
            {"split": split, "model_id": model, **totals}
            for (split, model), totals in sorted(aggregate.items())
        ],
        "limits": "All declared pairs included. Raw scores retained; shifted scores fit one offset using each reference. Song grouping and byte hashes detect declared/identical-file leakage, not unidentified covers, excerpts, alternate encodings or pretrained overlap. Permission and review notes are supplied declarations, not verified licenses or ground truth. No collection, inference or training performed.",
        "manifest_metadata": payload.get("metadata", {}),
    }

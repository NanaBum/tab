"""Measure a detector on a fixed local excerpt partition."""

import argparse
import json
from dataclasses import asdict
from pathlib import Path

import soundfile as sf

from tabber.evaluation import score_notes
from tabber.events import load_events, save_events
from tabber.media import sha256_file
from tabber.separate import separate_guitar
from tabber.transcribe import transcribe


def verified_asset(root, relative, digest):
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()) or sha256_file(path) != digest:
        raise ValueError(f"Excerpt asset failed verification: {relative}")
    return path


def load_partition(manifest_path, split):
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    if manifest.get("format") != "tabber-onset-excerpts" or manifest.get("schema_version") != 1:
        raise ValueError("Use a version 1 onset-excerpt manifest")
    identity_splits = {}
    partition = []
    for row in manifest["excerpts"]:
        for key in ("song_id", "original_recording_sha256", "decoded_audio_sha256"):
            if identity_splits.setdefault(row[key], row["split"]) != row["split"]:
                raise ValueError("A song or recording appears in multiple splits")
        if row["split"] != split:
            continue
        root = manifest_path.parent
        audio = verified_asset(root, row["audio"], row["audio_sha256"])
        notes = verified_asset(root, row["labels"], row["labels_sha256"])
        reference = load_events(notes)
        info = sf.info(audio)
        if (
            info.frames != row["frames"]
            or info.samplerate != row["sample_rate"]
            or info.channels != row["channels"]
            or len(reference) != row["note_count"]
            or any(note.end > info.duration for note in reference)
        ):
            raise ValueError("Excerpt metadata disagrees with saved audio or labels")
        partition.append((row, audio, reference))
    if not partition:
        raise ValueError(f"No excerpts in split {split}")
    return partition


def reuse_inputs(root, manifest_hash, split, excerpts):
    report = json.loads((root / "report.json").read_text(encoding="utf-8"))
    if (
        report["manifest_sha256"] != manifest_hash
        or report["split"] != split
        or not report["separate_guitar"]
        or len(report["excerpts"]) != len(excerpts)
    ):
        raise ValueError("Stem report does not describe this partition")
    stems = []
    for index, (old, (row, _, _)) in enumerate(zip(report["excerpts"], excerpts, strict=True), 1):
        if any(old[key] != row[key] for key in ("song_id", "audio_sha256", "labels_sha256")):
            raise ValueError("Saved stem identity does not match the current excerpt")
        relative = f"excerpt-{index:03d}/stems/htdemucs_6s/audio/guitar.wav"
        stems.append(verified_asset(root, relative, old["detector_input_sha256"]))
    return stems


def evaluate(manifest_path, output, split, backend, separate, reuse_stems=None):
    excerpts = load_partition(manifest_path, split)
    manifest_hash = sha256_file(manifest_path)
    stems = reuse_inputs(reuse_stems, manifest_hash, split, excerpts) if reuse_stems else None
    output.mkdir(parents=True, exist_ok=False)
    report = {
        "purpose": "Pitch and attack comparison against weak score candidates",
        "manifest_sha256": manifest_hash,
        "split": split,
        "backend": backend,
        "separate_guitar": separate or stems is not None,
        "onset_tolerance_seconds": 0.075,
        "excerpts": [],
        "limits": "Labels come from aligned score playback. An unmatched detection is not necessarily an audible false note. Duration is not scored.",
    }
    if reuse_stems:
        report["reused_stem_report_sha256"] = sha256_file(reuse_stems / "report.json")
    for index, (row, audio, reference) in enumerate(excerpts, 1):
        run = output / f"excerpt-{index:03d}"
        run.mkdir()
        path = separate_guitar(audio, run / "stems") if separate else audio
        if stems is not None:
            path = stems[index - 1]
        if abs(sf.info(path).duration - row["frames"] / row["sample_rate"]) > 0.001:
            raise ValueError("Detector input duration differs from the source excerpt")
        predicted = transcribe(path, backend)
        prediction_path = run / "detected-notes.json"
        source = {
            "song_id": row["song_id"],
            "audio_sha256": row["audio_sha256"],
            "labels_sha256": row["labels_sha256"],
            "detector_input_sha256": sha256_file(path),
        }
        save_events(
            predicted,
            prediction_path,
            {**source, "backend": backend, "separated": report["separate_guitar"]},
        )
        scores = score_notes(reference, predicted, onset_tolerance=0.075)
        report["excerpts"].append(
            {
                **source,
                "prediction_sha256": sha256_file(prediction_path),
                "scores": asdict(scores),
                "missed": scores.reference_notes - scores.matched_notes,
                "unmatched_detections": scores.predicted_notes - scores.matched_notes,
            }
        )
        print(
            f"{row['song_id']}: {scores.matched_notes}/{scores.reference_notes} matches", flush=True
        )
    report["totals"] = {
        key: sum(row["scores"][key] for row in report["excerpts"])
        for key in ("reference_notes", "predicted_notes", "matched_notes")
    }
    with (output / "report.json").open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--split", choices=("validation", "test"), default="test")
    parser.add_argument(
        "--backend", choices=("baseline", "basic-pitch", "guitar-gaps"), required=True
    )
    stem_options = parser.add_mutually_exclusive_group()
    stem_options.add_argument("--separate", action="store_true")
    stem_options.add_argument(
        "--reuse-stems", type=Path, help="Use verified stems from a prior run"
    )
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        evaluate(
            args.manifest, args.output, args.split, args.backend, args.separate, args.reuse_stems
        )
    except (OSError, KeyError, ValueError, RuntimeError) as error:
        parser.exit(1, f"Could not evaluate excerpts: {error}\n")


if __name__ == "__main__":
    main()

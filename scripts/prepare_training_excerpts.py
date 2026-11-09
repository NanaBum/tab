"""Package source-checked audio excerpts and weak score-onset labels."""

import argparse
import json
import math
import re
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.io import wavfile

from tabber.alignment import excerpt_target
from tabber.events import load_events, save_events
from tabber.media import sha256_file


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def verify_row(row, root):
    pair_path = root / row["pair"]
    pair = read_json(pair_path)
    if (
        pair.get("format") != "tabber-training-pair"
        or pair.get("schema_version") != 1
        or pair.get("song_id") != row["song_id"]
        or pair.get("test_fixture")
        or pair.get("excluded_from_training")
    ):
        raise ValueError("Expected a matching, non-fixture source pair")
    pair_hash = sha256_file(pair_path)
    original = pair["roles"]["audio_original"]
    matches = [asset for asset in pair["assets"] if asset["path"] == original]
    original_path = pair_path.parent / original
    if len(matches) != 1 or matches[0]["bytes"] != original_path.stat().st_size:
        raise ValueError("Original recording does not match its pair manifest")
    original_hash = sha256_file(original_path)
    if original_hash != matches[0]["sha256"]:
        raise ValueError("Original recording hash does not match its pair manifest")

    audio = root / row["audio"]
    audio_hash = sha256_file(audio)
    evidence_path = root / row["evidence"]
    evidence = read_json(evidence_path)
    if evidence["audio_sha256"] != audio_hash or evidence["source_pair_sha256"] != pair_hash:
        raise ValueError("Alignment evidence does not identify this audio and source pair")
    shift, scale = row["score_shift_seconds"], row["score_scale"]
    if not math.isfinite(shift) or not math.isfinite(scale) or scale <= 0:
        raise ValueError("Use a finite shift and positive finite scale")
    if scale != evidence.get("score_scale", 1):
        raise ValueError("Planned score scale differs from the alignment evidence")
    if shift == evidence["calibrated_shift_seconds"]:
        score_key = "calibrated_flux"
    elif shift == evidence["coarse_score_shift_seconds"]:
        score_key = "coarse_flux"
    else:
        raise ValueError("Planned shift must match a checked score clock")
    passed = {
        tuple(window["window_seconds"])
        for window in evidence["windows"]
        if window[score_key] > window["control_max_flux"]
    }

    tracks, track_hashes = [], []
    numbers = row["tracks"]
    if (
        not numbers
        or any(type(n) is not int or n <= 0 for n in numbers)
        or len(set(numbers)) != len(numbers)
    ):
        raise ValueError("Choose distinct one-based score track numbers")
    for number in numbers:
        reference = pair_path.parent.parent / f"labels/gp7-track-{number}.json"
        metadata = read_json(reference)["metadata"]
        if (
            metadata["source_pair_sha256"] != pair_hash
            or metadata["score_track"]["track"] != number
        ):
            raise ValueError("Score labels do not identify the selected pair and track")
        track_hashes.append(sha256_file(reference))
        tracks.append(load_events(reference))
    if sorted(track_hashes) != sorted(reference["sha256"] for reference in evidence["references"]):
        raise ValueError("Selected labels differ from the alignment evidence")

    if not row["windows"] or any(tuple(window) not in passed for window in row["windows"]):
        raise ValueError("Every selected window must beat its displaced controls")
    provenance = {
        "source_pair_sha256": pair_hash,
        "original_recording_sha256": original_hash,
        "decoded_audio_sha256": audio_hash,
        "alignment_evidence_sha256": sha256_file(evidence_path),
        "score_track_numbers": numbers,
        "score_track_sha256": track_hashes,
        "score_shift_seconds": shift,
        "score_scale": scale,
    }
    return audio, tracks, provenance


def write_excerpts(row, root, output, split_by_identity, windows_by_audio):
    song_id, split = row["song_id"], row["split"]
    if not isinstance(song_id, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,79}", song_id):
        raise ValueError("Use a lowercase song-group identifier")
    if split not in {"train", "validation", "test"}:
        raise ValueError("Split must be train, validation or test")
    audio, tracks, provenance = verify_row(row, root)
    for identity in (
        song_id,
        provenance["original_recording_sha256"],
        provenance["decoded_audio_sha256"],
    ):
        if split_by_identity.setdefault(identity, split) != split:
            raise ValueError("A song or recording appears in multiple splits")

    rows = []
    split_folder = output / split
    existing = sum(path.is_dir() for path in split_folder.glob(f"{song_id}-[0-9]*"))
    with sf.SoundFile(audio) as recording:
        seen = windows_by_audio.setdefault(provenance["decoded_audio_sha256"], [])
        for lo, hi in row["windows"]:
            first, last = round(lo * recording.samplerate), round(hi * recording.samplerate)
            if not 0 <= first < last <= recording.frames:
                raise ValueError("Excerpt is outside the source recording")
            if any(first < end and start < last for start, end in seen):
                raise ValueError("Source excerpt windows overlap")
            seen.append((first, last))
            start = first / recording.samplerate
            duration = (last - first) / recording.samplerate
            recording.seek(first)
            samples = recording.read(last - first, dtype="float32", always_2d=True)
            if len(samples) != last - first or not np.isfinite(samples).all():
                raise ValueError("Excerpt audio is incomplete or nonfinite")
            notes = excerpt_target(
                tracks,
                score_shift=row["score_shift_seconds"],
                score_scale=row["score_scale"],
                recording_start=start,
                duration=duration,
            )
            if not notes:
                raise ValueError("No score attacks in selected excerpt")
            folder = split_folder / f"{song_id}-{existing + len(rows) + 1:03d}"
            folder.mkdir(parents=True)
            waveform = folder / "audio.wav"
            labels = folder / "onsets.json"
            wavfile.write(waveform, recording.samplerate, samples)
            record = {
                "song_id": song_id,
                "split": split,
                "source_start_frame": first,
                "frames": len(samples),
                "sample_rate": recording.samplerate,
                "channels": recording.channels,
                "note_count": len(notes),
                "label_status": "weak_score_candidates",
                "target": "pitch and onset",
                **provenance,
            }
            save_events(notes, labels, record)
            rows.append(
                {
                    **record,
                    "audio": waveform.relative_to(output).as_posix(),
                    "audio_sha256": sha256_file(waveform),
                    "labels": labels.relative_to(output).as_posix(),
                    "labels_sha256": sha256_file(labels),
                }
            )
    return rows


def prepare(plan_path, output, root):
    plan = read_json(plan_path)
    if (
        plan.get("format") != "tabber-excerpt-plan"
        or plan.get("schema_version") != 1
        or plan.get("label_status") != "weak_score_candidates"
    ):
        raise ValueError("Use a version 1 weak-score excerpt plan")
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise FileExistsError("Choose a fresh output folder")
    if not {"train", "validation"} <= {row["split"] for row in plan["rows"]}:
        raise ValueError("The plan needs training and validation songs")

    split_by_identity, windows_by_audio, rows = {}, {}, []
    with tempfile.TemporaryDirectory(prefix=".excerpt-stage-", dir=output.parent) as staging:
        stage = Path(staging) / "dataset"
        stage.mkdir()
        for row in plan["rows"]:
            rows.extend(write_excerpts(row, root, stage, split_by_identity, windows_by_audio))
        manifest = {
            "format": "tabber-onset-excerpts",
            "schema_version": 1,
            "plan_sha256": sha256_file(plan_path),
            "label_status": "weak_score_candidates",
            "limits": "Selected score attacks with audio evidence. Score releases remain in the event files for inspection. The target is pitch and onset.",
            "excerpts": rows,
        }
        (stage / "manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        if output.exists():
            raise FileExistsError("Choose a fresh output folder")
        stage.rename(output)
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        rows = prepare(args.plan, args.output, args.root)
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as error:
        parser.exit(1, f"Could not prepare excerpts: {error}\n")
    print(f"Packaged {len(rows)} excerpts: {args.output.resolve()}")


if __name__ == "__main__":
    main()

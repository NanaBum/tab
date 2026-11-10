"""Prepare separate development or held-out Guitar-TECHS feature caches."""

import argparse
import io
import json
import math
import zipfile
from collections import Counter
from pathlib import Path

import mido
import numpy as np
import soundfile as sf
from download_guitar_techs import FILES, verify
from probe_attack_alignment import assess_windows, pitch_flux

from tabber.guitar_techs import string_notes
from tabber.media import sha256_file
from tabber.models import Note
from tabber.string_model import FEATURE_VERSION, audio_features, isolated_features

CHANNELS = ("directinput", "micamp")


def midi_notes(archive, name, take):
    raw = archive.read(f"{name}/midi/midi_{take}.mid")
    return string_notes(mido.MidiFile(file=io.BytesIO(raw)))


def confirmed_offset(evidence):
    shift = evidence["calibrated_shift_seconds"]
    if not math.isfinite(shift) or abs(shift) > 0.1 or not evidence["windows"]:
        raise ValueError("Audio offset is unsupported")
    if any(
        row["calibrated_flux"] <= row["control_max_flux"]
        or row["local_best_on_search_edge"]
        or abs(shift - row["local_best_shift_seconds"]) > 0.035
        for row in evidence["windows"]
    ):
        raise ValueError("Later audio windows do not support the first-window offset")
    return shift


def feature_rows(stream, notes, offset, metadata):
    samples, rate = sf.read(stream, always_2d=True)
    duration = len(samples) / rate
    waveform, mfcc = audio_features(samples, rate)
    moved = [
        (Note(max(0, row["start"] + offset), min(duration, row["end"] + offset), row["pitch"]), row)
        for row in notes
        if max(0, row["start"] + offset) < min(duration, row["end"] + offset)
    ]
    features = isolated_features(waveform, mfcc, [note for note, _ in moved])
    return [
        {
            **metadata,
            "features": feature,
            "pitch": note.pitch,
            "string": row["string"],
            "start": note.start,
            "midi_start": row["start"],
        }
        for ((note, row), feature) in zip(moved, features, strict=True)
        if feature is not None
        and row["start"] + offset >= 0
        and row["playable_standard"]
        and not row["track_expression"]
    ]


def read_recording(archive, name, take, channel, notes, evidence):
    member = f"{name}/audio/{channel}/{channel}_{take}.wav"
    with io.BytesIO(archive.read(member)) as stream:
        if evidence is None:
            flux, duration = pitch_flux(stream)
            attacks = [(n["start"], n["pitch"]) for n in notes if n["playable_standard"]]
            evidence = assess_windows(
                flux,
                attacks,
                ((1, duration / 2), (duration / 2, duration - 1)),
                coarse=0.0,
                duration=duration,
            )
            stream.seek(0)
        elif evidence["member"] != member:
            raise ValueError("Timing audit identifies a different audio member")
        shift = confirmed_offset(evidence)
        player = name.split("_", 1)[0]
        rows = feature_rows(
            stream, notes, shift, {"player": player, "take": take, "channel": channel}
        )
    return rows, {
        "player": player,
        "take": take,
        "channel": channel,
        "shift": shift,
        "timing_windows": evidence["windows"],
        "features": len(rows),
    }


def prepare(data, split, audit_path, destination):
    audit = json.loads(audit_path.read_text(encoding="utf-8")) if audit_path else None
    players = {row["player"]: row for row in audit["players"]} if audit else {}
    archives = ("P1_singlenotes", "P2_singlenotes") if split == "development" else ("P3_music",)
    rows, recordings, hashes = [], [], {}
    for name in archives:
        path = data / f"{name}.zip"
        verify(path, *FILES[path.name])
        hashes[name] = sha256_file(path)
        player = name.split("_", 1)[0]
        with zipfile.ZipFile(path) as archive:
            takes = (
                ("allsinglenotes",)
                if split == "development"
                else tuple(f"{i:02}" for i in range(1, 13))
            )
            for take in takes:
                notes = midi_notes(archive, name, take)
                if split == "development" and (
                    players[player]["archive_sha256"] != hashes[name]
                    or players[player]["notes"] != notes
                ):
                    raise ValueError("Development notes disagree with the verified timing audit")
                for channel in CHANNELS:
                    evidence = players[player]["audio"][channel] if split == "development" else None
                    try:
                        features, record = read_recording(
                            archive, name, take, channel, notes, evidence
                        )
                    except ValueError as error:
                        if split == "development":
                            raise
                        features, record = (
                            [],
                            {
                                "player": player,
                                "take": take,
                                "channel": channel,
                                "rejected": str(error),
                            },
                        )
                    rows.extend(features)
                    recordings.append(record)
                    status = record.get("rejected", f"{len(features)} feature windows")
                    print(f"{player} {take} {channel}: {status}", flush=True)
    if not rows:
        raise ValueError("No supported feature windows")
    destination.mkdir(parents=True, exist_ok=False)
    cache = destination / "features.npz"
    np.savez_compressed(
        cache,
        feature_version=FEATURE_VERSION,
        split=split,
        **{key: np.asarray([row[key] for row in rows]) for key in rows[0]},
    )
    report = {
        "split": split,
        "archives_sha256": hashes,
        "clock_audit_sha256": sha256_file(audit_path) if audit_path else None,
        "features_sha256": sha256_file(cache),
        "features_by_player": Counter(row["player"] for row in rows),
        "recordings": recordings,
        "limits": "Oracle pitch and offset-corrected MIDI gates. Unisolated and expression-flagged windows are excluded. No fit.",
    }
    with (destination / "report.json").open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--split", choices=("development", "test"), required=True)
    parser.add_argument("--clock-audit", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if bool(args.clock_audit) != (args.split == "development"):
        parser.error("Provide --clock-audit only for the development split")
    try:
        prepare(args.data, args.split, args.clock_audit, args.output)
    except (OSError, ValueError, KeyError, RuntimeError, zipfile.BadZipFile) as error:
        parser.exit(1, f"Could not prepare Guitar-TECHS features: {error}\n")


if __name__ == "__main__":
    main()

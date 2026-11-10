"""Decode Guitar-TECHS string tracks and audit their audio clocks without training."""

import argparse
import io
import json
import zipfile
from pathlib import Path

import mido
from download_guitar_techs import FILES, verify
from probe_attack_alignment import assess_windows, pitch_flux

from tabber.guitar_techs import string_notes
from tabber.media import sha256_file


def audit_single_notes(folder, player):
    name = f"{player}_singlenotes"
    archive_path = folder / f"{name}.zip"
    verify(archive_path, *FILES[archive_path.name])
    with zipfile.ZipFile(archive_path) as archive:
        midi = mido.MidiFile(file=io.BytesIO(archive.read(f"{name}/midi/midi_allsinglenotes.mid")))
        notes = string_notes(midi)
        if not notes:
            raise ValueError("Expected attacks in the single-note archive")
        attacks = [(n["start"], n["pitch"]) for n in notes if n["playable_standard"]]
        audio = {}
        for channel in ("directinput", "micamp"):
            member = f"{name}/audio/{channel}/{channel}_allsinglenotes.wav"
            with io.BytesIO(archive.read(member)) as stream:
                flux, duration = pitch_flux(stream)
            windows = (
                (1, duration / 3),
                (duration / 3, duration * 2 / 3),
                (duration * 2 / 3, duration - 1),
            )
            audio[channel] = {
                "member": member,
                "duration_seconds": duration,
                **assess_windows(flux, attacks, windows, coarse=0.0, duration=duration),
            }
    return {
        "player": player,
        "archive_sha256": sha256_file(archive_path),
        "notes": notes,
        "audio": audio,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        rows = []
        for player in ("P1", "P2"):
            row = audit_single_notes(args.data, player)
            rows.append(row)
            print(f"{player}: decoded {len(row['notes'])} attacks from named strings", flush=True)
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump(
                {
                    "purpose": "Development audio clock check before string-feature extraction",
                    "players": rows,
                    "limits": "Global offset and displaced controls only. MIDI pitches are base notes and expression is flagged by track. P3 is held out. No model weights fitted.",
                },
                stream,
                indent=2,
            )
            stream.write("\n")
    except (OSError, ValueError, KeyError, RuntimeError, zipfile.BadZipFile) as error:
        parser.exit(1, f"Could not audit Guitar-TECHS: {error}\n")


if __name__ == "__main__":
    main()

"""Inspect a local GP3/GP4/GP5 file and import candidate timed note events."""

import argparse
import hashlib
import json
from pathlib import Path

import guitarpro

from tabber.events import save_events
from tabber.gp5 import read_gp5
from tabber.reference import describe_tracks, extract_reference


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tab", type=Path)
    parser.add_argument(
        "--track", type=int, help="One-based track number; required for multi-track scores"
    )
    parser.add_argument("--list-tracks", action="store_true")
    parser.add_argument("--allow-approximate-techniques", action="store_true")
    parser.add_argument("--output", type=Path, default=Path("runs/reference-events.json"))
    args = parser.parse_args()
    try:
        if args.tab.suffix.lower() not in (".gp3", ".gp4", ".gp5"):
            raise ValueError("Use a local GP3, GP4 or GP5 file")
        if args.output.resolve() == args.tab.resolve():
            raise ValueError("Output must not overwrite the source tab")
        song = read_gp5(args.tab)
        if args.list_tracks:
            print(json.dumps(describe_tracks(song), indent=2))
            return
        result = extract_reference(
            song,
            track_number=args.track,
            allow_approximate_techniques=args.allow_approximate_techniques,
        )
        with args.tab.open("rb") as stream:
            result.metadata["source_sha256"] = hashlib.file_digest(stream, "sha256").hexdigest()
        result.metadata["source_file"] = str(args.tab.resolve())
        save_events(result.notes, args.output, result.metadata)
    except (ValueError, OSError, EOFError, guitarpro.GPException) as error:
        parser.exit(1, f"Could not import reference: {error}\n")
    print(f"Imported {len(result.notes)} candidate events from track {args.track or 1}.")
    print(
        "Reference note: Score timing is not verified performance timing; data-use permission is not assessed."
    )
    if result.metadata["approximate_techniques"]:
        print(
            "Reference note: Only base-note symbols imported; technique timing/pitches require review."
        )
    print(f"Saved: {args.output.resolve()}")


if __name__ == "__main__":
    main()

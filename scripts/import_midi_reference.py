"""List/select local MIDI tracks/channels and save candidate timed reference events."""

import argparse
import json
from pathlib import Path

import mido

from tabber.events import save_events
from tabber.media import sha256_file
from tabber.midi_reference import describe_midi, extract_midi_reference


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("midi", type=Path)
    parser.add_argument("--list-tracks", action="store_true")
    parser.add_argument("--track", type=int, help="One-based physical MIDI track")
    parser.add_argument("--channels", help="Comma-separated one-based MIDI channels (1–16)")
    parser.add_argument("--allow-approximate-expression", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--pair-manifest",
        type=Path,
        help="Carry source-pair provenance/warnings after verifying its score MIDI hash",
    )
    args = parser.parse_args()
    try:
        midi = mido.MidiFile(args.midi)
        if args.list_tracks:
            print(json.dumps(describe_midi(midi), indent=2))
            return
        if args.output is None or args.output.resolve() in {
            args.midi.resolve(),
            args.pair_manifest.resolve() if args.pair_manifest else args.midi.resolve(),
        }:
            raise ValueError("Choose --output separate from the input MIDI and pair manifest")
        channels = (
            tuple(int(value.strip()) for value in args.channels.split(","))
            if args.channels
            else None
        )
        result = extract_midi_reference(
            midi,
            track_number=args.track,
            channels=channels,
            allow_approximate_expression=args.allow_approximate_expression,
        )
        result.metadata["source_file_sha256"] = sha256_file(args.midi)
        result.metadata["source_file"] = str(args.midi.resolve())
        if args.pair_manifest:
            pair = json.loads(args.pair_manifest.read_text(encoding="utf-8-sig"))
            if (
                not isinstance(pair, dict)
                or pair.get("format") != "tabber-training-pair"
                or pair.get("schema_version") != 1
            ):
                raise ValueError("Use a version 1 tabber-training-pair manifest")
            sources = pair.get("sources", {})
            if not isinstance(sources, dict):
                raise ValueError("Pair sources must be an object")
            matches = [
                asset for asset in pair["assets"] if asset["path"] == pair["roles"]["score_midi"]
            ]
            if (
                len(matches) != 1
                or matches[0]["sha256"] != result.metadata["source_file_sha256"]
                or matches[0]["bytes"] != args.midi.stat().st_size
            ):
                raise ValueError(
                    "The selected MIDI does not match the pair's declared source-score MIDI"
                )
            result.metadata["source_pair_sha256"] = sha256_file(args.pair_manifest)
            result.metadata["source_pair"] = {
                key: pair[key]
                for key in (
                    "song_id",
                    "split",
                    "label_status",
                    "recording_version_review",
                    "alignment",
                    "permission_notes",
                    "tab_warnings",
                    "test_fixture",
                    "excluded_from_training",
                )
                if key in pair
            }
            result.metadata["source_pair"]["songsterr"] = sources.get("songsterr", {})
        save_events(result.notes, args.output, result.metadata)
    except (OSError, ValueError, TypeError, KeyError, EOFError) as error:
        parser.exit(1, f"Could not import MIDI reference: {error}\n")
    print(f"Saved {len(result.notes)} candidate MIDI note events: {args.output.resolve()}")


if __name__ == "__main__":
    main()

"""Prepare local song/audio/tab bundles from explicit matching URLs."""

import argparse
import json
import re
import subprocess
from datetime import datetime
from pathlib import Path

from .collection import bundle_training_pair, fetch_local_tab_bundle
from .media import download_youtube, sha256_file, youtube_url


def collect_pair(
    song_id,
    songsterr_url,
    recording_url,
    output,
    *,
    server="http://127.0.0.1:5174",
    tab_permission="not recorded",
    recording_permission="not recorded",
):
    song_id = song_id.strip().lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,79}", song_id):
        raise ValueError("Use a song ID of up to 80 letters/digits/hyphens/underscores")
    youtube_url(recording_url)
    if output.exists() and any(output.iterdir()):
        raise ValueError("Choose an empty new collection folder")
    output.mkdir(parents=True, exist_ok=True)
    state = {
        "song_id": song_id,
        "songsterr_url": songsterr_url,
        "recording_url": recording_url,
        "complete": False,
    }
    state_path = output / "collection-state.json"
    state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    try:
        print("Fetching one complete tab revision from the local Songsterr downloader…", flush=True)
        tab = fetch_local_tab_bundle(
            songsterr_url, output / "downloads/songsterr-source.zip", server=server
        )
        print(
            "Downloading the explicitly selected recording and retaining its source audio…",
            flush=True,
        )
        audio = output / "downloads/audio"
        download_youtube(recording_url, audio)
        manifest = bundle_training_pair(
            song_id,
            audio / "audio-source.json",
            tab,
            output / "pair",
            tab_permission=tab_permission,
            recording_permission=recording_permission,
        )
        state.update(complete=True, pair_manifest="pair/pair.json")
    except Exception as error:
        state["error"] = str(error)
        raise
    finally:
        state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    return manifest


def collect_queue(path, output, *, server="http://127.0.0.1:5174"):
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if (
        not isinstance(payload, dict)
        or payload.get("format") != "tabber-collection-queue"
        or payload.get("schema_version") != 1
    ):
        raise ValueError("Use a version 1 tabber-collection-queue file")
    items = payload.get("items")
    if not isinstance(items, list) or not 1 <= len(items) <= 10000:
        raise ValueError("Queue must contain 1 to 10,000 explicit song pairs")
    identities = set()
    for item in items:
        if not isinstance(item, dict):
            raise TypeError("Each queue entry must be an object")
        for key in ("pair_id", "song_id"):
            value = item.get(key)
            if not isinstance(value, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,79}", value):
                raise ValueError(f"Queue {key} needs a lowercase song/recording identifier")
        if item["pair_id"] in identities:
            raise ValueError("Queue pair_id values must be unique")
        identities.add(item["pair_id"])
        youtube_url(item["youtube_url"])
        if not isinstance(item.get("songsterr_url"), str) or not item["songsterr_url"].startswith(
            "https://www.songsterr.com/a/wsa/"
        ):
            raise ValueError("Each queue entry needs a Songsterr HTTPS tab URL")
    if output.exists() and any(output.iterdir()):
        raise ValueError("Use an empty new batch output folder")
    output.mkdir(parents=True, exist_ok=True)
    report = {
        "format": "tabber-collection-results",
        "schema_version": 1,
        "queue_sha256": sha256_file(path),
        "requested_pairs": len(items),
        "results": [],
    }
    for item in items:
        row = {"pair_id": item["pair_id"], "song_id": item["song_id"], "complete": False}
        try:
            collect_pair(
                item["song_id"],
                item["songsterr_url"],
                item["youtube_url"],
                output / item["pair_id"],
                server=server,
                tab_permission=item.get("tab_permission_note", "not recorded"),
                recording_permission=item.get("recording_permission_note", "not recorded"),
            )
            row.update(complete=True, manifest=f"{item['pair_id']}/pair/pair.json")
        except (
            OSError,
            ValueError,
            KeyError,
            TypeError,
            RuntimeError,
            subprocess.CalledProcessError,
        ) as error:
            row["error"] = str(error)
        report["results"].append(row)
        report["all_succeeded"] = len(report["results"]) == len(items) and all(
            r["complete"] for r in report["results"]
        )
        (output / "collection-results.json").write_text(
            json.dumps(report, indent=2) + "\n", encoding="utf-8"
        )
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--song-id")
    parser.add_argument("--songsterr-url")
    parser.add_argument("--youtube-url")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--server", default="http://127.0.0.1:5174")
    parser.add_argument("--tab-permission-note", default="not recorded")
    parser.add_argument("--recording-permission-note", default="not recorded")
    parser.add_argument("--interactive", action="store_true")
    parser.add_argument(
        "--queue",
        type=Path,
        help="Collect an explicit JSON list sequentially and record every failure",
    )
    parser.add_argument(
        "--audio-manifest", type=Path, help="Bundle an already downloaded audio-source.json"
    )
    parser.add_argument(
        "--tab-bundle", type=Path, help="Bundle an already captured Songsterr source ZIP"
    )
    args = parser.parse_args()
    if args.interactive:
        args.song_id = args.song_id or input("Song group ID (artist-title): ").strip()
        args.songsterr_url = args.songsterr_url or input("Songsterr tab URL: ").strip()
        args.youtube_url = args.youtube_url or input("Matching YouTube recording URL: ").strip()
    try:
        if args.queue:
            if any(
                (
                    args.song_id,
                    args.songsterr_url,
                    args.youtube_url,
                    args.audio_manifest,
                    args.tab_bundle,
                    args.interactive,
                )
            ):
                raise ValueError("Use --queue separately from single-pair inputs")
            output = args.output or Path("data/training-pairs") / datetime.now().strftime(
                "%Y%m%d-%H%M%S-%f"
            )
            result = collect_queue(args.queue, output, server=args.server)
            print(f"Batch results: {(output / 'collection-results.json').resolve()}")
            if not result["all_succeeded"]:
                parser.exit(
                    1, "Some pairs failed; completed pairs and failure records were retained.\n"
                )
            return
        if not args.song_id:
            raise ValueError("Supply --song-id to keep versions of the same song grouped")
        output = args.output or Path("data/training-pairs") / datetime.now().strftime(
            "%Y%m%d-%H%M%S-%f"
        )
        if args.audio_manifest or args.tab_bundle:
            if (
                not args.audio_manifest
                or not args.tab_bundle
                or args.youtube_url
                or args.songsterr_url
            ):
                raise ValueError(
                    "For existing files, supply both --audio-manifest and --tab-bundle without download URLs"
                )
            bundle_training_pair(
                args.song_id,
                args.audio_manifest,
                args.tab_bundle,
                output,
                tab_permission=args.tab_permission_note,
                recording_permission=args.recording_permission_note,
            )
        else:
            if not args.youtube_url or not args.songsterr_url:
                raise ValueError("Supply both matching --songsterr-url and --youtube-url")
            collect_pair(
                args.song_id,
                args.songsterr_url,
                args.youtube_url,
                output,
                server=args.server,
                tab_permission=args.tab_permission_note,
                recording_permission=args.recording_permission_note,
            )
    except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Could not collect pair: {error}\n")
    print(f"Source pair prepared for review: {output.resolve()}")
    print("Alignment/version review is pending; no model training was started.")


if __name__ == "__main__":
    main()

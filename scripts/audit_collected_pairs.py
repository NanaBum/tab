"""Check collected pair assets and flag repeated source identities across song groups."""

import argparse
import json
from collections import defaultdict
from pathlib import Path, PurePosixPath

from tabber.collection import inspect_tab_bundle
from tabber.media import sha256_file

ROLES = ("audio_original", "audio_mp3", "score", "score_midi")


def verify_pair(manifest, pair):
    if pair["format"] != "tabber-training-pair" or pair["schema_version"] != 1:
        raise ValueError("Expected a version 1 pair manifest")
    song = pair["song_id"]
    if not isinstance(song, str) or not song.strip():
        raise ValueError("Missing song group")
    root = manifest.parent.resolve()
    assets = {}
    for item in pair["assets"]:
        name = item["path"]
        relative = PurePosixPath(name)
        target = (root / name).resolve()
        if (
            name in assets
            or relative.as_posix() != name
            or ".." in relative.parts
            or "\\" in name
            or ":" in name
            or relative.is_absolute()
            or not target.is_relative_to(root)
            or not target.is_file()
            or target == manifest.resolve()
        ):
            raise ValueError(f"Missing, duplicate or unsafe asset path: {name}")
        if target.stat().st_size != item["bytes"] or sha256_file(target) != item["sha256"]:
            raise ValueError(f"Asset changed: {name}")
        assets[name] = item
    original, preview, gp7, midi = (assets[pair["roles"][key]] for key in ROLES)
    audio = pair["sources"]["audio"]
    tab = pair["sources"]["songsterr"]
    if (
        "audio/audio-source.json" not in assets
        or json.loads((root / "audio/audio-source.json").read_text(encoding="utf-8-sig")) != audio
    ):
        raise ValueError("The embedded audio manifest disagrees with the pair")
    archive = root / assets["songsterr-source.zip"]["path"]
    tab_manifest, files = inspect_tab_bundle(archive.read_bytes())
    if tab_manifest["source"] != tab:
        raise ValueError("The embedded tab revision disagrees with the pair")
    for relative, value in files.items():
        name = f"tab/{relative}"
        if name not in assets or (root / name).read_bytes() != value:
            raise ValueError(f"Extracted score file disagrees with the tab capture: {name}")
    if gp7["path"] != "tab/score.gp7" or midi["path"] != "tab/score.mid":
        raise ValueError("The score roles disagree with the tab capture")
    for role, asset in (("original", original), ("mp3", preview)):
        declared = audio["assets"][role]
        if declared != {**asset, "path": PurePosixPath(asset["path"]).name}:
            raise ValueError(f"The {role} audio role disagrees with the source record")
    identities = {
        "recording_id": str(audio["source_metadata"]["id"]),
        "recording_sha256": original["sha256"],
        "songsterr_song_id": str(tab["song_id"]),
        "score_sha256": gp7["sha256"],
        "score_midi_sha256": midi["sha256"],
    }
    if any(not value or value == "None" for value in identities.values()):
        raise ValueError("Missing recording or score identity")
    return {
        "song_id": song,
        "source_identity": identities,
        "version_review": pair["recording_version_review"],
        "alignment_status": pair["alignment"]["status"],
        "asset_count": len(assets),
        "asset_bytes": sum(item["bytes"] for item in assets.values()),
    }


def audit(root):
    root = root.resolve(strict=True)
    passed, invalid, fixtures = [], [], []
    identities = defaultdict(list)
    exact_pairs = defaultdict(list)
    manifests = sorted(root.glob("*/*/pair/pair.json"))
    if not manifests:
        raise ValueError("No pair manifests found under the collection root")
    for manifest in manifests:
        relative = manifest.relative_to(root).as_posix()
        try:
            if not manifest.resolve().is_relative_to(root):
                raise ValueError("Pair manifest escapes the collection root")
            pair = json.loads(manifest.read_text(encoding="utf-8-sig"))
            if pair.get("test_fixture") or pair.get("excluded_from_training"):
                fixtures.append(relative)
                continue
            result = verify_pair(manifest, pair)
        except (OSError, KeyError, TypeError, ValueError) as error:
            invalid.append({"manifest": relative, "error": str(error)})
            continue
        passed.append({"manifest": relative, **result})
        for kind, value in result["source_identity"].items():
            identities[kind, value].append((relative, result["song_id"]))
        source = result["source_identity"]
        exact_pairs[source["recording_sha256"], source["score_sha256"]].append(relative)
    conflicts = [
        {"identity_type": kind, "identity": value, "members": members}
        for (kind, value), members in identities.items()
        if len({group for _, group in members}) > 1
    ]
    duplicates = [members for members in exact_pairs.values() if len(members) > 1]
    return {
        "verified_pairs": len(passed),
        "song_groups": len({pair["song_id"] for pair in passed}),
        "verified_asset_count": sum(pair["asset_count"] for pair in passed),
        "verified_asset_bytes": sum(pair["asset_bytes"] for pair in passed),
        "cross_group_source_conflicts": conflicts,
        "duplicate_bundles": duplicates,
        "invalid_pairs": invalid,
        "excluded_fixtures": fixtures,
        "pairs": passed,
        "limits": "Hash and identity checks only. Musical recording-version match and alignment require separate checks.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="Collection root containing batch directories")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = audit(args.root)
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, indent=2)
            stream.write("\n")
    except (OSError, ValueError) as error:
        parser.exit(1, f"Could not audit collection: {error}\n")
    print(f"Verified {report['verified_pairs']} pairs across {report['song_groups']} song groups")
    if any(
        report[k] for k in ("invalid_pairs", "cross_group_source_conflicts", "duplicate_bundles")
    ):
        parser.exit(1, f"Review collection issues in {args.output}\n")


if __name__ == "__main__":
    main()

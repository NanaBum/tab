"""Collect exact audio/tab assets into reviewable local training-pair bundles."""

import hashlib
import io
import json
import re
import shutil
import urllib.error
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

from .media import sha256_file

MAX_BUNDLE_BYTES = 100 * 1024 * 1024


def fetch_local_tab_bundle(songsterr_url, destination, *, server="http://127.0.0.1:5174"):
    location = urlsplit(server)
    if (
        location.scheme != "http"
        or location.hostname not in {"127.0.0.1", "localhost", "::1"}
        or location.username
        or location.password
        or location.path not in ("", "/")
        or location.query
        or location.fragment
    ):
        raise ValueError("Use the local Songsterr server on a loopback HTTP address")
    if destination.exists():
        raise ValueError("The tab bundle output already exists")
    request = urllib.request.Request(
        server.rstrip("/") + "/api/local-bundle",
        data=json.dumps({"byLinkUrl": songsterr_url}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            body = response.read(MAX_BUNDLE_BYTES + 1)
            if len(body) > MAX_BUNDLE_BYTES:
                raise ValueError("Tab bundle exceeds the 100 MiB transfer limit")
            digest = response.headers.get("X-Bundle-SHA256")
            if not digest or hashlib.sha256(body).hexdigest() != digest:
                raise ValueError("Local tab bundle checksum was missing or did not match")
    except urllib.error.HTTPError as error:
        detail = error.read(4096).decode("utf-8", errors="replace")
        raise ValueError(f"Local tab downloader returned {error.code}: {detail}") from error
    except urllib.error.URLError as error:
        raise ValueError(
            f"Could not reach the local tab downloader at {server}; start it with its launcher first"
        ) from error
    inspect_tab_bundle(body)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("xb") as stream:
        stream.write(body)
    return destination


def _inspect_tab_bundle(content):
    """Check bounded ZIP membership, track completeness and exact asset hashes."""
    if len(content) > MAX_BUNDLE_BYTES:
        raise ValueError("Tab bundle is too large")
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        members = archive.infolist()
        names = [item.filename for item in members]
        if (
            len(set(names)) != len(names)
            or sum(item.file_size for item in members) > MAX_BUNDLE_BYTES
        ):
            raise ValueError("Tab bundle has duplicate entries or excessive expanded size")
        for item in members:
            path = PurePosixPath(item.filename)
            if (
                path.is_absolute()
                or ".." in path.parts
                or "\\" in item.filename
                or ":" in item.filename
                or item.is_dir()
                or (item.external_attr >> 16) & 0o170000 == 0o120000
            ):
                raise ValueError("Unsafe tab bundle path or entry type")
        files = {name: archive.read(name) for name in names}
    manifest = json.loads(files["manifest.json"])
    if (
        manifest.get("format") != "songsterr-local-source-bundle"
        or manifest.get("schema_version") != 1
    ):
        raise ValueError("Use a version 1 source bundle from our local Songsterr downloader")
    assets = manifest["assets"]
    if not isinstance(assets, list) or len({a["path"] for a in assets}) != len(assets):
        raise ValueError("Invalid or duplicate tab bundle asset declarations")
    if {a["path"] for a in assets} != set(files) - {"manifest.json"}:
        raise ValueError("Tab bundle declarations do not cover exactly its saved files")
    for asset in assets:
        payload = files[asset["path"]]
        if len(payload) != asset["bytes"] or hashlib.sha256(payload).hexdigest() != asset["sha256"]:
            raise ValueError(f"Tab asset checksum/size mismatch: {asset['path']}")
    tracks, completeness = manifest["tracks"], manifest["completeness"]
    if (
        completeness.get("complete") is not True
        or completeness["declared_track_count"] != len(tracks)
        or completeness["fetched_track_count"] != len(tracks)
        or completeness.get("missing_part_ids")
    ):
        raise ValueError("Tab bundle is not a complete declared-track capture")
    if (
        not tracks
        or len({t["part_id"] for t in tracks}) != len(tracks)
        or any(t["source_file"] not in files for t in tracks)
    ):
        raise ValueError("Invalid track identities or missing original track JSON")
    expected_files = {"manifest.json", "score.gp7", "score.mid", "source/metadata.json"}
    for track in tracks:
        identity = track["part_id"]
        if (
            type(identity) is not int
            or identity < 0
            or track["source_file"] != f"source/tracks/part-{identity}.json"
        ):
            raise ValueError("Track IDs must match their exact saved source filenames")
        expected_files.add(track["source_file"])
    if set(files) != expected_files:
        raise ValueError("Unexpected files in the version 1 tab source bundle")
    if not {"score.gp7", "score.mid", "source/metadata.json"}.issubset(files):
        raise ValueError("Tab bundle lacks required score/source files")
    return manifest, files


def inspect_tab_bundle(content):
    try:
        return _inspect_tab_bundle(content)
    except (zipfile.BadZipFile, KeyError, TypeError, AttributeError, json.JSONDecodeError) as error:
        raise ValueError(f"Invalid tab source bundle: {error}") from error


def bundle_training_pair(
    song_id,
    audio_manifest,
    tab_bundle,
    output,
    *,
    tab_permission="not recorded",
    recording_permission="not recorded",
):
    song_id = song_id.strip().lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,79}", song_id):
        raise ValueError(
            "Use a song ID with letters, digits, hyphens or underscores, up to 80 characters"
        )
    output = Path(output).resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError("Use an empty new training-pair output folder")
    audio_manifest, tab_bundle = Path(audio_manifest).resolve(), Path(tab_bundle).resolve()
    audio = json.loads(audio_manifest.read_text(encoding="utf-8-sig"))
    if audio.get("format") != "tabber-audio-download" or audio.get("schema_version") != 1:
        raise ValueError("Use an audio-source.json from the local audio downloader")
    tab, files = inspect_tab_bundle(tab_bundle.read_bytes())
    sources = {}
    for role in ("original", "mp3"):
        asset = audio["assets"][role]
        relative = PurePosixPath(asset["path"])
        if (
            relative.is_absolute()
            or len(relative.parts) != 1
            or "\\" in asset["path"]
            or ":" in asset["path"]
        ):
            raise ValueError("Audio asset paths must be simple local filenames")
        path = audio_manifest.parent / asset["path"]
        if (
            not path.is_file()
            or path.stat().st_size != asset["bytes"]
            or sha256_file(path) != asset["sha256"]
        ):
            raise ValueError(f"Missing or changed audio asset: {role}")
        sources[role] = path
    output.mkdir(parents=True, exist_ok=True)
    original = output / "audio" / sources["original"].name
    preview = output / "audio" / sources["mp3"].name
    original.parent.mkdir()
    shutil.copy2(sources["original"], original)
    if preview != original:
        shutil.copy2(sources["mp3"], preview)
    shutil.copy2(audio_manifest, output / "audio/audio-source.json")
    shutil.copy2(tab_bundle, output / "songsterr-source.zip")
    for name, content in files.items():
        destination = output / "tab" / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
    assets = [
        {
            "path": p.relative_to(output).as_posix(),
            "bytes": p.stat().st_size,
            "sha256": sha256_file(p),
        }
        for p in sorted(output.rglob("*"))
        if p.is_file()
    ]
    manifest = {
        "format": "tabber-training-pair",
        "schema_version": 1,
        "song_id": song_id,
        "split": "unassigned",
        "label_status": "candidate",
        "recording_version_review": "pending",
        "alignment": {"status": "pending", "global_shift_seconds": None},
        "sources": {"audio": audio, "songsterr": tab["source"]},
        "permission_notes": {"tab": tab_permission, "recording": recording_permission},
        "roles": {
            "audio_original": original.relative_to(output).as_posix(),
            "audio_mp3": preview.relative_to(output).as_posix(),
            "score": "tab/score.gp7",
            "score_midi": "tab/score.mid",
        },
        "tab_warnings": tab.get("warnings", {}),
        "assets": assets,
        "limits": "Packaged source assets, not aligned training tensors. GP7 is not accepted by the existing GP3/4/5 reference importer. Check matching recording/version, choose target track and review alignment before use. Related versions share song_id across dataset splits. No model training performed.",
    }
    (output / "pair.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest

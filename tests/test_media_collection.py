import hashlib
import io
import json
import sys
import zipfile
from pathlib import Path
from types import ModuleType

import pytest

from tabber.collect import collect_queue
from tabber.collection import bundle_training_pair, fetch_local_tab_bundle, inspect_tab_bundle
from tabber.media import convert_mp3, download_youtube, sha256_file, youtube_url


@pytest.mark.parametrize(
    "url",
    [
        "https://youtu.be/jNQXAC9IVRw",
        "https://www.youtube.com/watch?v=jNQXAC9IVRw&list=ignored",
        "https://music.youtube.com/watch?v=jNQXAC9IVRw",
    ],
)
def test_youtube_identity_is_one_canonical_video(url):
    assert youtube_url(url) == ("https://www.youtube.com/watch?v=jNQXAC9IVRw", "jNQXAC9IVRw")


@pytest.mark.parametrize(
    "url",
    [
        "https://youtube.com.evil.test/watch?v=jNQXAC9IVRw",
        "file:///private",
        "https://www.youtube.com/playlist?list=abc",
        "https://user:secret@youtube.com/watch?v=jNQXAC9IVRw",
    ],
)
def test_nonvideo_or_credential_urls_are_rejected(url):
    with pytest.raises(ValueError):
        youtube_url(url)


def test_download_keeps_source_and_writes_identity_hashes_without_core_dependency(
    tmp_path, monkeypatch
):
    options_seen = {}

    class FakeYoutube:
        def __init__(self, options):
            options_seen.update(options)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def extract_info(self, url, download):
            assert url == "https://www.youtube.com/watch?v=jNQXAC9IVRw" and download
            Path(self.prepare_filename({})).write_bytes(b"original encoded audio")
            return {
                "id": "jNQXAC9IVRw",
                "title": "synthetic test",
                "channel": "fixture",
                "duration": 2,
            }

        def prepare_filename(self, info):
            return (
                options_seen["outtmpl"].replace("%(id)s", "jNQXAC9IVRw").replace("%(ext)s", "webm")
            )

    module, version, utils = (
        ModuleType("yt_dlp"),
        ModuleType("yt_dlp.version"),
        ModuleType("yt_dlp.utils"),
    )
    module.YoutubeDL, version.__version__, utils.DownloadError = FakeYoutube, "test", RuntimeError
    for name, value in (("yt_dlp", module), ("yt_dlp.version", version), ("yt_dlp.utils", utils)):
        monkeypatch.setitem(sys.modules, name, value)
    monkeypatch.setattr("tabber.media.find_ffmpeg", lambda value=None: tmp_path / "ffmpeg.exe")
    monkeypatch.setattr(
        "tabber.media.convert_mp3",
        lambda source, destination, **kwargs: destination.write_bytes(b"MP3 preview"),
    )
    result = download_youtube("https://youtu.be/jNQXAC9IVRw", tmp_path / "output")
    assert options_seen["noplaylist"] is True and options_seen["format"] == "bestaudio"
    for role in ("original", "mp3"):
        asset = result["assets"][role]
        assert sha256_file(tmp_path / "output" / asset["path"]) == asset["sha256"]
    assert (tmp_path / "output/jNQXAC9IVRw.webm").read_bytes() == b"original encoded audio"


def source_zip(problem=None):
    files = {
        "score.gp7": b"synthetic GP7 fixture",
        "score.mid": b"synthetic MIDI fixture",
        "source/metadata.json": b"{}",
        "source/tracks/part-0.json": b"{}",
    }
    if problem == "unsafe":
        files["../escape"] = b"unsafe"
    manifest = {
        "format": "songsterr-local-source-bundle",
        "schema_version": 1,
        "source": {"song_id": 1, "revision_id": 2},
        "completeness": {
            "complete": True,
            "declared_track_count": 1,
            "fetched_track_count": 1,
            "missing_part_ids": [],
        },
        "tracks": [{"part_id": 0, "source_file": "source/tracks/part-0.json"}],
        "assets": [
            {"path": name, "bytes": len(value), "sha256": hashlib.sha256(value).hexdigest()}
            for name, value in files.items()
        ],
    }
    if problem == "changed":
        files["score.mid"] = b"changed"
    if problem == "missing":
        del files["score.mid"]
    if problem == "incomplete":
        manifest["completeness"]["complete"] = False
    if problem == "extra":
        files["extra.txt"] = b"unlisted"
    if problem == "track":
        manifest["tracks"][0]["part_id"] = 1
    files["manifest.json"] = json.dumps(manifest).encode()
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        for name, value in files.items():
            archive.writestr(name, value)
    return stream.getvalue()


@pytest.mark.parametrize(
    "problem", ["changed", "missing", "incomplete", "unsafe", "extra", "track"]
)
def test_bad_source_bundles_fail_without_extracting(problem):
    with pytest.raises(ValueError):
        inspect_tab_bundle(source_zip(problem))


def test_pair_retains_sources_hashes_and_pending_alignment(tmp_path):
    download = tmp_path / "download"
    download.mkdir()
    assets = {}
    for role, name, value in (
        ("original", "recording.webm", b"original"),
        ("mp3", "recording.mp3", b"preview"),
    ):
        path = download / name
        path.write_bytes(value)
        assets[role] = {"path": name, "bytes": len(value), "sha256": sha256_file(path)}
    audio = download / "audio-source.json"
    audio.write_text(
        json.dumps(
            {
                "format": "tabber-audio-download",
                "schema_version": 1,
                "source_url": "test",
                "assets": assets,
            }
        )
    )
    tab = tmp_path / "tab.zip"
    tab.write_bytes(source_zip())
    output = tmp_path / "pair"
    result = bundle_training_pair(
        "Artist-Song",
        audio,
        tab,
        output,
        tab_permission="received",
        recording_permission="owner supplied",
    )
    assert result["song_id"] == "artist-song" and result["split"] == "unassigned"
    assert result["alignment"]["status"] == "pending" and result["label_status"] == "candidate"
    assert result["permission_notes"]["tab"] == "received"
    assert (output / result["roles"]["audio_original"]).read_bytes() == b"original"
    for asset in result["assets"]:
        assert sha256_file(output / asset["path"]) == asset["sha256"]
    assert (download / "recording.webm").read_bytes() == b"original"


def test_invalid_server_is_rejected_before_request(tmp_path):
    with pytest.raises(ValueError, match="loopback"):
        fetch_local_tab_bundle("anything", tmp_path / "tab.zip", server="https://someone.example")


def test_mp3_conversion_never_overwrites_source_or_existing_output(tmp_path):
    source = tmp_path / "input.mp3"
    source.write_bytes(b"keep")
    with pytest.raises(ValueError):
        convert_mp3(source, source)
    assert source.read_bytes() == b"keep"


def queue_file(tmp_path, duplicate=False):
    rows = [
        {
            "pair_id": identity,
            "song_id": "same-song",
            "songsterr_url": "https://www.songsterr.com/a/wsa/example-tab-s1",
            "youtube_url": "https://www.youtube.com/watch?v=jNQXAC9IVRw",
        }
        for identity in ("first", "first" if duplicate else "second")
    ]
    path = tmp_path / "queue.json"
    path.write_text(
        json.dumps({"format": "tabber-collection-queue", "schema_version": 1, "items": rows})
    )
    return path


def test_batch_retains_every_failure_and_continues_to_other_explicit_pairs(tmp_path, monkeypatch):
    path = queue_file(tmp_path)
    calls = []

    def collect(song_id, tab, audio, output, **kwargs):
        calls.append(output.name)
        if output.name == "first":
            raise ValueError("Source unavailable")

    monkeypatch.setattr("tabber.collect.collect_pair", collect)
    result = collect_queue(path, tmp_path / "batch")
    assert calls == ["first", "second"] and result["all_succeeded"] is False
    assert [row["complete"] for row in result["results"]] == [False, True]
    assert result["results"][0]["error"] == "Source unavailable"
    assert (tmp_path / "batch/collection-results.json").exists()


def test_duplicate_batch_ids_fail_before_any_download(tmp_path, monkeypatch):
    path = queue_file(tmp_path, duplicate=True)
    monkeypatch.setattr(
        "tabber.collect.collect_pair", lambda *a, **k: pytest.fail("Must validate first")
    )
    with pytest.raises(ValueError, match="unique"):
        collect_queue(path, tmp_path / "batch")
    assert not (tmp_path / "batch").exists()

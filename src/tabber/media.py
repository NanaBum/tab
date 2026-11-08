"""Local single-recording download and MP3 conversion; optional yt-dlp environment."""

import argparse
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path
from urllib.parse import parse_qs, urlsplit


def sha256_file(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def youtube_url(value):
    parsed = urlsplit(value.strip())
    if (
        parsed.scheme != "https"
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
    ):
        raise ValueError("Paste a complete HTTPS YouTube video URL")
    host = (parsed.hostname or "").lower()
    if host in {"youtu.be", "www.youtu.be"}:
        video_id = parsed.path.strip("/")
    elif host in {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"}:
        if parsed.path == "/watch":
            values = parse_qs(parsed.query).get("v", [])
            video_id = values[0] if len(values) == 1 else ""
        else:
            match = re.fullmatch(r"/(?:shorts|embed|live)/([A-Za-z0-9_-]{11})/?", parsed.path)
            video_id = match.group(1) if match else ""
    else:
        video_id = ""
    if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
        raise ValueError("Use one YouTube video, not a channel, playlist or another website")
    return f"https://www.youtube.com/watch?v={video_id}", video_id


def find_ffmpeg(explicit=None):
    if explicit:
        result = Path(explicit).resolve()
        if not result.is_file():
            raise ValueError("The supplied FFmpeg executable was not found")
        return result
    executable = shutil.which("ffmpeg")
    if executable:
        return Path(executable)
    root = Path(__file__).resolve().parents[2]
    candidates = sorted(
        (root / ".venv-audio/Lib/site-packages/imageio_ffmpeg/binaries").glob("ffmpeg*.exe")
    )
    if candidates:
        return candidates[-1]
    raise ValueError("FFmpeg is needed; supply --ffmpeg or set up the local audio environment")


def convert_mp3(source, destination, *, ffmpeg=None):
    """Create an MP3 while retaining source bytes; never overwrite an existing file."""
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if destination.suffix.lower() != ".mp3":
        raise ValueError("The MP3 output filename must end in .mp3")
    if not source.is_file() or source == destination or destination.exists():
        raise ValueError("Choose an existing input and a new, different MP3 output path")
    destination.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            str(find_ffmpeg(ffmpeg)),
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "warning",
            "-n",
            "-i",
            str(source),
            "-vn",
            "-c:a",
            "libmp3lame",
            "-b:a",
            "320k",
            str(destination),
        ],
        check=True,
    )
    return destination


def download_youtube(url, output, *, ffmpeg=None, max_duration=7200):
    canonical, video_id = youtube_url(url)
    executable = find_ffmpeg(ffmpeg)
    output = Path(output).resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError("Choose an empty output folder so earlier downloads remain untouched")
    if not 0 < max_duration <= 86400:
        raise ValueError("Maximum recording duration must be between 1 second and 24 hours")
    try:
        from yt_dlp import YoutubeDL
        from yt_dlp.utils import DownloadError
        from yt_dlp.version import __version__
    except ImportError as error:
        raise ValueError("Use the separate media environment with yt-dlp installed") from error

    def selected_recording(info, *, incomplete=False):
        if info.get("is_live") or info.get("live_status") in {"is_upcoming", "is_live"}:
            return "Use a completed recording rather than a live stream"
        if info.get("duration") and info["duration"] > max_duration:
            return f"Recording exceeds the {max_duration:g}-second duration limit"
        return None

    options = {
        "format": "bestaudio",
        "noplaylist": True,
        "outtmpl": str(output / "%(id)s.%(ext)s"),
        "windowsfilenames": True,
        "keepvideo": True,
        "overwrites": False,
        "ffmpeg_location": str(executable),
        "socket_timeout": 30,
        "retries": 3,
        "fragment_retries": 3,
        "match_filter": selected_recording,
    }
    node = shutil.which("node")
    if node:
        options["js_runtimes"] = {"node": {"path": node}}
    output.mkdir(parents=True, exist_ok=True)
    try:
        with YoutubeDL(options) as downloader:
            info = downloader.extract_info(canonical, download=True)
    except DownloadError as error:
        raise ValueError(f"YouTube download failed: {error}") from error
    if not info or info.get("id") != video_id or info.get("_type") in {"playlist", "multi_video"}:
        raise ValueError("The selected recording was not downloaded as one expected video")
    original = Path(downloader.prepare_filename(info)).resolve()
    if not original.is_file() or output not in original.parents:
        raise ValueError("The original downloaded audio file was not found in the output folder")
    mp3 = output / f"{video_id}.mp3"
    if original.suffix.lower() == ".mp3":
        mp3 = original
    else:
        convert_mp3(original, mp3, ffmpeg=executable)
    fields = (
        "id",
        "title",
        "artist",
        "track",
        "album",
        "channel",
        "channel_id",
        "uploader",
        "upload_date",
        "duration",
        "license",
        "webpage_url",
    )
    manifest = {
        "format": "tabber-audio-download",
        "schema_version": 1,
        "source_url": canonical,
        "selected_url": url,
        "source_metadata": {k: info.get(k) for k in fields},
        "tool": {"name": "yt-dlp", "version": __version__, "javascript_runtime": node},
        "recording_version_review": "pending; title/channel do not establish an official or matching version",
        "permission_note": "not recorded",
        "original_retained": True,
        "assets": {
            name: {"path": path.name, "bytes": path.stat().st_size, "sha256": sha256_file(path)}
            for name, path in (("original", original), ("mp3", mp3))
        },
    }
    (output / "audio-source.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", nargs="?")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ffmpeg", type=Path)
    parser.add_argument("--max-duration", type=float, default=7200)
    parser.add_argument(
        "--local-audio", type=Path, help="Convert an existing local file without downloading"
    )
    args = parser.parse_args()
    try:
        if args.local_audio:
            if args.url:
                raise ValueError("Choose a YouTube URL or --local-audio, not both")
            convert_mp3(args.local_audio, args.output, ffmpeg=args.ffmpeg)
        elif args.url:
            download_youtube(
                args.url, args.output, ffmpeg=args.ffmpeg, max_duration=args.max_duration
            )
        else:
            raise ValueError("Supply a YouTube video URL or --local-audio")
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Could not prepare audio: {error}\n")
    print(f"Audio ready: {args.output.resolve()}")


if __name__ == "__main__":
    main()

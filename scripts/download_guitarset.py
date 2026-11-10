"""Download selected original GuitarSet v1.1.0 archives with checksum verification."""

import argparse
import hashlib
import shutil
import time
import urllib.request
from pathlib import Path

FILES = {
    "annotations": ("annotation.zip", "b39b78e63d3446f2e54ddb7a54df9b10"),
    "audio": ("audio_mono-mic.zip", "275966d6610ac34999b58426beb119c3"),
}


def checksum(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "md5").hexdigest()


def download(filename, expected, output):
    target = output / filename
    if target.is_file() and checksum(target) == expected:
        print(f"Already verified {target}", flush=True)
        return
    temporary = target.with_suffix(".part")
    url = f"https://zenodo.org/api/records/3371780/files/{filename}/content"
    for attempt in range(3):
        try:
            print(f"Downloading {filename} (attempt {attempt + 1}/3)", flush=True)
            with (
                urllib.request.urlopen(url, timeout=30) as response,
                temporary.open("wb") as stream,
            ):
                shutil.copyfileobj(response, stream, length=1024 * 1024)
            if checksum(temporary) != expected:
                raise ValueError(f"Checksum mismatch for {filename}")
            temporary.replace(target)
            print(f"Verified {target}; extract manually when needed", flush=True)
            return
        except (OSError, ValueError):
            if attempt == 2:
                raise
            time.sleep(2)


def main():
    parser = argparse.ArgumentParser(description="GuitarSet download; audio is about 657 MB")
    parser.add_argument("--include-audio", action="store_true")
    parser.add_argument("--output", type=Path, default=Path("data/guitarset"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    for kind in ["annotations", "audio"] if args.include_audio else ["annotations"]:
        filename, expected = FILES[kind]
        download(filename, expected, args.output)


if __name__ == "__main__":
    main()

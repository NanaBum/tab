"""Download selected original GuitarSet v1.1.0 archives with checksum verification."""

import argparse
import hashlib
import urllib.request
from pathlib import Path

FILES = {
    "annotations": ("annotation.zip", "b39b78e63d3446f2e54ddb7a54df9b10"),
    "audio": ("audio_mono-mic.zip", "275966d6610ac34999b58426beb119c3"),
}


def main():
    parser = argparse.ArgumentParser(description="GuitarSet download; audio is about 657 MB")
    parser.add_argument("--include-audio", action="store_true")
    parser.add_argument("--output", type=Path, default=Path("data/guitarset"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    for kind in ["annotations", "audio"] if args.include_audio else ["annotations"]:
        filename, expected = FILES[kind]
        target = args.output / filename
        temporary = target.with_suffix(".part")
        print(f"Downloading {filename}", flush=True)
        urllib.request.urlretrieve(
            f"https://zenodo.org/records/3371780/files/{filename}?download=1", temporary
        )
        with temporary.open("rb") as stream:
            actual = hashlib.file_digest(stream, "md5").hexdigest()
        if actual != expected:
            temporary.unlink()
            raise ValueError(f"Checksum mismatch for {filename}")
        temporary.replace(target)
        print(f"Verified {target}; extract manually when needed")


if __name__ == "__main__":
    main()

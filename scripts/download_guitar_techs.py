"""Download the 354 MB Guitar-TECHS timbre pilot and verify published checksums."""

import argparse
import hashlib
import tempfile
import urllib.request
from pathlib import Path

RECORD = "https://zenodo.org/api/records/14963133/files"
FILES = {
    "P1_singlenotes.zip": (108626613, "ca0c4674dde3805574685a313f7c39eb"),
    "P2_singlenotes.zip": (116133457, "40fbf03d8b04bb2cf42df20f36dc2254"),
    "P3_music.zip": (129505089, "071ba80aecf00f4a31fbd167b3f22198"),
}


def verify(path, size, expected):
    with path.open("rb") as stream:
        if path.stat().st_size != size or hashlib.file_digest(stream, "md5").hexdigest() != expected:
            raise ValueError(f"Archive size or checksum differs: {path.name}")


def download(output, name, size, expected):
    target = output / name
    if not target.exists():
        with tempfile.TemporaryDirectory(prefix=".guitar-techs-", dir=output) as stage:
            temporary = Path(stage) / name
            remaining = size
            print(f"Downloading {name} ({size / 1e6:.1f} MB)", flush=True)
            with (
                urllib.request.urlopen(f"{RECORD}/{name}/content", timeout=45) as response,
                temporary.open("xb") as stream,
            ):
                while chunk := response.read(min(remaining + 1, 1024 * 1024)):
                    remaining -= len(chunk)
                    if remaining < 0:
                        raise ValueError(f"Download exceeded the pinned size: {name}")
                    stream.write(chunk)
            verify(temporary, size, expected)
            target.hardlink_to(temporary)
    verify(target, size, expected)
    print(f"Verified {name}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("data/guitar-techs"))
    args = parser.parse_args()
    try:
        args.output.mkdir(parents=True, exist_ok=True)
        for name, (size, expected) in FILES.items():
            download(args.output, name, size, expected)
    except (OSError, ValueError) as error:
        parser.exit(1, f"Could not retrieve Guitar-TECHS: {error}\n")


if __name__ == "__main__":
    main()

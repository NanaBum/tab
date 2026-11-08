"""Explicitly download the ~99 MB published guitar checkpoint and verify SHA-256."""

import argparse
import json
import tempfile
import urllib.request
from pathlib import Path

from tabber.guitar_gaps import (
    CHECKPOINT_NAME,
    CHECKPOINT_SHA256,
    MODEL_REPOSITORY,
    MODEL_REVISION,
    checkpoint_digest,
    default_checkpoint,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=default_checkpoint())
    args = parser.parse_args()
    target = args.output.resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    url = f"https://huggingface.co/{MODEL_REPOSITORY}/resolve/{MODEL_REVISION}/{CHECKPOINT_NAME}"
    if not target.is_file() or checkpoint_digest(target) != CHECKPOINT_SHA256:
        print(
            "Downloading approximately 99 MB for local guitar inference; no training.", flush=True
        )
        with tempfile.NamedTemporaryFile(
            dir=target.parent, suffix=".download", delete=False
        ) as stream:
            temporary = Path(stream.name)
        try:
            with (
                urllib.request.urlopen(url, timeout=30) as response,
                temporary.open("wb") as stream,
            ):
                total = 0
                while block := response.read(1024 * 1024):
                    stream.write(block)
                    total += len(block)
                    if total // (10 * 1024 * 1024) != (total - len(block)) // (10 * 1024 * 1024):
                        print(f"Downloaded {total // (1024 * 1024)} MiB", flush=True)
            if checkpoint_digest(temporary) != CHECKPOINT_SHA256:
                raise ValueError("Downloaded checkpoint checksum mismatch")
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
    provenance = {
        "repository": MODEL_REPOSITORY,
        "revision": MODEL_REVISION,
        "filename": CHECKPOINT_NAME,
        "sha256": CHECKPOINT_SHA256,
        "bytes": target.stat().st_size,
        "source": url,
    }
    target.with_suffix(".provenance.json").write_text(
        json.dumps(provenance, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Verified local checkpoint: {target}")


if __name__ == "__main__":
    main()

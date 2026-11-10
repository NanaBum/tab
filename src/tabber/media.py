"""Hash local files for reproducible checks."""

import hashlib


def sha256_file(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()

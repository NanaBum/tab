"""Retrieve fixed electric pieces or picked licks (~5 MB each) from IDMT's archive.

Uses checked HTTP ranges, ZIP CRC32 and locally pinned per-member SHA-256.
Does not download or claim to verify the complete 1.33 GB archive's MD5.
"""

import argparse
import hashlib
import io
import json
import tempfile
import urllib.request
import zipfile
from pathlib import Path

URL = "https://zenodo.org/api/records/7544110/files/IDMT-SMT-GUITAR_V2.zip/content"
SIZE = 1329918978
FILES = {
    "annotation/nocturneNr2.xml": "8395037434bfd3af2cb9b0a52cac2bd7a965ecff13e904f0400e4773c9060cfe",
    "annotation/pathetique_mono.xml": "fcb1226bebf2571c220bdf84d47e3f8bbaf31782b3be4cd8d0665b772cae88b3",
    "annotation/pathetique_poly.xml": "fcbd58e526b1bf899cec178f13472766a6eaa2b23346f571cb92ae780268582f",
    "annotation/promenade_mono.xml": "07a2d03eb0f25a89b5d51e214f9662ef4b6a61ce73af103cff70d3a9be57d17c",
    "annotation/quintfall.xml": "f17b23e85b954908bf65d08e35eca14b61e6c6982fc5f2f635275762ab1b422a",
    "audio/nocturneNr2.wav": "8333a6d3d224e35193defcd9724aa42085c6b71d0ba24ff1045f6f1c58acc25a",
    "audio/pathetique_mono.wav": "c8f56672faadf3062e8cee33ddef77a71d3eb975c8a8a5d92292e64eb6383184",
    "audio/pathetique_poly.wav": "f4611abb9be67b67a4cf80c5e0225bb4a129e12a5c4278d90b648b92b922d854",
    "audio/promenade_mono.wav": "b33b99b1d88319cc141b78ea58a4da4c507923d3e2af366e898ce55c9ad4f47e",
    "audio/quintfall.wav": "0863de6b236f12d1d2d82131132939d6bbe2bc8f126e7c2aadb71d962c58586b",
}
LICK_FILES = {
    "annotation/AR_Lick1_KN.xml": "412d30e12a1e79f4fa64f69854f7f08de65a814a308b7dc46a023f40fe602af6",
    "audio/AR_Lick1_KN.wav": "18597b2dc85aff01395a638ef848e529ef789796a9be7ff5a904165b0ab61ce6",
    "annotation/AR_Lick6_KN.xml": "be6438c7a17d7112fc0014c2e8fc18fd93b3f354c4456e03029287f4ea8cda55",
    "audio/AR_Lick6_KN.wav": "3b757b97faf92ac6b925dce69a918a694c6794553e27e7b8ae2b10e2cf09d9dc",
    "annotation/AR_Lick12_KN.xml": "5d342d786c5d47eeca1dd5954177306ab7b29ad6c19a13c2c2ea2c5595d158d4",
    "audio/AR_Lick12_KN.wav": "e7f786c769cff6438db8f1225d15db2e0c0e1e97f75f92d8bb71de3beed57e9c",
}
MUTED_FILES = {
    "annotation/AR_Lick1_MN.xml": "92c128e0e99db04bba2c8d88bc5d57fb0b52722f81a5971afb5c5177340ddaa1",
    "audio/AR_Lick1_MN.wav": "f53d237d237f5655004ea729e52f2cdff3c2b31ff4e6494fd1bdbcc99da76815",
    "annotation/AR_Lick6_MN.xml": "d33974db4eb8930e31d452a8e14db14c845a2f875b5ae2e62cc35703956dd09a",
    "audio/AR_Lick6_MN.wav": "c04e7d591e17358377a54b34b590e3410ce25abb598be4b8c8e2922f54b36cd0",
    "annotation/AR_Lick12_MN.xml": "b3ca268d37114f858b415db2343f5db1ec932878f828c987d5c2a261423ff265",
    "audio/AR_Lick12_MN.wav": "79d46b455ad0454b013172c83661dec985f3abd705433d50b275968a6d2191c9",
}


class RangeArchive(io.RawIOBase):
    """Seekable view of the fixed archive; refuse unbounded/full-download replies."""

    def __init__(self):
        self.position = 0
        self.transferred = 0

    def seekable(self):
        return True

    def readable(self):
        return True

    def tell(self):
        return self.position

    def seek(self, offset, whence=0):
        if whence not in (0, 1, 2):
            raise ValueError("Invalid seek mode")
        position = (0, self.position, SIZE)[whence] + offset
        if not 0 <= position <= SIZE:
            raise ValueError("Seek outside archive")
        self.position = position
        return position

    def read(self, size=-1):
        count = SIZE - self.position if size < 0 else min(size, SIZE - self.position)
        if not count:
            return b""
        if count > 8 * 1024 * 1024 or self.transferred + count > 32 * 1024 * 1024:
            raise ValueError("Requested archive range exceeds the small-subset download budget")
        end = self.position + count - 1
        request = urllib.request.Request(URL, headers={"Range": f"bytes={self.position}-{end}"})
        with urllib.request.urlopen(request, timeout=30) as response:
            expected = f"bytes {self.position}-{end}/{SIZE}"
            if response.status != 206 or response.headers.get("Content-Range") != expected:
                raise ValueError("Server did not honor the exact byte range; full download refused")
            content = response.read(count + 1)
        if len(content) != count:
            raise ValueError("Archive range length differs from request")
        self.position += count
        self.transferred += count
        return content


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection", choices=("pieces", "licks", "muted"), default="pieces")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    subset = "dataset3" if args.selection == "pieces" else "dataset2"
    selected = {"pieces": FILES, "licks": LICK_FILES, "muted": MUTED_FILES}[args.selection]
    args.output = args.output or Path("data/idmt") / (
        "muted" if args.selection == "muted" else subset
    )
    args.output.mkdir(parents=True, exist_ok=True)
    remote = RangeArchive()
    files = []
    with zipfile.ZipFile(remote) as archive:
        for relative, expected in selected.items():
            target = args.output / relative
            content = target.read_bytes() if target.is_file() else b""
            member = archive.getinfo(f"IDMT-SMT-GUITAR_V2/{subset}/" + relative)
            if hashlib.sha256(content).hexdigest() != expected:
                if member.file_size > 8 * 1024 * 1024:
                    raise ValueError("Unexpectedly large archive member")
                content = archive.read(member)
                if hashlib.sha256(content).hexdigest() != expected:
                    raise ValueError(f"Pinned member checksum differs: {relative}")
                target.parent.mkdir(parents=True, exist_ok=True)
                with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as stream:
                    temporary = Path(stream.name)
                    stream.write(content)
                try:
                    temporary.replace(target)
                finally:
                    temporary.unlink(missing_ok=True)
            files.append({"file": relative, "bytes": len(content), "sha256": expected})
            print(f"Verified {relative}", flush=True)
    manifest = {
        "source": "https://zenodo.org/records/7544110",
        "selection": args.selection,
        "archive_url": URL,
        "license": "CC BY-NC-ND 4.0; evaluation purpose",
        "integrity": "Locally pinned selected-member SHA256; complete archive MD5 not verified",
        "transferred_bytes": remote.transferred,
        "files": files,
    }
    (args.output / "download-manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Retrieved {remote.transferred:,} bytes; complete archive not downloaded")


if __name__ == "__main__":
    main()

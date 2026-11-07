import subprocess
import sys
from pathlib import Path


def separate_guitar(path: Path, output: Path) -> Path:
    """Optional Demucs six-source model; weights download on first use."""
    subprocess.run(
        [
            sys.executable,
            "-m",
            "demucs",
            "-n",
            "htdemucs_6s",
            "--two-stems",
            "guitar",
            "-o",
            str(output),
            str(path),
        ],
        check=True,
    )
    stem = output / "htdemucs_6s" / path.stem / "guitar.wav"
    if not stem.exists():
        raise ValueError("Demucs did not produce the expected guitar stem")
    return stem

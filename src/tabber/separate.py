import os
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf


def separate_guitar(path: Path, output: Path) -> Path:
    """Optional local Demucs environment; CPU-only, weights cached in models/."""
    root = Path(__file__).resolve().parents[2]
    python = root / ".venv-separation" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not python.is_file():
        python = Path(sys.executable)
    environment = os.environ.copy()
    environment["TORCH_HOME"] = str(root / "models/torch")
    environment["OMP_NUM_THREADS"] = "4"
    audio, rate = sf.read(path, always_2d=True)
    if not len(audio) or not np.all(np.isfinite(audio)) or np.max(np.abs(audio)) < 1e-7:
        raise ValueError("Guitar separation needs nonempty, audible, finite audio")
    if audio.shape[1] != 2:
        audio = np.repeat(audio.mean(axis=1, keepdims=True), 2, axis=1)
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    # Demucs 4.0.1's mono tensor expansion aliases samples on modern PyTorch.
    # A real stereo file avoids the in-place normalization bug, and soundfile
    # also decodes supported inputs without requiring ffmpeg/ffprobe binaries.
    with tempfile.TemporaryDirectory(prefix="input-", dir=output) as directory:
        normalized = Path(directory) / (path.stem + ".wav")
        sf.write(normalized, audio, rate, subtype="FLOAT")
        del audio
        command = [
            str(python),
            "-m",
            "demucs",
            "-n",
            "htdemucs_6s",
            "--two-stems",
            "guitar",
            "--device",
            "cpu",
            "--shifts",
            "0",
            "--segment",
            "7",
            "-o",
            str(output),
            str(normalized),
        ]
        try:
            subprocess.run(command, check=True, env=environment)
        except subprocess.CalledProcessError as error:
            raise RuntimeError(
                f"Guitar separation failed (Demucs exit code {error.returncode}). "
                "Check the conversion log and the optional Demucs setup in the README. "
                "You can also turn off separation and retry with the original recording."
            ) from error
    stem = output / "htdemucs_6s" / path.stem / "guitar.wav"
    if not stem.exists():
        raise ValueError("Demucs did not produce the expected guitar stem")
    return stem

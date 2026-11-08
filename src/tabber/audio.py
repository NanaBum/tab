"""Local codec preparation and streaming input checks; no automatic gain changes."""

import importlib.util
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf


def find_ffmpeg() -> str:
    configured = os.environ.get("TABBER_FFMPEG")
    if configured:
        path = Path(configured).expanduser()
        if not path.is_file():
            raise ValueError("TABBER_FFMPEG must name an existing FFmpeg executable")
        return str(path.resolve())
    executable = shutil.which("ffmpeg")
    if executable:
        return executable
    if importlib.util.find_spec("imageio_ffmpeg") is not None:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    root = Path(__file__).resolve().parents[2]
    python = root / ".venv-audio" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if python.is_file():
        try:
            result = subprocess.run(
                [
                    str(python),
                    "-c",
                    "import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())",
                ],
                capture_output=True,
                check=False,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except subprocess.TimeoutExpired as error:
            raise ValueError("The local audio decoder did not start within 30 seconds") from error
        path = Path(result.stdout.strip())
        if result.returncode == 0 and path.is_file():
            return str(path)
    raise ValueError(
        "This audio format needs the optional local audio decoder. "
        "Set up .venv-audio from requirements/audio.in, install FFmpeg, or convert a copy to WAV."
    )


def prepare_audio(source: Path, output: Path) -> Path:
    """Use supported sources directly; decode unsupported local audio to a new WAV."""
    source = source.resolve()
    if not source.is_file():
        raise ValueError(f"Input file does not exist: {source}")
    try:
        sf.info(source)
        return source
    except sf.LibsndfileError:
        decoder = find_ffmpeg()
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        prefix="decoded-", suffix=".wav", dir=output, delete=False
    ) as f:
        target = Path(f.name)
    try:
        result = subprocess.run(
            [
                decoder,
                "-hide_banner",
                "-loglevel",
                "error",
                "-nostdin",
                "-y",
                "-protocol_whitelist",
                "file,pipe",
                "-i",
                str(source),
                "-map",
                "0:a:0",
                "-vn",
                "-c:a",
                "pcm_f32le",
                str(target),
            ],
            capture_output=True,
            check=False,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode:
            raise ValueError("Could not decode this audio file: " + result.stderr.strip()[-1200:])
        sf.info(target)
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    return target


def inspect_audio(path: Path) -> dict:
    """Measure all samples in bounded blocks and flag heuristic input concerns."""
    peak, energy, mono_energy, sample_count, near_full_scale = 0.0, 0.0, 0.0, 0, 0
    with sf.SoundFile(path) as stream:
        frames, channels, rate = len(stream), stream.channels, stream.samplerate
        if not frames:
            raise ValueError("Recording contains no audio samples")
        for block in stream.blocks(blocksize=65536, dtype="float64", always_2d=True):
            if not np.all(np.isfinite(block)):
                raise ValueError("Audio contains non-finite samples")
            peak = max(peak, float(np.max(np.abs(block))))
            energy += float(np.sum(block**2))
            mono_energy += float(np.sum(block.mean(axis=1) ** 2))
            sample_count += block.size
            near_full_scale += int(np.sum(np.abs(block) >= 0.999))
    rms = (energy / sample_count) ** 0.5
    mono_rms = (mono_energy / frames) ** 0.5
    warnings = []
    if peak < 0.01:
        warnings.append(
            "Recording level is very low. Check the recording input, level and playback."
        )
    if near_full_scale / sample_count > 0.001:
        warnings.append("Many samples reach full scale. Check the recording for clipping.")
    if channels > 1 and rms > 0 and mono_rms < rms * 0.1:
        warnings.append(
            "Combining stereo channels greatly reduces the level. Review the input channels."
        )
    return {
        "seconds": frames / rate,
        "sample_rate": rate,
        "channels": channels,
        "peak": peak,
        "rms": rms,
        "mono_rms": mono_rms,
        "samples_at_or_above_0_999": near_full_scale,
        "sample_count": sample_count,
        "warnings": warnings,
        "policy": "Heuristic input checks only; no gain, denoising, trimming or pitch changes",
    }

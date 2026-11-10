"""Optional published GAPS guitar model; CPU inference with pinned local weights.

Uses Riley's pinned fork of Kong's transcription architecture and postprocessor.
Torch and the model package are imported only when this backend is requested.
"""

import hashlib
import math
from functools import lru_cache
from pathlib import Path

import numpy as np

from .models import Note

CHECKPOINT_NAME = "guitar-gaps-paper-version-12200_iterations.pth"
CHECKPOINT_SHA256 = "94a7c936ec9fde83686d29007dc256274384e832739cadece39e92cee3b69a7e"
RELEASE_V1_SHA256 = "b89cf4dba3e18b26a867c62353329dc6f6e7c316a798d4f69159d32a5c938185"
MODEL_REVISION = "b7bec65a2b860aca72856b0feef58b5df407b777"
MODEL_REPOSITORY = "xavriley/midi-transcription-models"


def default_checkpoint() -> Path:
    return Path(__file__).resolve().parents[2] / "models/guitar-gaps" / CHECKPOINT_NAME


def release_v1_checkpoint() -> Path:
    return default_checkpoint().parents[1] / "guitar-offset-projection-v1" / "reg_offset_fc.pt"


def checkpoint_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _stitch_segments(values: np.ndarray) -> np.ndarray:
    """Join half-overlapped windows using the upstream quarter-window policy."""
    if values.ndim != 3 or values.shape[0] < 1:
        raise ValueError("Expected nonempty segment/frame/pitch activations")
    if len(values) == 1:
        return values[0]
    # Centered analysis adds one endpoint frame; remove it before slicing.
    values = values[:, :-1]
    frames = values.shape[1]
    if frames % 4:
        raise ValueError("Segment frames must support quarter-window stitching")
    quarter = frames // 4
    return np.concatenate(
        [
            values[0, : 3 * quarter],
            *[window[quarter : 3 * quarter] for window in values[1:-1]],
            values[-1, quarter:],
        ]
    )


def _make_segments(audio: np.ndarray, segment_samples: int = 160000) -> np.ndarray:
    if audio.ndim != 1 or not len(audio) or not np.all(np.isfinite(audio)):
        raise ValueError("Guitar model needs nonempty finite mono audio")
    padding = math.ceil(len(audio) / segment_samples) * segment_samples - len(audio)
    padded = np.pad(audio, (0, padding))
    return np.stack(
        [
            padded[i : i + segment_samples]
            for i in range(0, len(padded) - segment_samples + 1, segment_samples // 2)
        ]
    )


@lru_cache(maxsize=2)
def _load_model(checkpoint: Path, release_checkpoint: Path | None = None):
    if not checkpoint.is_file():
        raise ValueError("Guitar model weights are missing; run scripts/download_guitar_model.py")
    if checkpoint_digest(checkpoint) != CHECKPOINT_SHA256:
        raise ValueError(
            "Guitar model checkpoint checksum does not match the pinned published weights"
        )
    if release_checkpoint is not None:
        if not release_checkpoint.is_file():
            raise ValueError("The optional local guitar release weights are missing")
        if checkpoint_digest(release_checkpoint) != RELEASE_V1_SHA256:
            raise ValueError(
                "Guitar release checkpoint checksum does not match the verified weights"
            )
    try:
        import torch
        from piano_transcription_inference.models import Regress_onset_offset_frame_velocity_CRNN
    except ImportError as error:
        raise ValueError(
            "Set up the separate .venv-guitar environment from requirements/guitar.in"
        ) from error
    torch.set_num_threads(4)
    # The verified author checkpoint also contains numeric NumPy sampler state.
    # Retain weights_only loading with a scoped list of known numeric constructors.
    numeric_numpy = [
        np.core.multiarray._reconstruct,
        np.ndarray,
        np.dtype,
        *[
            type(np.dtype(t))
            for t in (np.float32, np.float64, np.int32, np.int64, np.uint32, np.uint64, np.uint8)
        ],
    ]
    with torch.serialization.safe_globals(numeric_numpy):
        checkpoint_data = torch.load(checkpoint, map_location="cpu", weights_only=True)
    model = Regress_onset_offset_frame_velocity_CRNN(frames_per_second=100, classes_num=88)
    model.load_state_dict(checkpoint_data["model"], strict=True)
    if release_checkpoint is not None:
        state = torch.load(release_checkpoint, map_location="cpu", weights_only=True)
        model.reg_offset_model.fc.load_state_dict(state, strict=True)
    model.eval()
    return model


def gaps_activations(
    path: Path, *, checkpoint: Path | None = None, input_gain: float = 1.0, release_v1=False
):
    """Run the frozen network once for one or more decoder comparisons."""
    if not math.isfinite(input_gain) or not 0 < input_gain <= 1:
        raise ValueError("Guitar-model input gain must be above zero and at most one")
    original = (checkpoint or default_checkpoint()).resolve()
    model = (
        _load_model(original, release_v1_checkpoint().resolve())
        if release_v1
        else _load_model(original)
    )
    import librosa
    from piano_transcription_inference.pytorch_utils import forward

    audio, rate = librosa.load(str(path), sr=16000, mono=True)
    duration = len(audio) / rate
    if input_gain != 1:
        audio = audio * input_gain
    segments = _make_segments(audio)
    output = forward(model, segments, batch_size=1)
    # Upstream's crop uses sample count against frame arrays. Crop in frame units
    # before decoding, so padded silence cannot create out-of-recording events.
    valid_frames = math.ceil(duration * 100)
    output = {key: _stitch_segments(value)[:valid_frames] for key, value in output.items()}
    if any(not np.all(np.isfinite(value)) for value in output.values()):
        raise ValueError("Guitar model produced non-finite activations")
    return output, duration


def _validate_onset_threshold(onset_threshold):
    if not math.isfinite(onset_threshold) or not 0 < onset_threshold <= 1:
        raise ValueError("Guitar-model onset threshold must be above zero and at most one")


def decode_gaps(output, duration, *, onset_threshold=0.3) -> list[Note]:
    """Decode one threshold without changing the stored network outputs."""
    _validate_onset_threshold(onset_threshold)
    from piano_transcription_inference.utilities import RegressionPostProcessor

    processor = RegressionPostProcessor(100, 88, onset_threshold, 0.3, 0.1, 0.2)
    events, _ = processor.output_dict_to_midi_events(dict(output))
    valid_frames = len(output["reg_onset_output"])
    notes = []
    for event in events:
        start, end, pitch = (
            float(event["onset_time"]),
            float(event["offset_time"]),
            int(event["midi_note"]),
        )
        if start < 0 or end > duration or end <= start:
            raise ValueError("Guitar model produced an event outside valid recording time")
        frame = min(round(start * 100), valid_frames - 1)
        activation = float(
            output["reg_onset_output"][max(0, frame - 2) : frame + 3, pitch - 21].max()
        )
        # This is an onset regression activation, not a calibrated probability.
        # All decoded events are retained; no Basic Pitch confidence filter applies.
        notes.append(Note(start, end, pitch, float(np.clip(activation, 0, 1))))
    return sorted(notes, key=lambda note: note.start)


def transcribe_gaps(
    path: Path,
    *,
    checkpoint: Path | None = None,
    onset_threshold: float = 0.3,
    input_gain: float = 1.0,
    release_v1=False,
) -> list[Note]:
    _validate_onset_threshold(onset_threshold)
    output, duration = gaps_activations(
        path, checkpoint=checkpoint, input_gain=input_gain, release_v1=release_v1
    )
    return decode_gaps(output, duration, onset_threshold=onset_threshold)

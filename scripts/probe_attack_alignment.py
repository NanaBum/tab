"""Check a score-to-audio clock against pitch-specific attack evidence."""

import argparse
import json
import math
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.ndimage import gaussian_filter1d

from tabber.events import load_events
from tabber.media import sha256_file

SAMPLE_RATE = 22050
HOP = 128
STEP = HOP / SAMPLE_RATE
LOW_PITCH = 36
PITCH_BINS = 72
CONTROLS = (-0.8, -0.6, -0.4, 0.4, 0.6, 0.8)


def pitch_flux(path):
    import librosa

    audio, rate = sf.read(path, always_2d=True)
    if not audio.size or not np.isfinite(audio).all():
        raise ValueError("Audio must contain finite samples")
    mono = librosa.resample(audio.mean(axis=1), orig_sr=rate, target_sr=SAMPLE_RATE)
    magnitude = abs(
        librosa.cqt(
            mono,
            sr=SAMPLE_RATE,
            hop_length=HOP,
            fmin=librosa.midi_to_hz(LOW_PITCH),
            n_bins=PITCH_BINS,
        )
    )
    log_magnitude = np.log1p(magnitude / max(1e-8, np.percentile(magnitude, 60)))
    flux = np.maximum(0, np.diff(log_magnitude, axis=1, prepend=log_magnitude[:, :1]))
    flux = gaussian_filter1d(flux, 2, axis=1)
    flux /= np.maximum(np.percentile(flux, 90, axis=1, keepdims=True), 1e-6)
    return np.minimum(flux, 6), len(audio) / rate


def assess_windows(flux, attacks, windows, *, coarse, duration, scale=1.0):
    """Fit on the first window and apply that estimate to all later windows."""
    if not math.isfinite(coarse):
        raise ValueError("The coarse shift must be finite")
    if not math.isfinite(scale) or scale <= 0:
        raise ValueError("The score scale must be finite and positive")
    scaled_attacks = [(time * scale, pitch) for time, pitch in attacks]
    shifts = coarse + np.arange(-43, 44) * STEP
    rows = []
    calibrated_index = None
    offsets = np.r_[shifts, coarse + np.asarray(CONTROLS)]
    previous_end = 0.0
    for lo, hi in windows:
        if not (max(0.8, previous_end) <= lo < hi <= duration - 0.8):
            raise ValueError("Use ordered, disjoint windows at least 0.8s inside the audio")
        previous_end = hi
        in_window = [(t, p) for t, p in scaled_attacks if lo <= t + coarse < hi]
        anchors = [(t, p) for t, p in in_window if LOW_PITCH <= p < LOW_PITCH + len(flux)]
        if len(anchors) < 10:
            raise ValueError(f"Window {lo:g}–{hi:g}s needs at least ten in-range candidate attacks")
        times, pitches = map(np.asarray, zip(*anchors))
        pitch_indices = pitches - LOW_PITCH

        frames = np.rint((times + offsets[:, None]) / STEP).astype(int)
        if frames.min() < 0 or frames.max() >= flux.shape[1]:
            raise ValueError("Audio features do not cover the requested window")
        energies = flux[pitch_indices, frames].mean(axis=1)
        curve, controls = energies[: len(shifts)], energies[len(shifts) :]
        best_index = max(
            range(len(shifts)),
            key=lambda index: (curve[index], -abs(shifts[index] - coarse)),
        )
        best = float(shifts[best_index])
        if calibrated_index is None:
            calibrated_index = best_index
        rows.append(
            {
                "window_seconds": [lo, hi],
                "candidate_pitch_attacks": len(anchors),
                "out_of_range_attacks": len(in_window) - len(anchors),
                "local_best_shift_seconds": round(best, 4),
                "local_best_on_search_edge": best_index in (0, len(shifts) - 1),
                "coarse_flux": round(float(curve[43]), 4),
                "calibrated_flux": round(float(curve[calibrated_index]), 4),
                "control_mean_flux": round(float(np.mean(controls)), 4),
                "control_max_flux": round(float(controls.max()), 4),
                "local_best_flux": round(float(curve[best_index]), 4),
            }
        )
    return {"calibrated_shift_seconds": round(float(shifts[calibrated_index]), 4), "windows": rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audio", type=Path, help="Audio with the original recording's time zero")
    parser.add_argument("--reference", type=Path, action="append", required=True)
    parser.add_argument("--coarse-shift", type=float, required=True)
    parser.add_argument(
        "--score-scale", type=float, default=1, help="Multiply score times before adding the shift"
    )
    parser.add_argument("--window", type=float, nargs=2, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if len(args.window) < 2:
            raise ValueError("Supply at least one calibration and one later check window")
        references, attacks, pairs = [], set(), set()
        for path in args.reference:
            metadata = json.loads(path.read_text(encoding="utf-8-sig"))["metadata"]
            pairs.add(metadata["source_pair_sha256"])
            references.append(
                {"sha256": sha256_file(path), "score_track": metadata.get("score_track")}
            )
            attacks.update((round(n.start, 8), n.pitch) for n in load_events(path))
        if len(pairs) != 1:
            raise ValueError("Reference tracks must come from one source pair")
        flux, duration = pitch_flux(args.audio)
        result = assess_windows(
            flux,
            sorted(attacks),
            args.window,
            coarse=args.coarse_shift,
            duration=duration,
            scale=args.score_scale,
        )
        result.update(
            audio_sha256=sha256_file(args.audio),
            source_pair_sha256=pairs.pop(),
            references=references,
            coarse_score_shift_seconds=args.coarse_shift,
            score_scale=args.score_scale,
            mapping="recording_time = score_time * score_scale + shift",
            score_shift_grid_step_seconds=STEP,
            control_offsets_from_coarse_seconds=CONTROLS,
            limits=(
                "Positive log constant-Q energy changes at exact score pitch. "
                "The first window fits the offset and later windows check it on the same recording. "
                "Other parts and harmonics can contribute. This report does not approve labels."
            ),
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, indent=2)
            stream.write("\n")
    except (ImportError, OSError, ValueError, TypeError, KeyError) as error:
        parser.exit(1, f"Could not check attack alignment: {error}\n")
    print(f"Checked {len(result['windows'])} windows: {args.output.resolve()}")


if __name__ == "__main__":
    main()

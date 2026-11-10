"""Evaluate saved string-timbre priors on annotated electric guitar without fitting."""

import argparse
import itertools
import json
from pathlib import Path

import numpy as np
import soundfile as sf
from sweep_guitar_onsets import SELECTION

from tabber.evaluation import idmt_recording
from tabber.fretting import assign_frets, assign_polyphonic_frets
from tabber.media import sha256_file
from tabber.models import STANDARD_TUNING
from tabber.string_model import StringModel, audio_features, isolated_features


def evaluate_track(wav, annotation, model):
    reference = idmt_recording(annotation.read_text(encoding="utf-8-sig"))
    notes = reference.notes
    audio, rate = sf.read(wav, always_2d=True)
    waveform, mfcc = audio_features(audio, rate)
    features = isolated_features(waveform, mfcc, notes)
    indices = [i for i, feature in enumerate(features) if feature is not None]
    pitches = [notes[i].pitch for i in indices]
    timbre = np.asarray([features[i] for i in indices]).reshape(-1, 39)
    predictions = {
        "pitch_component": model.predict(pitches, np.broadcast_to(model.mean[-39:], timbre.shape)),
        "pitch_and_timbre": model.predict(pitches, timbre),
    }
    labeled = [i for i in indices if reference.positions[i] is not None]
    ambiguous = {
        i
        for i in labeled
        if sum(0 <= notes[i].pitch - tuning <= 24 for tuning in STANDARD_TUNING) > 1
    }
    labeled_rows = [j for j, i in enumerate(indices) if i in ambiguous]
    string_scores = {
        name: sum(
            int(np.argmax(probs[j])) == reference.positions[indices[j]][0] for j in labeled_rows
        )
        for name, probs in predictions.items()
    }
    ordered = sorted(notes, key=lambda n: n.start)
    polyphonic = any(b.start < a.end - 1e-6 for a, b in itertools.pairwise(ordered))
    solver = assign_polyphonic_frets if polyphonic else assign_frets
    position_scores = {}
    valid = [i for i, position in enumerate(reference.positions) if position is not None]
    configs = {"ergonomic": None}
    for name, probs in predictions.items():
        priors = np.full((len(notes), 6), 1 / 6)
        priors[indices] = probs
        configs[name] = priors
    for name, priors in configs.items():
        try:
            assigned = {id(n.note): (n.string, n.fret) for n in solver(notes, string_priors=priors)}
        except ValueError as error:
            position_scores[name] = {"error": str(error)}
            continue
        position_scores[name] = {
            "all_consistent_correct": sum(
                assigned[id(notes[i])] == reference.positions[i] for i in valid
            ),
            "ambiguous_isolated_correct": sum(
                assigned[id(notes[i])] == reference.positions[i] for i in ambiguous
            ),
        }
    return {
        "audio_sha256": sha256_file(wav),
        "annotation_sha256": sha256_file(annotation),
        "notes": len(notes),
        "consistent_positions": len(valid),
        "features": len(indices),
        "isolated_labeled_positions": len(labeled),
        "ambiguous_isolated_positions": len(ambiguous),
        "string_correct": string_scores,
        "solver": "polyphonic" if polyphonic else "melodic",
        "positions": position_scores,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--weights", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        model = StringModel(args.weights)
        rows = []
        for group, names in SELECTION.items():
            for name in names:
                root = args.data / group
                row = evaluate_track(
                    root / "audio" / f"{name}.wav", root / "annotation" / f"{name}.xml", model
                )
                rows.append({"group": group, "track": name, **row})
                print(
                    f"{name}: {row['ambiguous_isolated_positions']} ambiguous labeled windows",
                    flush=True,
                )
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump(
                {
                    "weights_sha256": sha256_file(args.weights),
                    "tracks": rows,
                    "limits": "Oracle pitch, onset and duration. Pitch component uses zero standardized timbre features in the same frozen model. No fitting or tuning. The selection is small and does not measure full-band accuracy.",
                },
                stream,
                indent=2,
            )
            stream.write("\n")
    except (OSError, KeyError, TypeError, ValueError) as error:
        parser.exit(1, f"Could not evaluate electric string priors: {error}\n")


if __name__ == "__main__":
    main()

"""Measure missed and extra attacks while re-decoding one frozen guitar model."""

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from tabber.evaluation import idmt_recording, score_notes
from tabber.guitar_gaps import decode_gaps, gaps_activations
from tabber.media import sha256_file

SELECTION = {
    "dataset3": (
        "nocturneNr2",
        "pathetique_mono",
        "pathetique_poly",
        "promenade_mono",
        "quintfall",
    ),
    "dataset2": ("AR_Lick1_KN", "AR_Lick6_KN", "AR_Lick12_KN"),
    "muted": ("AR_Lick1_MN", "AR_Lick6_MN", "AR_Lick12_MN"),
}
THRESHOLDS = (0.18, 0.24, 0.30, 0.36, 0.42)


def compare(data):
    rows = []
    for group, names in SELECTION.items():
        for name in names:
            wav = data / group / "audio" / f"{name}.wav"
            xml = data / group / "annotation" / f"{name}.xml"
            ref = idmt_recording(xml.read_text(encoding="utf-8-sig")).notes
            output, duration = gaps_activations(wav)
            scores = {}
            for threshold in THRESHOLDS:
                notes = decode_gaps(output, duration, onset_threshold=threshold)
                score = score_notes(ref, notes)
                scores[str(threshold)] = {
                    **asdict(score),
                    "missed": score.reference_notes - score.matched_notes,
                    "extra": score.predicted_notes - score.matched_notes,
                }
            rows.append(
                {
                    "track": name,
                    "group": group,
                    "audio_sha256": sha256_file(wav),
                    "reference_sha256": sha256_file(xml),
                    "scores": scores,
                }
            )
            print(f"Scored {name}", flush=True)
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("data/idmt"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Choose a fresh output file")
    rows = compare(args.data)
    report = {
        "purpose": "Fixed IDMT development set; compare attacks across guitar-model thresholds",
        "thresholds": THRESHOLDS,
        "onset_tolerance_seconds": 0.05,
        "limits": "Training overlap for the pretrained model is unresolved. Extra and missed are relative to the supplied annotations.",
        "tracks": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")


if __name__ == "__main__":
    main()

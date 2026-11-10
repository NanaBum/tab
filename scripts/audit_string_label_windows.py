"""Find score-isolated string/fret candidates in verified aligned excerpts."""

import argparse
import json
from collections import Counter
from pathlib import Path

from evaluate_onset_excerpts import load_partition
from prepare_training_excerpts import read_json, verify_row

from tabber.media import sha256_file
from tabber.models import STANDARD_TUNING, Note
from tabber.string_model import tone_window


def positioned_track(path, original_hash):
    if sha256_file(path) != original_hash:
        raise ValueError(f"Original score events failed verification: {path.name}")
    sidecar = path.with_name(f"{path.stem}-positions.json")
    plain, enriched = read_json(path), read_json(sidecar)
    old, new = plain["metadata"], enriched["metadata"]
    for key in ("source_pair_sha256", "source_file_sha256", "score_track"):
        if old[key] != new[key]:
            raise ValueError(f"Position file does not match the original score: {sidecar.name}")
    ticks = new["playback_notes"]
    if (
        enriched["notes"] != plain["notes"]
        or [{k: v for k, v in tick.items() if k != "source_position"} for tick in ticks]
        != old["playback_notes"]
    ):
        raise ValueError(f"Position file changed the playback events: {sidecar.name}")
    tuning = new["score_track"]["tunings"]
    notes = [
        (Note(**event), tick["source_position"], tuning)
        for event, tick in zip(enriched["notes"], ticks, strict=True)
    ]
    return notes, sha256_file(sidecar)


def eligible(position, tunings, pitch):
    if not position or position["pitch_effect"] or position["dead_note"]:
        return False
    staff, string, fret = (position[key] for key in ("staff", "string", "fret"))
    return (
        0 <= staff < len(tunings)
        and tuple(tunings[staff]) == STANDARD_TUNING
        and position["capo"] == 0
        and 0 <= string < len(STANDARD_TUNING)
        and 0 <= fret <= 24
        and position["pitch_consistent"]
        and STANDARD_TUNING[string] == position["open_pitch_with_capo"]
        and STANDARD_TUNING[string] + fret == pitch
    )


def audit_clip(sources, row):
    start = row["source_start_frame"] / row["sample_rate"]
    duration = row["frames"] / row["sample_rate"]
    scale, shift = row["score_scale"], row["score_shift_seconds"] - start
    spans = [(n.start * scale + shift, n.end * scale + shift) for n, _, _ in sources]
    active = [i for i, (a, b) in enumerate(spans) if a < duration and b > 0]
    counts = Counter()
    candidates = []
    for i in active:
        onset, end = spans[i]
        if onset < 0:
            continue
        note, position, tunings = sources[i]
        if not eligible(position, tunings, note.pitch):
            counts["no_supported_position"] += 1
            continue
        clip_note = Note(onset, min(end, duration), note.pitch)
        window = tone_window(clip_note)
        if window is None:
            counts["outside_feature_window"] += 1
            continue
        lo, hi = window
        if any(j != i and spans[j][0] < hi and spans[j][1] > lo for j in active):
            counts["score_overlap"] += 1
            continue
        counts["candidate"] += 1
        candidates.append(
            {
                "start": clip_note.start,
                "end": clip_note.end,
                "pitch": clip_note.pitch,
                "string": position["string"],
                "fret": position["fret"],
            }
        )
    return counts, candidates


def audit(plan, manifest, root, output):
    package = read_json(manifest)
    if package["plan_sha256"] != sha256_file(plan):
        raise ValueError("The excerpt manifest was built from a different plan")
    rows = package["excerpts"]
    for split in {row["split"] for row in rows}:
        load_partition(manifest, split)
    totals, excerpts = {}, []
    iterator = iter(rows)
    for planned in read_json(plan)["rows"]:
        _, _, provenance = verify_row(planned, root)
        labels = (root / planned["pair"]).parent.parent / "labels"
        sources, hashes = [], []
        for track, digest in zip(
            provenance["score_track_numbers"], provenance["score_track_sha256"], strict=True
        ):
            notes, position_hash = positioned_track(labels / f"gp7-track-{track}.json", digest)
            sources.extend(notes)
            hashes.append(position_hash)
        for first, last in planned["windows"]:
            row = next(iterator, None)
            if (
                row is None
                or row["song_id"] != planned["song_id"]
                or row["split"] != planned["split"]
                or any(row[key] != value for key, value in provenance.items())
                or row["source_start_frame"] != round(first * row["sample_rate"])
                or row["frames"] != round(last * row["sample_rate"]) - row["source_start_frame"]
            ):
                raise ValueError("Excerpt does not match its planned source and window")
            counts, candidates = audit_clip(sources, row)
            totals.setdefault(row["split"], Counter()).update(counts)
            excerpts.append(
                {
                    "song_id": row["song_id"],
                    "split": row["split"],
                    "audio_sha256": row["audio_sha256"],
                    "positions_sha256": hashes,
                    "counts": counts,
                    "candidates": candidates,
                }
            )
    if next(iterator, None) is not None:
        raise ValueError("Excerpt manifest contains unplanned rows")
    with output.open("x", encoding="utf-8") as stream:
        json.dump(
            {
                "manifest_sha256": sha256_file(manifest),
                "totals": totals,
                "excerpts": excerpts,
                "limits": "Weak written positions and score-only isolation. Actual audio may contain other instruments, omitted guitar parts, or different timing and fingering.",
            },
            stream,
            indent=2,
        )
        stream.write("\n")
    return totals


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(audit(args.plan, args.manifest, args.root, args.output)))
    except (OSError, KeyError, TypeError, ValueError) as error:
        parser.exit(1, f"Could not audit string label windows: {error}\n")


if __name__ == "__main__":
    main()

"""Compare ordered single-note examples when reference timing is unavailable.

This is sequence edit distance, not a replacement for timed note-event metrics.
Pitch alignment never uses the reference fingering to choose between ties.
"""

from .models import STANDARD_TUNING


def validate_positions(positions: list[dict]) -> list[dict]:
    if not isinstance(positions, list):
        raise TypeError("Positions must be a list of string/fret objects")
    result = []
    for index, position in enumerate(positions, 1):
        if not isinstance(position, dict):
            raise TypeError(f"Position {index} must be a string/fret object")
        string, fret = position.get("string"), position.get("fret")
        if (
            type(string) is not int
            or not 0 <= string < 6
            or type(fret) is not int
            or not 0 <= fret <= 24
        ):
            raise ValueError(f"Position {index} needs string 0-5 (high E first) and fret 0-24")
        pitch = STANDARD_TUNING[string] + fret
        if "pitch" in position and position["pitch"] != pitch:
            raise ValueError(f"Position {index} pitch disagrees with standard tuning")
        result.append({"string": string, "fret": fret, "pitch": pitch})
    return result


def compare_sequences(reference: list[dict], predicted: list[dict]) -> dict:
    """Minimize substitutions + missing + extra; break cost ties by pitch matches."""
    reference, predicted = validate_positions(reference), validate_positions(predicted)
    rows, columns = len(reference), len(predicted)
    if (rows + 1) * (columns + 1) > 1_000_000:
        raise ValueError("Sequence check is for short examples; split this into smaller phrases")
    # Entries are (edit count, negative exact-pitch matches). No timing/fret cost.
    costs = [[(0, 0)] * (columns + 1) for _ in range(rows + 1)]
    parents = [[None] * (columns + 1) for _ in range(rows + 1)]
    ways = [[0] * (columns + 1) for _ in range(rows + 1)]
    ways[0][0] = 1
    for i in range(1, rows + 1):
        costs[i][0], parents[i][0] = (i, 0), "missing"
        ways[i][0] = 1
    for j in range(1, columns + 1):
        costs[0][j], parents[0][j] = (j, 0), "extra"
        ways[0][j] = 1
    for i in range(1, rows + 1):
        for j in range(1, columns + 1):
            match = reference[i - 1]["pitch"] == predicted[j - 1]["pitch"]
            diagonal, missing, extra = costs[i - 1][j - 1], costs[i - 1][j], costs[i][j - 1]
            candidates = [
                (
                    (diagonal[0] + (not match), diagonal[1] - match),
                    "match" if match else "wrong_pitch",
                ),
                ((missing[0] + 1, missing[1]), "missing"),
                ((extra[0] + 1, extra[1]), "extra"),
            ]
            costs[i][j], parents[i][j] = min(candidates, key=lambda item: item[0])
            ways[i][j] = min(
                2,
                sum(
                    count
                    for (key, _), count in zip(
                        candidates, (ways[i - 1][j - 1], ways[i - 1][j], ways[i][j - 1])
                    )
                    if key == costs[i][j]
                ),
            )
    i, j, alignment = rows, columns, []
    while i or j:
        operation = parents[i][j]
        expected_index = i - 1 if operation != "extra" else None
        predicted_index = j - 1 if operation != "missing" else None
        entry = {
            "operation": operation,
            "reference_index": expected_index,
            "predicted_index": predicted_index,
        }
        if expected_index is not None:
            entry["reference"] = reference[expected_index]
            i -= 1
        if predicted_index is not None:
            entry["predicted"] = predicted[predicted_index]
            j -= 1
        alignment.append(entry)
    alignment.reverse()
    matches = [a for a in alignment if a["operation"] == "match"]
    correct_positions = sum(
        (a["reference"]["string"], a["reference"]["fret"])
        == (a["predicted"]["string"], a["predicted"]["fret"])
        for a in matches
    )
    distance = costs[rows][columns][0]
    return {
        "purpose": "Ordered single-note check; no reference timing or chord alignment",
        "reference_notes": rows,
        "predicted_notes": columns,
        "pitch_edit_distance": distance,
        "pitch_alignment_ambiguous": ways[rows][columns] > 1,
        "normalized_pitch_edit_distance": distance / max(rows, columns) if rows or columns else 0,
        "exact_pitch_matches": len(matches),
        "wrong_pitch": sum(a["operation"] == "wrong_pitch" for a in alignment),
        "missing": sum(a["operation"] == "missing" for a in alignment),
        "extra": sum(a["operation"] == "extra" for a in alignment),
        "reference_fingering_among_pitch_matches": {
            "correct": correct_positions,
            "compared": len(matches),
            "agreement": correct_positions / len(matches) if matches else None,
        },
        "alignment": alignment,
        "limits": "Repeated pitches may admit ambiguous alignments; alternate fingerings may sound correct. No rhythm score.",
    }

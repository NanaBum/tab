import pytest

from tabber.sequence import compare_sequences, validate_positions


def positions(frets):
    return [{"string": 0, "fret": f} for f in frets]


def test_sequence_comparison_reports_each_kind_of_pitch_error():
    report = compare_sequences(positions([0, 2, 4, 5]), positions([0, 2, 3, 5, 7]))
    assert report["pitch_edit_distance"] == 2
    assert report["exact_pitch_matches"] == 3
    assert (report["wrong_pitch"], report["missing"], report["extra"]) == (1, 0, 1)
    assert report["normalized_pitch_edit_distance"] == 0.4


def test_sequence_detects_missing_notes_and_keeps_repeated_attacks():
    report = compare_sequences(positions([0, 0, 2, 4]), positions([0, 2, 4]))
    assert report["pitch_edit_distance"] == report["missing"] == 1
    assert report["exact_pitch_matches"] == 3
    assert report["pitch_alignment_ambiguous"]


def test_same_pitch_on_another_string_is_a_pitch_match_but_different_fingering():
    report = compare_sequences(positions([0]), [{"string": 1, "fret": 5}])
    assert report["pitch_edit_distance"] == 0
    assert report["reference_fingering_among_pitch_matches"] == {
        "correct": 0,
        "compared": 1,
        "agreement": 0,
    }


def test_empty_sequences_do_not_invent_conditional_fingering_accuracy():
    assert compare_sequences([], [])["normalized_pitch_edit_distance"] == 0
    report = compare_sequences(positions([0]), [])
    assert report["missing"] == 1
    assert report["reference_fingering_among_pitch_matches"]["agreement"] is None
    assert compare_sequences([], positions([0]))["extra"] == 1


def test_pitch_alignment_does_not_choose_ties_to_improve_reference_fingering():
    reference = [{"string": 0, "fret": 0}, {"string": 1, "fret": 5}]
    first = compare_sequences(reference, [{"string": 0, "fret": 0}])
    second = compare_sequences(reference, [{"string": 1, "fret": 5}])
    assert first["pitch_alignment_ambiguous"] and second["pitch_alignment_ambiguous"]
    assert [a["reference_index"] for a in first["alignment"]] == [
        a["reference_index"] for a in second["alignment"]
    ]


def test_sequence_cli_compares_saved_result_without_changing_it(tmp_path, monkeypatch):
    import json

    from scripts.compare_reference_sequence import main
    from tabber.export import write_outputs
    from tabber.models import FrettedNote, Note

    reference = tmp_path / "reference.json"
    reference.write_text(json.dumps(positions([0, 2, 4])), encoding="utf-8")
    output = tmp_path / "export"
    write_outputs(
        [FrettedNote(Note(i, i + 0.5, 64 + fret), 0, fret) for i, fret in enumerate([0, 3, 4])],
        output,
        120,
    )
    predicted = output / "notes.json"
    before = predicted.read_bytes()
    report_path = tmp_path / "comparison.json"
    monkeypatch.setattr(
        "sys.argv", ["compare", str(reference), str(predicted), "--output", str(report_path)]
    )
    main()
    report = json.loads(report_path.read_text())
    assert report["wrong_pitch"] == report["pitch_edit_distance"] == 1
    assert report["exact_pitch_matches"] == 2
    assert predicted.read_bytes() == before


@pytest.mark.parametrize(
    "bad",
    [
        [{"string": True, "fret": 0}],
        [{"string": 6, "fret": 0}],
        [{"string": 0, "fret": -1}],
        [{"string": 0, "fret": 0, "pitch": 65}],
    ],
)
def test_reference_positions_require_unambiguous_valid_standard_tuning(bad):
    with pytest.raises(ValueError):
        validate_positions(bad)

from scripts.audit_fretting_constraints import exact_feasibility
from tabber.models import Note


def test_constraint_audit_accepts_a_playable_open_c_chord():
    notes = [Note(0, 1, pitch) for pitch in (48, 52, 55, 60, 64)]
    assert exact_feasibility(notes, span=2, time_limit=2)["status"] == 0


def test_constraint_audit_rejects_two_sustained_notes_that_both_require_low_e():
    notes = [Note(0, 1, 40), Note(0.5, 1.5, 41)]
    assert exact_feasibility(notes, span=24, time_limit=2)["status"] == 2

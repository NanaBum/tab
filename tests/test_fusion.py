from tabber.fusion import complementary_notes
from tabber.models import Note


def test_complementary_notes_pair_repetitions_one_to_one_and_keep_primary_timing():
    primary = [Note(0.1, 0.3, 60), Note(0.18, 0.4, 60)]
    secondary = [Note(0.11, 0.5, 60), Note(0.16, 0.5, 64), Note(0.5, 0.6, 60)]
    assert complementary_notes(primary, secondary) == [
        (primary[0], 0, 0),
        (secondary[1], None, 1),
        (primary[1], 1, None),
        (secondary[2], None, 2),
    ]

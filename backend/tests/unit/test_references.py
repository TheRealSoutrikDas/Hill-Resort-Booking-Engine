import random
import re

from app.db.models.booking import BOOKING_REFERENCE_ALPHABET
from app.services.references import (
    generate_booking_reference,
    is_valid_booking_reference,
    normalize_booking_reference,
)


def test_alphabet_excludes_easily_confused_characters() -> None:
    assert len(BOOKING_REFERENCE_ALPHABET) == 31
    assert not set("ILO01") & set(BOOKING_REFERENCE_ALPHABET)


def test_generated_reference_has_the_expected_format() -> None:
    for _ in range(200):
        reference = generate_booking_reference()
        assert re.fullmatch(r"BK-[A-Z2-9]{8}", reference)
        assert is_valid_booking_reference(reference)


def test_seeded_rng_gives_the_same_references_every_run() -> None:
    first = [generate_booking_reference(random.Random(42)) for _ in range(3)]
    second = [generate_booking_reference(random.Random(42)) for _ in range(3)]
    assert first == second


def test_secure_references_do_not_repeat_in_practice() -> None:
    references = {generate_booking_reference() for _ in range(10_000)}
    assert len(references) == 10_000


def test_lookup_input_is_normalized_before_validation() -> None:
    assert normalize_booking_reference("  bk-7f3k9qxm ") == "BK-7F3K9QXM"
    assert is_valid_booking_reference(normalize_booking_reference("  bk-7f3k9qxm "))


def test_invalid_references_are_rejected() -> None:
    for value in ["", "BK-7F3K9QX", "BK-7F3K9QXM1", "BK-7F3K9QX0", "XX-7F3K9QXM", "7F3K9QXM"]:
        assert not is_valid_booking_reference(value)

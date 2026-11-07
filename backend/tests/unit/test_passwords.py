from argon2 import PasswordHasher

from app.services import passwords


def test_hash_and_verify() -> None:
    stored = passwords.hash_password("correct horse battery")
    assert stored.startswith("$argon2id$")
    assert passwords.verify_password(stored, "correct horse battery")
    assert not passwords.verify_password(stored, "correct horse battery!")


def test_same_password_hashes_differently_each_time() -> None:
    assert passwords.hash_password("same password") != passwords.hash_password("same password")


def test_unusable_marker_never_verifies() -> None:
    assert not passwords.verify_password("!", "anything at all")
    assert not passwords.needs_rehash("!")


def test_length_rules_without_composition_rules() -> None:
    assert not passwords.is_acceptable("x" * 9)
    assert passwords.is_acceptable("x" * 10)  # no digits or symbols required (A-71)
    assert passwords.is_acceptable("x" * 128)
    assert not passwords.is_acceptable("x" * 129)


def test_weaker_old_hashes_are_flagged_for_upgrade() -> None:
    weak = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1).hash("a password here")
    try:
        passwords.use_hasher(PasswordHasher(time_cost=2, memory_cost=16, parallelism=1))
        assert passwords.needs_rehash(weak)
        assert passwords.verify_password(weak, "a password here")  # still accepted
    finally:
        passwords.use_hasher(PasswordHasher(time_cost=1, memory_cost=8, parallelism=1))

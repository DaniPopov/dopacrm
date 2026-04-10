"""Unit tests for core/security.py — password hashing + JWT."""

from app.core.security import hash_password, needs_rehash, verify_password


def test_hash_password_returns_argon2_format() -> None:
    """The hash should be a self-contained argon2 string."""
    h = hash_password("hunter2")
    assert h.startswith("$argon2"), f"expected argon2 hash, got {h[:20]!r}"


def test_hash_password_is_unique_per_call() -> None:
    """Two hashes of the same password should differ (random salt)."""
    a = hash_password("same-password")
    b = hash_password("same-password")
    assert a != b


def test_verify_password_matches_correct_password() -> None:
    h = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", h) is True


def test_verify_password_rejects_wrong_password() -> None:
    h = hash_password("correct horse battery staple")
    assert verify_password("wrong password", h) is False


def test_needs_rehash_is_false_for_fresh_hash() -> None:
    """A hash just produced with current params shouldn't need rehashing."""
    h = hash_password("test")
    assert needs_rehash(h) is False

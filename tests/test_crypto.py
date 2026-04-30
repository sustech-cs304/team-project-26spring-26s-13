"""
tests/test_crypto.py
Unit tests for backend/utils/crypto.py (Fernet encrypt/decrypt).

conftest.py sets FERNET_KEY in os.environ before any backend import,
so the singleton is always initialised with the test key.
"""

import pytest

# conftest.py already patched FERNET_KEY; safe to import now
from backend.utils.crypto import encrypt, decrypt


def test_encrypt_returns_bytes():
    """encrypt() must return non-empty bytes."""
    result = encrypt("hello world")
    assert isinstance(result, bytes)
    assert len(result) > 0


def test_decrypt_round_trip_ascii():
    """Encrypted text must decrypt back to the original string."""
    plaintext = "my_secret_password_123"
    assert decrypt(encrypt(plaintext)) == plaintext


def test_decrypt_round_trip_unicode():
    """Encrypt/decrypt must handle Unicode (including Chinese characters)."""
    plaintext = "南科大密码 π≈3.14"
    assert decrypt(encrypt(plaintext)) == plaintext


def test_decrypt_round_trip_long_string():
    """Encrypt/decrypt must work for large payloads."""
    plaintext = "x" * 10_000
    assert decrypt(encrypt(plaintext)) == plaintext


def test_encrypt_different_plaintexts_produce_different_ciphertexts():
    ct1 = encrypt("password_one")
    ct2 = encrypt("password_two")
    assert ct1 != ct2


def test_encrypt_same_plaintext_nondeterministic():
    """Fernet uses a random IV, so two encryptions of the same text differ."""
    ct1 = encrypt("same_text")
    ct2 = encrypt("same_text")
    assert ct1 != ct2


def test_decrypt_invalid_ciphertext_raises():
    """Decrypting corrupted bytes must raise an exception."""
    with pytest.raises(Exception):
        decrypt(b"totally-not-a-fernet-token")


def test_decrypt_empty_bytes_raises():
    """Decrypting empty bytes must raise an exception."""
    with pytest.raises(Exception):
        decrypt(b"")

from cryptography.fernet import Fernet

from app.core.crypto import (
    decrypt_secret,
    encrypt_secret,
    generate_extension_token,
    hash_token,
    token_matches,
)


def test_secret_round_trip():
    key = Fernet.generate_key().decode()
    ciphertext = encrypt_secret("sk-ant-secret", master_key=key)
    assert b"sk-ant-secret" not in ciphertext
    assert decrypt_secret(ciphertext, master_key=key) == "sk-ant-secret"


def test_extension_token_is_stored_as_hash_only():
    token = generate_extension_token()
    stored = hash_token(token)
    assert token.startswith("hb_") and token not in stored
    assert token_matches(token, stored)
    assert not token_matches(token + "x", stored)

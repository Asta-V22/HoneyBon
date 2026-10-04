"""Secrets at rest: Fernet for provider API keys, SHA-256 hashes for extension tokens."""

import hashlib
import hmac
import secrets

from cryptography.fernet import Fernet

from app.core.config import get_settings

TOKEN_PREFIX = "hb_"


def _fernet(master_key: str | None = None) -> Fernet:
    key = master_key or get_settings().master_key
    if not key:
        raise RuntimeError("MASTER_KEY is not set")
    return Fernet(key)


def encrypt_secret(plaintext: str, master_key: str | None = None) -> bytes:
    return _fernet(master_key).encrypt(plaintext.encode())


def decrypt_secret(ciphertext: bytes, master_key: str | None = None) -> str:
    return _fernet(master_key).decrypt(ciphertext).decode()


def generate_extension_token() -> str:
    return TOKEN_PREFIX + secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def token_matches(token: str, token_hash: str) -> bool:
    return hmac.compare_digest(hash_token(token), token_hash)

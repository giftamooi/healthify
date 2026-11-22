"""Autentikasi: password hash, JWT (untuk pengguna app), API key (untuk kelompok lain)."""
import hashlib
import hmac
import os
import secrets
import time

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer

from .db import get_db

JWT_ALG = "HS256"
JWT_TTL_SECONDS = 24 * 3600


def _jwt_secret() -> str:
    secret = os.getenv("JWT_SECRET")
    if not secret:
        raise RuntimeError("JWT_SECRET belum diisi di .env")
    return secret


# ---------- password ----------
def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return f"{salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    salt_hex, digest_hex = stored.split("$")
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex), n=2**14, r=8, p=1)
    return hmac.compare_digest(digest.hex(), digest_hex)


# ---------- JWT ----------
def create_token(user_id: int) -> str:
    now = int(time.time())
    payload = {"sub": str(user_id), "iat": now, "exp": now + JWT_TTL_SECONDS}
    return jwt.encode(payload, _jwt_secret(), algorithm=JWT_ALG)


bearer_scheme = HTTPBearer(auto_error=False)


def current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db=Depends(get_db),
):
    if creds is None:
        raise HTTPException(401, "Token tidak ada")
    try:
        payload = jwt.decode(creds.credentials, _jwt_secret(), algorithms=[JWT_ALG])
    except jwt.PyJWTError:
        raise HTTPException(401, "Token tidak valid atau kedaluwarsa")
    row = db.execute("SELECT * FROM users WHERE id = ?", (int(payload["sub"]),)).fetchone()
    if row is None:
        raise HTTPException(401, "Pengguna tidak ditemukan")
    return row


# ---------- API key ----------
api_key_scheme = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_api_key(key: str | None = Depends(api_key_scheme)) -> str:
    valid = [k.strip() for k in os.getenv("API_KEYS", "").split(",") if k.strip()]
    if not key or not any(hmac.compare_digest(key, v) for v in valid):
        raise HTTPException(401, "API key salah atau tidak ada")
    return key

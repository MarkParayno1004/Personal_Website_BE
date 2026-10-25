import os
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone
import bcrypt
import jwt

load_dotenv()

# Recommended: at least 32 bytes (256 bits) for HS256
SECRET_KEY = os.getenv("JWT_SECRET_KEY")
if not SECRET_KEY:
    raise ValueError("JWT_SECRET_KEY environment variable is not set. Check your env")
if os.getenv("APP_ENV", "development").lower() == "production" and len(SECRET_KEY.encode("utf-8")) < 32:
    raise ValueError("JWT_SECRET_KEY must be at least 32 bytes in production")

HEADER = {
    "alg": "HS256",
    "type": "JWT",
}

ALGORITHM = HEADER["alg"]
ACCESS_TOKEN_EXPIRE_MINUTES = 60


def hash_password(password: str) -> str:
    """Hash a plaintext password using bcrypt."""
    pwd_bytes = password.encode("utf-8")
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pwd_bytes, salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against a bcrypt hash."""
    # bcrypt 5 raises on >72-byte input; such a password can never match a stored hash.
    if len(plain_password.encode("utf-8")) > 72:
        return False
    return bcrypt.checkpw(
        plain_password.encode("utf-8"),
        hashed_password.encode("utf-8"),
    )


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """Create a signed JWT access token including the custom header."""
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta if expires_delta else timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire, "iat": now})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM, headers=HEADER)


def decode_access_token(token: str) -> dict:
    """Decode and validate a JWT access token. The algorithm is pinned, never read from the token."""
    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    # Email-verification / password-reset tokens must never work as login tokens.
    if "purpose" in payload:
        raise jwt.InvalidTokenError("Not an access token")
    return payload


def create_purpose_token(user_id: int, purpose: str, expires_delta: timedelta, **claims) -> str:
    """Single-purpose token (e.g. password reset) that decode_access_token refuses."""
    return create_access_token({"sub": str(user_id), "purpose": purpose, **claims}, expires_delta)


def decode_purpose_token(token: str, purpose: str) -> dict:
    """Decode a token created by create_purpose_token; raises jwt.InvalidTokenError on any mismatch."""
    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    if payload.get("purpose") != purpose:
        raise jwt.InvalidTokenError("Wrong token purpose")
    return payload

import os
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone
import bcrypt
import jwt

load_dotenv()

# Recommended: at least 32 bytes (256 bits) for HS256
SECRET_KEY = os.getenv("JWT_SECRET_KEY")
if not SECRET_KEY:
    raise ValueError("SECRET KET environment variable is not set. Check your env")

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
    return bcrypt.checkpw(
        plain_password.encode("utf-8"),
        hashed_password.encode("utf-8"),
    )


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """Create a signed JWT access token including the custom header."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta if expires_delta else timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=HEADER["alg"], headers=HEADER)


def decode_access_token(token: str) -> dict:
    """Decode and validate a JWT access token using the token header."""
    header = jwt.get_unverified_header(token)
    alg = header.get("alg", HEADER["alg"])
    return jwt.decode(token, SECRET_KEY, algorithms=[alg])

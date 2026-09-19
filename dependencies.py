from fastapi import Depends, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBasic, HTTPBasicCredentials, HTTPBearer
from sqlalchemy.orm import Session
from database import get_db
from models import User
from security import decode_access_token, verify_password

security_scheme = HTTPBearer(auto_error=False)
security_basic = HTTPBasic(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Validate Bearer token and retrieve the current authenticated user."""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    try:
        payload = decode_access_token(token)
        user_id_str = payload.get("sub")
        if not user_id_str:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload",
            )
        user_id = int(user_id_str)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return user


def get_current_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    """Ensure the authenticated user has administrative privileges."""
    if not current_user.admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Administrative privileges required",
        )
    return current_user


def get_docs_authenticated_user(
    basic_credentials: HTTPBasicCredentials | None = Depends(security_basic),
    credentials: HTTPAuthorizationCredentials | None = Depends(security_scheme),
    token: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> User:
    """
    Authenticate access to protected API documentation (/docs, /redoc, /openapi.json) using:
    1. HTTP Basic Auth (email + password from DB)
    2. JWT Bearer token
    3. Query parameter ?token=...
    """
    # 1. Try HTTP Basic Auth (Browser popup login)
    if basic_credentials:
        user = db.query(User).filter(User.email == basic_credentials.username).first()
        if user and user.hashed_password and verify_password(basic_credentials.password, user.hashed_password):
            return user

    # 2. Try Bearer token or Query parameter token
    raw_token = credentials.credentials if credentials else token
    if raw_token:
        try:
            payload = decode_access_token(raw_token)
            user_id = int(payload.get("sub", 0))
            user = db.query(User).filter(User.id == user_id).first()
            if user:
                return user
        except Exception:
            pass

    # Prompt browser HTTP Basic auth modal if unauthenticated
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required to access API documentation",
        headers={"WWW-Authenticate": "Basic realm='Protected API Documentation'"},
    )

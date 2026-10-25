import io
import os
import uuid
from datetime import timedelta
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, UploadFile, File, status
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy.orm import Session
import storage
from audit import record_audit
from database import get_db
from dependencies import get_current_user
from mailer import send_password_reset_email, send_verification_email
from models import User
from rate_limit import email_limiter, login_limiter, register_limiter
from schemas import (
    EmailRequest,
    PasswordChange,
    PasswordResetConfirm,
    TokenConfirm,
    UserCreate,
    UserLogin,
    UserPublic,
    UserWithToken,
)
from security import create_access_token, create_purpose_token, decode_purpose_token, hash_password, verify_password

# Reject decompression bombs (Pillow raises above 2x this pixel count)
Image.MAX_IMAGE_PIXELS = 16_000_000

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tiff"}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB
MAX_PROFILE_PICTURE_DIMENSIONS = (512, 512)
OUTPUT_IMAGE_FORMAT = "WEBP"
OUTPUT_IMAGE_EXT = ".webp"
OUTPUT_IMAGE_QUALITY = 82
MAX_DOCUMENT_SIZE = 10 * 1024 * 1024  # 10 MB

VERIFY_EMAIL_PURPOSE = "verify_email"
VERIFY_EMAIL_TTL = timedelta(hours=24)
PASSWORD_RESET_PURPOSE = "password_reset"
PASSWORD_RESET_TTL = timedelta(minutes=30)


def convert_and_optimize_image(
    file_bytes: bytes,
    max_dimensions: tuple[int, int] = MAX_PROFILE_PICTURE_DIMENSIONS,
    quality: int = OUTPUT_IMAGE_QUALITY,
) -> bytes:
    """
    Validates, applies EXIF orientation transpose, scales down if larger than max_dimensions,
    and converts/compresses the image to a lightweight WebP byte stream.
    """
    try:
        image = Image.open(io.BytesIO(file_bytes))
    except (UnidentifiedImageError, ValueError, Exception):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid image file or corrupted image data",
        )

    # Correct image orientation from EXIF metadata (e.g., smartphone camera captures)
    try:
        image = ImageOps.exif_transpose(image)
    except Exception:
        pass

    # Normalize color mode for WebP conversion
    if image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info):
        image = image.convert("RGBA")
    else:
        image = image.convert("RGB")

    # Scale down preserving aspect ratio
    image.thumbnail(max_dimensions, Image.Resampling.LANCZOS)

    # Export to optimized WebP buffer
    buffer = io.BytesIO()
    image.save(buffer, format=OUTPUT_IMAGE_FORMAT, quality=quality, optimize=True)
    return buffer.getvalue()


def validate_pdf_file(file: UploadFile) -> bytes:
    """Validate that the uploaded file is strictly a valid PDF document."""
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext != ".pdf":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Only PDF files (.pdf) are allowed. Received: '{ext or 'unknown'}'",
        )

    file.file.seek(0, 2)
    size = file.file.tell()
    file.file.seek(0)
    if size > MAX_DOCUMENT_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File exceeds maximum allowed size of {MAX_DOCUMENT_SIZE // (1024 * 1024)} MB",
        )
    if size == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty",
        )

    file_bytes = file.file.read()
    if not file_bytes.startswith(b"%PDF"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid PDF file format. File does not start with valid PDF signature.",
        )

    return file_bytes


def private_pdf_response(key: str | None, filename: str) -> Response:
    """Stream a private PDF to an already-authorized caller."""
    data = storage.get_private(key) if key else None
    if data is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No CV file uploaded")
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"', "Cache-Control": "private, no-store"},
    )


def issue_token(user: User) -> UserWithToken:
    token = create_access_token({"sub": str(user.id), "email": user.email, "ver": user.token_version})
    return UserWithToken(**UserPublic.model_validate(user).model_dump(), token=token)


def queue_verification_email(background_tasks: BackgroundTasks, user: User) -> None:
    # The email claim ties the link to the address it was sent to.
    token = create_purpose_token(user.id, VERIFY_EMAIL_PURPOSE, VERIFY_EMAIL_TTL, email=user.email)
    background_tasks.add_task(send_verification_email, user.email, token)


def invalid_link() -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired link")


router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=UserWithToken,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(register_limiter)],
)
def register(
    user_data: UserCreate,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    existing = db.query(User).filter(User.email == user_data.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email is already registered",
        )

    new_user = User(
        email=user_data.email,
        first_name=user_data.first_name,
        last_name=user_data.last_name,
        admin=False,  # Enforce non-admin for public registrations (use scripts/create_admin.py for admins)
        hashed_password=hash_password(user_data.password),
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    record_audit(db, request, new_user, "register", "user", new_user.id)
    queue_verification_email(background_tasks, new_user)
    return issue_token(new_user)


@router.post("/login", response_model=UserWithToken, dependencies=[Depends(login_limiter)])
def login(credentials: UserLogin, request: Request, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == credentials.email).first()
    if not user or not verify_password(credentials.password, user.hashed_password):
        record_audit(db, request, None, "login_failed", details={"email": credentials.email})
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    record_audit(db, request, user, "login", "user", user.id)
    return issue_token(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Revoke every token issued to the current user (all devices)."""
    current_user.token_version += 1
    db.commit()
    record_audit(db, request, current_user, "logout", "user", current_user.id)
    return None


@router.put("/me/password", response_model=UserWithToken, dependencies=[Depends(login_limiter)])
def change_password(
    payload: PasswordChange,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Change password, revoke all existing tokens, and return a fresh token."""
    if not verify_password(payload.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )
    current_user.hashed_password = hash_password(payload.new_password)
    current_user.token_version += 1
    db.commit()
    record_audit(db, request, current_user, "password_change", "user", current_user.id)
    db.refresh(current_user)
    return issue_token(current_user)


@router.post("/verify-email/request", status_code=status.HTTP_202_ACCEPTED, dependencies=[Depends(email_limiter)])
def request_email_verification(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
):
    """Email a fresh verification link to the current user (no-op if already verified)."""
    if not current_user.email_verified:
        queue_verification_email(background_tasks, current_user)
    return {"detail": "If your email is not verified yet, a verification link has been sent."}


@router.post("/verify-email/confirm", response_model=UserPublic)
def confirm_email_verification(payload: TokenConfirm, request: Request, db: Session = Depends(get_db)):
    try:
        claims = decode_purpose_token(payload.token, VERIFY_EMAIL_PURPOSE)
        user = db.query(User).filter(User.id == int(claims["sub"])).first()
    except Exception:
        raise invalid_link()
    if not user or user.email != claims.get("email"):
        raise invalid_link()
    if not user.email_verified:
        user.email_verified = True
        db.commit()
        record_audit(db, request, user, "email_verified", "user", user.id)
        db.refresh(user)
    return user


@router.post("/password-reset/request", status_code=status.HTTP_202_ACCEPTED, dependencies=[Depends(email_limiter)])
def request_password_reset(
    payload: EmailRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Always 202, whether or not the email exists, so accounts cannot be enumerated."""
    user = db.query(User).filter(User.email == payload.email).first()
    record_audit(db, request, user, "password_reset_request", "user", user.id if user else None)
    if user:
        # "ver" makes the link single-use: confirming bumps token_version, which invalidates it.
        token = create_purpose_token(user.id, PASSWORD_RESET_PURPOSE, PASSWORD_RESET_TTL, ver=user.token_version)
        background_tasks.add_task(send_password_reset_email, user.email, token)
    return {"detail": "If that email is registered, a password reset link has been sent."}


@router.post("/password-reset/confirm", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(email_limiter)])
def confirm_password_reset(payload: PasswordResetConfirm, request: Request, db: Session = Depends(get_db)):
    try:
        claims = decode_purpose_token(payload.token, PASSWORD_RESET_PURPOSE)
        user = db.query(User).filter(User.id == int(claims["sub"])).first()
        token_version = int(claims["ver"])
    except Exception:
        raise invalid_link()
    if not user or user.token_version != token_version:
        raise invalid_link()
    user.hashed_password = hash_password(payload.new_password)
    user.token_version += 1  # revokes this link and every session
    user.email_verified = True  # receiving the link proves the address
    db.commit()
    record_audit(db, request, user, "password_reset_confirm", "user", user.id)
    return None


@router.get("/me", response_model=UserPublic)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(request: Request, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Permanently delete the current user's account, all their records, and uploaded files."""
    if current_user.admin and db.query(User).filter(User.admin.is_(True)).count() == 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete the last administrator account",
        )
    user_id, profile_picture, cv_key = current_user.id, current_user.profile_picture, current_user.cv_url
    db.delete(current_user)
    db.commit()
    record_audit(db, request, None, "account_delete", "user", user_id)  # the actor row is gone; target_id names it
    storage.delete_public(profile_picture)
    storage.delete_private(cv_key)
    return None


@router.put("/me/profile-picture", response_model=UserPublic)
def upload_profile_picture(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Upload or replace the authenticated user's profile picture."""
    # Validate file extension
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type '{ext}' not allowed. Accepted: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    # Validate file size
    file.file.seek(0, 2)  # Seek to end
    size = file.file.tell()
    file.file.seek(0)  # Reset to beginning
    if size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File too large. Maximum size is {MAX_FILE_SIZE // (1024 * 1024)} MB",
        )

    # Read and compress/convert image first, so a bad upload never wipes the existing picture
    file_bytes = file.file.read()
    optimized_bytes = convert_and_optimize_image(file_bytes)

    key = f"profile_pictures/{current_user.id}_{uuid.uuid4().hex}{OUTPUT_IMAGE_EXT}"
    url = storage.put_public(key, optimized_bytes, "image/webp")

    # Store the public URL, then drop the previous file
    old_picture = current_user.profile_picture
    current_user.profile_picture = url
    db.commit()
    db.refresh(current_user)
    storage.delete_public(old_picture)
    return current_user


@router.delete("/me/profile-picture", response_model=UserPublic)
def delete_profile_picture(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Remove the authenticated user's profile picture."""
    if not current_user.profile_picture:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No profile picture to delete",
        )

    storage.delete_public(current_user.profile_picture)
    current_user.profile_picture = None
    db.commit()
    db.refresh(current_user)
    return current_user


@router.get("/me/cv")
def download_user_cv(current_user: User = Depends(get_current_user)):
    """Download the authenticated user's own CV (CVs are never publicly reachable)."""
    return private_pdf_response(current_user.cv_url, "cv.pdf")


@router.put("/me/cv", response_model=UserPublic)
@router.post("/me/cv", response_model=UserPublic)
def upload_user_cv(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Upload or replace the authenticated user's CV PDF file (max 10MB)."""
    pdf_bytes = validate_pdf_file(file)
    key = storage.put_private(f"documents/user_{current_user.id}_cv_{uuid.uuid4().hex}.pdf", pdf_bytes, "application/pdf")

    old_key = current_user.cv_url
    current_user.cv_url = key
    db.commit()
    db.refresh(current_user)
    storage.delete_private(old_key)
    return current_user


@router.delete("/me/cv", response_model=UserPublic)
def delete_user_cv(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Remove the authenticated user's CV PDF."""
    if not current_user.cv_url:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No CV file to delete",
        )

    storage.delete_private(current_user.cv_url)
    current_user.cv_url = None
    db.commit()
    db.refresh(current_user)
    return current_user

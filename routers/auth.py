import io
import os
import uuid
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy.orm import Session
from database import get_db
from dependencies import get_current_user
from models import User
from schemas import UserCreate, UserLogin, UserPublic
from security import create_access_token, hash_password, verify_password

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads", "profile_pictures")
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tiff"}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB
MAX_PROFILE_PICTURE_DIMENSIONS = (512, 512)
OUTPUT_IMAGE_FORMAT = "WEBP"
OUTPUT_IMAGE_EXT = ".webp"
OUTPUT_IMAGE_QUALITY = 82


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

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=UserPublic, status_code=status.HTTP_201_CREATED)
def register(user_data: UserCreate, db: Session = Depends(get_db)):
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

    # Issue JWT token
    token = create_access_token({"sub": str(new_user.id), "email": new_user.email})
    new_user.token = token
    db.commit()
    db.refresh(new_user)
    return new_user


@router.post("/login", response_model=UserPublic)
def login(credentials: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == credentials.email).first()
    if not user or not verify_password(credentials.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    token = create_access_token({"sub": str(user.id), "email": user.email})
    user.token = token
    db.commit()
    db.refresh(user)
    return user


@router.get("/me", response_model=UserPublic)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user


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

    # Ensure upload directory exists
    os.makedirs(UPLOAD_DIR, exist_ok=True)

    # Delete previous profile picture if one exists
    if current_user.profile_picture:
        old_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            current_user.profile_picture.lstrip("/"),
        )
        if os.path.exists(old_path):
            os.remove(old_path)

    # Read and compress/convert image to lightweight WebP
    file_bytes = file.file.read()
    optimized_bytes = convert_and_optimize_image(file_bytes)

    # Save converted file with unique name and .webp extension
    unique_filename = f"{current_user.id}_{uuid.uuid4().hex}{OUTPUT_IMAGE_EXT}"
    file_path = os.path.join(UPLOAD_DIR, unique_filename)
    with open(file_path, "wb") as buffer:
        buffer.write(optimized_bytes)

    # Store relative URL path in the database
    current_user.profile_picture = f"/uploads/profile_pictures/{unique_filename}"
    db.commit()
    db.refresh(current_user)
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

    # Delete file from disk
    file_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        current_user.profile_picture.lstrip("/"),
    )
    if os.path.exists(file_path):
        os.remove(file_path)

    current_user.profile_picture = None
    db.commit()
    db.refresh(current_user)
    return current_user


DOCUMENTS_UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads", "documents")
MAX_DOCUMENT_SIZE = 10 * 1024 * 1024  # 10 MB


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
    if not file_bytes.startswith(b"%PDF-") and not file_bytes.startswith(b"%PDF"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid PDF file format. File does not start with valid PDF signature.",
        )

    return file_bytes


@router.put("/me/cv", response_model=UserPublic)
@router.post("/me/cv", response_model=UserPublic)
def upload_user_cv(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Upload or replace the authenticated user's CV PDF file (max 10MB)."""
    pdf_bytes = validate_pdf_file(file)

    os.makedirs(DOCUMENTS_UPLOAD_DIR, exist_ok=True)

    if current_user.cv_url:
        old_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            current_user.cv_url.lstrip("/"),
        )
        if os.path.exists(old_path):
            os.remove(old_path)

    unique_filename = f"user_{current_user.id}_cv_{uuid.uuid4().hex}.pdf"
    file_path = os.path.join(DOCUMENTS_UPLOAD_DIR, unique_filename)
    with open(file_path, "wb") as f:
        f.write(pdf_bytes)

    current_user.cv_url = f"/uploads/documents/{unique_filename}"
    db.commit()
    db.refresh(current_user)
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

    file_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        current_user.cv_url.lstrip("/"),
    )
    if os.path.exists(file_path):
        os.remove(file_path)

    current_user.cv_url = None
    db.commit()
    db.refresh(current_user)
    return current_user

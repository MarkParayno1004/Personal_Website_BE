import os
import uuid
import shutil
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy.orm import Session
from database import get_db
from dependencies import get_current_user
from models import User
from schemas import UserCreate, UserLogin, UserPublic
from security import create_access_token, hash_password, verify_password

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads", "profile_pictures")
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB

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

    # Save new file with a unique name
    unique_filename = f"{current_user.id}_{uuid.uuid4().hex}{ext}"
    file_path = os.path.join(UPLOAD_DIR, unique_filename)
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

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

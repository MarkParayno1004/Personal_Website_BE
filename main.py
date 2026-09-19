import os
from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from sqlalchemy.orm import Session
from database import Base, engine, get_db
from dependencies import get_docs_authenticated_user
from models import User
from routers import admin, auth, expenses, github, medications, portfolio

from schemas import UserCreate, UserLogin, UserPublic

ENVIRONMENT = os.getenv("APP_ENV").lower()
IS_PRODUCTION = ENVIRONMENT == "production"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Attempt to automatically create database tables in PostgreSQL on startup
    try:
        Base.metadata.create_all(bind=engine)
    except Exception as e:
        print(f"[Warning] Database tables could not be initialized automatically: {e}")
    yield


app = FastAPI(
    title="Personal Portfolio API",
    description="FastAPI backend featuring PostgreSQL, JWT Authentication, Admin Roles, Expenses & Medications trackers, GitHub Repositories, and LinkedIn Event Posts.",
    version="0.2.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan,
)

# Enable CORS for frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Modular Routers
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(expenses.router)
app.include_router(medications.router)
app.include_router(github.router)
app.include_router(portfolio.router)


# Protected API Documentation Endpoints
@app.get("/openapi.json", include_in_schema=False)
def get_protected_openapi(user: User = Depends(get_docs_authenticated_user)):
    if IS_PRODUCTION:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")
    return get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )


@app.get("/docs", include_in_schema=False)
def get_protected_docs(user: User = Depends(get_docs_authenticated_user)):
    if IS_PRODUCTION:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")
    return get_swagger_ui_html(openapi_url="/openapi.json", title=f"{app.title} - Swagger UI")


@app.get("/redoc", include_in_schema=False)
def get_protected_redoc(user: User = Depends(get_docs_authenticated_user)):
    if IS_PRODUCTION:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")
    return get_redoc_html(openapi_url="/openapi.json", title=f"{app.title} - ReDoc")


# Backwards-compatible root endpoint aliases
@app.post("/users/", response_model=UserPublic, status_code=status.HTTP_201_CREATED, tags=["Authentication"])
def create_user_alias(user_data: UserCreate, db: Session = Depends(get_db)):
    return auth.register(user_data=user_data, db=db)


@app.post("/login/", response_model=UserPublic, tags=["Authentication"])
def login_alias(credentials: UserLogin, db: Session = Depends(get_db)):
    return auth.login(credentials=credentials, db=db)


@app.get("/users/{user_id}", response_model=UserPublic, tags=["Authentication"])
def get_user_alias(user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return user


@app.get("/", tags=["Health"])
def health_check():
    return {
        "status": "healthy",
        "message": "Personal Portfolio API is running",
        "docs": "/docs",
    }
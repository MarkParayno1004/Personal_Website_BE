import os
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.orm import Session
import storage
from database import get_db
from dependencies import get_current_user, get_docs_authenticated_user
from models import User
from rate_limit import login_limiter, register_limiter
from redis_cache import get_redis_client
from routers import admin, auth, categories, expenses, github, incomes, medications, portfolio, savings

from schemas import UserCreate, UserLogin, UserPublic, UserWithToken

ENVIRONMENT = os.getenv("APP_ENV", "development").lower()
IS_PRODUCTION = ENVIRONMENT == "production"

# Comma-separated list of frontend origins allowed to call the API
CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:5173").split(",")
    if origin.strip()
]

# Schema is managed by Alembic only: run `alembic upgrade head` before starting the app.
app = FastAPI(
    title="Personal Portfolio API",
    description="FastAPI backend featuring PostgreSQL, JWT Authentication, Admin Roles, Expenses & Medications trackers, GitHub Repositories, and LinkedIn Event Posts.",
    version="0.2.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

# Enable CORS for frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Total-Count"],  # pagination total for list endpoints
)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    if IS_PRODUCTION:
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        # Docs are disabled in production, so nothing needs to run scripts from this origin.
        response.headers.setdefault("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
    return response

# Include Modular Routers
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(incomes.router)
app.include_router(categories.router)
app.include_router(expenses.router)
app.include_router(savings.router)
app.include_router(medications.router)
app.include_router(github.router)
app.include_router(portfolio.router)

# Local-disk fallback only: serve public uploads (profile pictures). With R2 they are served by R2_PUBLIC_BASE_URL.
# Private files (CVs) live in storage.PRIVATE_DIR, which is never mounted.
if not storage.USE_R2:
    os.makedirs(storage.PUBLIC_DIR, exist_ok=True)
    app.mount("/uploads", StaticFiles(directory=storage.PUBLIC_DIR), name="uploads")


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
@app.post(
    "/users/",
    response_model=UserWithToken,
    status_code=status.HTTP_201_CREATED,
    tags=["Authentication"],
    dependencies=[Depends(register_limiter)],
)
def create_user_alias(
    user_data: UserCreate,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    return auth.register(user_data=user_data, request=request, background_tasks=background_tasks, db=db)


@app.post("/login/", response_model=UserWithToken, tags=["Authentication"], dependencies=[Depends(login_limiter)])
def login_alias(credentials: UserLogin, request: Request, db: Session = Depends(get_db)):
    return auth.login(credentials=credentials, request=request, db=db)


@app.get("/users/{user_id}", response_model=UserPublic, tags=["Authentication"])
def get_user_alias(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Users may only read themselves; admins may read anyone.
    if user_id != current_user.id and not current_user.admin:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
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
    }


@app.get("/healthz", tags=["Health"])
def readiness_check(db: Session = Depends(get_db)):
    """Readiness probe: verifies the database answers; Redis is optional and only reported."""
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        return JSONResponse(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content={"status": "unhealthy", "database": "down"})
    return {"status": "healthy", "database": "up", "redis": "up" if get_redis_client() else "off"}
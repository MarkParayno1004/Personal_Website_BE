from datetime import datetime
from pydantic import BaseModel, ConfigDict, EmailStr


# ==========================================
# User Schemas
# ==========================================
class UserBase(BaseModel):
    first_name: str
    last_name: str
    email: EmailStr
    admin: bool = False


class UserCreate(UserBase):
    password: str


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserPublic(UserBase):
    id: int
    profile_picture: str | None = None
    token: str | None = None

    model_config = ConfigDict(from_attributes=True)


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class User(UserBase):
    id: int
    profile_picture: str | None = None
    token: str | None = None
    password: str | None = None
    hashed_password: str | None = None

    model_config = ConfigDict(from_attributes=True)


class UserRoleUpdate(BaseModel):
    admin: bool


# ==========================================
# Expenses & Tax Deduction Schemas
# ==========================================
class ExpenseItemCreate(BaseModel):
    description: str
    amount: float


class ExpenseItemResponse(BaseModel):
    id: int
    description: str
    amount: float

    model_config = ConfigDict(from_attributes=True)


class TaxDeductionCreate(BaseModel):
    description: str
    amount: float


class TaxDeductionResponse(BaseModel):
    id: int
    description: str
    amount: float

    model_config = ConfigDict(from_attributes=True)


class ExpenseCreate(BaseModel):
    title: str  # e.g. "Chase Sapphire Credit Card Expenses" or "Monthly Budget - March"
    gross_income: float = 0.0
    net_income: float | None = None
    category_id: int | None = None
    items: list[ExpenseItemCreate] = []
    tax_deductions: list[TaxDeductionCreate] = []


class ExpenseUpdate(BaseModel):
    title: str | None = None
    gross_income: float | None = None
    net_income: float | None = None
    category_id: int | None = None
    items: list[ExpenseItemCreate] | None = None
    tax_deductions: list[TaxDeductionCreate] | None = None


class ExpenseResponse(BaseModel):
    id: int
    title: str
    gross_income: float = 0.0
    net_income: float = 0.0
    total_tax_deductions: float = 0.0
    total_expenses: float = 0.0
    total_amount: float = 0.0  # Kept for backward compatibility
    remaining_income: float = 0.0
    category_id: int | None = None
    items: list[ExpenseItemResponse] = []
    tax_deductions: list[TaxDeductionResponse] = []
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# Medication Schemas
# ==========================================
class MedicationCreate(BaseModel):
    name: str
    cost: float  # Cost of medicine
    doses_taken: int = 0  # How many already taken
    category_id: int | None = None


class MedicationUpdate(BaseModel):
    cost: float | None = None
    doses_taken: int | None = None
    category_id: int | None = None


class MedicationDoseLog(BaseModel):
    doses: int = 1  # How many taken in this log event


class MedicationResponse(BaseModel):
    id: int
    name: str
    cost: float
    doses_taken: int
    total_spent: float = 0.0
    category_id: int | None = None

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# Category Schemas
# ==========================================
class CategoryCreate(BaseModel):
    title: str
    expenses: list[ExpenseCreate] = []
    medications: list[MedicationCreate] = []


class CategoryUpdate(BaseModel):
    title: str | None = None


class CategoryResponse(BaseModel):
    id: int
    title: str
    user_id: int | None = None
    expenses: list[ExpenseResponse] = []
    medications: list[MedicationResponse] = []
    total_expenses_amount: float = 0.0
    total_medications_amount: float = 0.0
    total_amount: float = 0.0
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# External API Schemas (GitHub & LinkedIn)
# ==========================================
class GitHubRepo(BaseModel):
    id: int
    name: str
    full_name: str
    html_url: str
    description: str | None = None
    language: str | None = None
    stars: int = 0
    forks: int = 0
    updated_at: str | None = None


class LinkedInPost(BaseModel):
    id: str
    text: str
    event_title: str | None = None
    event_url: str | None = None
    published_at: str | None = None
    likes_count: int = 0


# ==========================================
# Admin Schemas
# ==========================================
class AdminStats(BaseModel):
    total_users: int
    total_expenses: int
    total_medications: int
    total_categories: int = 0
    total_expense_amount: float


# ==========================================
# Portfolio Config Schemas
# ==========================================
class PortfolioConfigBase(BaseModel):
    full_name: str = "Mark Philip V. Parayno"
    headline: str = "Software Engineer | Mobile & Web Applications"
    location: str = "San Juan City, Philippines"
    phone: str = "+63 961 312 8973"
    email: str = "paraynomarkphilip@gmail.com"
    linkedin_url: str = "https://www.linkedin.com/in/mark-philip-parayno/"
    github_username: str = "MarkParayno1004"
    about_summary: str = (
        "Software Engineer with production experience building and maintaining mobile and web applications "
        "for a large retail enterprise. Strong across Flutter, Svelte, React, Django, and Laravel. Focused on "
        "shipping reliable features, improving performance, and keeping delivery pipelines healthy in Agile teams."
    )
    skills: dict[str, list[str]] | None = None
    experience: list[dict] | None = None
    education: list[dict] | None = None
    theme_config: dict | None = None


class PortfolioConfigUpdate(BaseModel):
    full_name: str | None = None
    headline: str | None = None
    location: str | None = None
    phone: str | None = None
    email: str | None = None
    linkedin_url: str | None = None
    github_username: str | None = None
    about_summary: str | None = None
    skills: dict[str, list[str]] | None = None
    experience: list[dict] | None = None
    education: list[dict] | None = None
    theme_config: dict | None = None


class PortfolioConfigResponse(PortfolioConfigBase):
    id: int
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


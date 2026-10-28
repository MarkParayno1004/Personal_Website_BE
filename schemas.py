from datetime import datetime
from typing import Annotated
from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr, Field


def _within_bcrypt_limit(value: str) -> str:
    if len(value.encode("utf-8")) > 72:
        raise ValueError("Password must be at most 72 bytes")
    return value


# Shared input constraints
Text = Annotated[str, Field(min_length=1, max_length=255)]
Money = Annotated[float, Field(ge=0)]
Password = Annotated[str, Field(min_length=8), AfterValidator(_within_bcrypt_limit)]


# ==========================================
# User Schemas
# ==========================================
class UserBase(BaseModel):
    first_name: Text
    last_name: Text
    email: EmailStr
    admin: bool = False


class UserCreate(UserBase):
    password: Password


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class PasswordChange(BaseModel):
    current_password: str
    new_password: Password


class EmailRequest(BaseModel):
    email: EmailStr


class TokenConfirm(BaseModel):
    token: str = Field(min_length=1, max_length=2048)


class PasswordResetConfirm(TokenConfirm):
    new_password: Password


class UserPublic(UserBase):
    id: int
    profile_picture: str | None = None
    email_verified: bool = False
    # The CV itself is private: only its presence is exposed; the owner downloads it via GET /auth/me/cv.
    has_cv: bool = False

    model_config = ConfigDict(from_attributes=True)


class UserWithToken(UserPublic):
    """Returned only by login/register; the token is never stored or exposed elsewhere."""
    token: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class User(UserBase):
    id: int
    profile_picture: str | None = None
    cv_url: str | None = None
    token: str | None = None
    password: str | None = None
    hashed_password: str | None = None

    model_config = ConfigDict(from_attributes=True)


class UserRoleUpdate(BaseModel):
    admin: bool


class AuditLogResponse(BaseModel):
    id: int
    actor_user_id: int | None = None
    action: str
    target_type: str | None = None
    target_id: str | None = None
    details: dict | None = None
    ip: str | None = None
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# Savings Schemas
# ==========================================
class SavingItemCreate(BaseModel):
    description: Text
    amount: Money


class SavingItemResponse(BaseModel):
    id: int
    saving_id: int | None = None
    description: str
    amount: float
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class SavingCreate(BaseModel):
    title: Text
    expense_id: int | None = None
    items: list[SavingItemCreate] = []


class SavingUpdate(BaseModel):
    title: Text | None = None
    expense_id: int | None = None
    items: list[SavingItemCreate] | None = None


class SavingLinkExpense(BaseModel):
    expense_id: int


class SavingResponse(BaseModel):
    id: int
    title: str
    expense_id: int | None = None
    user_id: int | None = None
    total_amount: float = 0.0
    items: list[SavingItemResponse] = []
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# Expenses & Tax Deduction Schemas
# ==========================================
class ExpenseItemCreate(BaseModel):
    description: Text
    amount: Money


class ExpenseItemResponse(BaseModel):
    id: int
    description: str
    amount: float

    model_config = ConfigDict(from_attributes=True)


class TaxDeductionCreate(BaseModel):
    description: Text
    amount: Money


class TaxDeductionResponse(BaseModel):
    id: int
    description: str
    amount: float

    model_config = ConfigDict(from_attributes=True)


class ExpenseCreate(BaseModel):
    title: Text  # e.g. "Chase Sapphire Credit Card Expenses" or "Monthly Budget - March"
    gross_income: Money = 0.0
    net_income: float | None = None
    category_id: int | None = None
    gross_income_id: int | None = None
    items: list[ExpenseItemCreate] = []
    tax_deductions: list[TaxDeductionCreate] = []


class ExpenseUpdate(BaseModel):
    title: Text | None = None
    gross_income: Money | None = None
    net_income: float | None = None
    category_id: int | None = None
    gross_income_id: int | None = None
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
    gross_income_id: int | None = None
    items: list[ExpenseItemResponse] = []
    tax_deductions: list[TaxDeductionResponse] = []
    savings: list[SavingResponse] = []
    total_savings: float = 0.0
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# Medication Schemas
# ==========================================
class MedicationCreate(BaseModel):
    name: Text
    cost: Money  # Cost of medicine
    doses_taken: int = Field(default=0, ge=0)  # How many already taken
    category_id: int | None = None
    gross_income_id: int | None = None


class MedicationUpdate(BaseModel):
    cost: Money | None = None
    doses_taken: int | None = Field(default=None, ge=0)
    category_id: int | None = None
    gross_income_id: int | None = None


class MedicationDoseLog(BaseModel):
    doses: int = Field(default=1, ge=1)  # How many taken in this log event


class MedicationResponse(BaseModel):
    id: int
    name: str
    cost: float
    doses_taken: int
    total_spent: float = 0.0
    category_id: int | None = None
    gross_income_id: int | None = None

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# Category Schemas
# ==========================================
class CategoryLinkItems(BaseModel):
    expense_ids: list[int] = []
    medication_ids: list[int] = []


class CategoryUnlinkItems(BaseModel):
    expense_ids: list[int] = []
    medication_ids: list[int] = []


class CategoryCreate(BaseModel):
    title: Text
    expenses: list[ExpenseCreate] = []
    medications: list[MedicationCreate] = []
    expense_ids: list[int] = []
    medication_ids: list[int] = []


class CategoryUpdate(BaseModel):
    title: Text | None = None
    expense_ids: list[int] | None = None
    medication_ids: list[int] | None = None


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
# Gross Income Schemas
# ==========================================
class GrossIncomeCreate(BaseModel):
    title: Text  # e.g. "Full-time Software Engineer Salary"
    amount: Money = 0.0  # Gross income amount
    tax_deductions: list[TaxDeductionCreate] = []
    expense_ids: list[int] = []
    medication_ids: list[int] = []


class GrossIncomeUpdate(BaseModel):
    title: Text | None = None
    amount: Money | None = None
    tax_deductions: list[TaxDeductionCreate] | None = None
    expense_ids: list[int] | None = None
    medication_ids: list[int] | None = None


class GrossIncomeLinkItems(BaseModel):
    expense_ids: list[int] = []
    medication_ids: list[int] = []


class GrossIncomeUnlinkItems(BaseModel):
    expense_ids: list[int] = []
    medication_ids: list[int] = []


class GrossIncomeResponse(BaseModel):
    id: int
    title: str
    amount: float = 0.0  # Gross income amount
    total_tax_deductions: float = 0.0
    net_income: float = 0.0
    total_expenses: float = 0.0
    total_medications: float = 0.0
    remaining_income: float = 0.0
    user_id: int | None = None
    tax_deductions: list[TaxDeductionResponse] = []
    expenses: list[ExpenseResponse] = []
    medications: list[MedicationResponse] = []
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
    total_gross_incomes: int = 0
    total_savings: int = 0
    total_expense_amount: float
    total_gross_income_amount: float = 0.0
    total_savings_amount: float = 0.0

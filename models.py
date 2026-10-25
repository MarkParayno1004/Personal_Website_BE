from datetime import datetime, timezone
from sqlalchemy import JSON, Boolean, Column, DateTime, Float, ForeignKey, Integer, String, false
from sqlalchemy.orm import relationship
from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    hashed_password = Column(String, nullable=False)
    admin = Column(Boolean, default=False, nullable=False)
    profile_picture = Column(String, nullable=True)  # public URL
    cv_url = Column(String, nullable=True)  # private storage key, never exposed (name kept to avoid a rename migration)
    # Bumped on logout/password change; tokens carrying an older "ver" claim are rejected.
    token_version = Column(Integer, default=0, server_default="0", nullable=False)
    email_verified = Column(Boolean, default=False, server_default=false(), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    @property
    def has_cv(self) -> bool:
        return bool(self.cv_url)

    categories = relationship("Category", back_populates="owner", cascade="all, delete-orphan")
    expenses = relationship("Expense", back_populates="owner", cascade="all, delete-orphan")
    medications = relationship("Medication", back_populates="owner", cascade="all, delete-orphan")
    gross_incomes = relationship("GrossIncome", back_populates="owner", cascade="all, delete-orphan")
    savings = relationship("Saving", back_populates="owner", cascade="all, delete-orphan")


class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    owner = relationship("User", back_populates="categories")
    # No delete cascade: deleting a category un-categorizes its expenses/medications instead of destroying them.
    expenses = relationship("Expense", back_populates="category")
    medications = relationship("Medication", back_populates="category")


class GrossIncome(Base):
    __tablename__ = "gross_incomes"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)  # e.g., "Full-time Job Salary", "Freelance Project"
    amount = Column(Float, default=0.0, nullable=False)  # Gross income amount
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    owner = relationship("User", back_populates="gross_incomes")
    tax_deductions = relationship("TaxDeduction", back_populates="gross_income", cascade="all, delete-orphan")
    expenses = relationship("Expense", back_populates="gross_income_rel")
    medications = relationship("Medication", back_populates="gross_income_rel")


class Expense(Base):
    __tablename__ = "expenses"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)  # e.g., "Chase Sapphire Credit Card Expenses"
    gross_income = Column(Float, default=0.0, nullable=False)
    net_income = Column(Float, default=0.0, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True, index=True)
    gross_income_id = Column(Integer, ForeignKey("gross_incomes.id"), nullable=True, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    owner = relationship("User", back_populates="expenses")
    category = relationship("Category", back_populates="expenses")
    gross_income_rel = relationship("GrossIncome", back_populates="expenses")
    items = relationship("ExpenseItem", back_populates="expense", cascade="all, delete-orphan")
    tax_deductions = relationship("TaxDeduction", back_populates="expense", cascade="all, delete-orphan")
    # No delete cascade: deleting an expense unlinks its savings instead of destroying them.
    savings = relationship("Saving", back_populates="expense")


class ExpenseItem(Base):
    __tablename__ = "expense_items"

    id = Column(Integer, primary_key=True, index=True)
    expense_id = Column(Integer, ForeignKey("expenses.id"), nullable=False, index=True)
    description = Column(String, nullable=False)
    amount = Column(Float, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    expense = relationship("Expense", back_populates="items")


class Saving(Base):
    __tablename__ = "savings"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    expense_id = Column(Integer, ForeignKey("expenses.id"), nullable=True, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    owner = relationship("User", back_populates="savings")
    expense = relationship("Expense", back_populates="savings")
    items = relationship("SavingItem", back_populates="saving", cascade="all, delete-orphan")


class SavingItem(Base):
    __tablename__ = "saving_items"

    id = Column(Integer, primary_key=True, index=True)
    saving_id = Column(Integer, ForeignKey("savings.id"), nullable=False, index=True)
    description = Column(String, nullable=False)
    amount = Column(Float, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    saving = relationship("Saving", back_populates="items")


class TaxDeduction(Base):
    __tablename__ = "tax_deductions"

    id = Column(Integer, primary_key=True, index=True)
    expense_id = Column(Integer, ForeignKey("expenses.id"), nullable=True, index=True)
    gross_income_id = Column(Integer, ForeignKey("gross_incomes.id"), nullable=True, index=True)
    description = Column(String, nullable=False)
    amount = Column(Float, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    expense = relationship("Expense", back_populates="tax_deductions")
    gross_income = relationship("GrossIncome", back_populates="tax_deductions")


class Medication(Base):
    __tablename__ = "medications"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    cost = Column(Float, nullable=False)  # Cost of the medicine
    doses_taken = Column(Integer, default=0, nullable=False)  # How many already taken
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True, index=True)
    gross_income_id = Column(Integer, ForeignKey("gross_incomes.id"), nullable=True, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    owner = relationship("User", back_populates="medications")
    category = relationship("Category", back_populates="medications")
    gross_income_rel = relationship("GrossIncome", back_populates="medications")


class PortfolioConfig(Base):
    __tablename__ = "portfolio_config"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String, nullable=False, default="Mark Philip V. Parayno")
    headline = Column(String, nullable=False, default="Software Engineer | Mobile & Web Applications")
    location = Column(String, nullable=False, default="San Juan City, Philippines")
    phone = Column(String, nullable=False, default="+63 961 312 8973")
    email = Column(String, nullable=False, default="paraynomarkphilip@gmail.com")
    linkedin_url = Column(String, nullable=False, default="https://www.linkedin.com/in/mark-philip-parayno/")
    github_username = Column(String, nullable=False, default="MarkParayno1004")
    about_summary = Column(
        String,
        nullable=False,
        default=(
            "Software Engineer with production experience building and maintaining mobile and web applications "
            "for a large retail enterprise. Strong across Flutter, Svelte, React, Django, and Laravel. Focused on "
            "shipping reliable features, improving performance, and keeping delivery pipelines healthy in Agile teams."
        ),
    )
    skills = Column(JSON, nullable=True)
    experience = Column(JSON, nullable=True)
    education = Column(JSON, nullable=True)
    theme_config = Column(JSON, nullable=True)
    cv_url = Column(String, nullable=True)  # private storage key, never exposed
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    @property
    def has_cv(self) -> bool:
        return bool(self.cv_url)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    # Plain integer, no FK: the record must survive (and keep pointing at) a deleted user.
    actor_user_id = Column(Integer, nullable=True, index=True)
    action = Column(String, nullable=False, index=True)
    target_type = Column(String, nullable=True)
    target_id = Column(String, nullable=True)
    details = Column(JSON, nullable=True)
    ip = Column(String, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)

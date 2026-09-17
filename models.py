from datetime import datetime, timezone
from sqlalchemy import JSON, Boolean, Column, DateTime, Float, ForeignKey, Integer, String
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
    token = Column(String, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    expenses = relationship("Expense", back_populates="owner", cascade="all, delete-orphan")
    medications = relationship("Medication", back_populates="owner", cascade="all, delete-orphan")


class Expense(Base):
    __tablename__ = "expenses"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)  # e.g., "Chase Sapphire Credit Card Expenses"
    gross_income = Column(Float, default=0.0, nullable=False)
    net_income = Column(Float, default=0.0, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    owner = relationship("User", back_populates="expenses")
    items = relationship("ExpenseItem", back_populates="expense", cascade="all, delete-orphan")
    tax_deductions = relationship("TaxDeduction", back_populates="expense", cascade="all, delete-orphan")


class ExpenseItem(Base):
    __tablename__ = "expense_items"

    id = Column(Integer, primary_key=True, index=True)
    expense_id = Column(Integer, ForeignKey("expenses.id"), nullable=False)
    description = Column(String, nullable=False)
    amount = Column(Float, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    expense = relationship("Expense", back_populates="items")


class TaxDeduction(Base):
    __tablename__ = "tax_deductions"

    id = Column(Integer, primary_key=True, index=True)
    expense_id = Column(Integer, ForeignKey("expenses.id"), nullable=False)
    description = Column(String, nullable=False)
    amount = Column(Float, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    expense = relationship("Expense", back_populates="tax_deductions")


class Medication(Base):
    __tablename__ = "medications"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    cost = Column(Float, nullable=False)  # Cost of the medicine
    doses_taken = Column(Integer, default=0, nullable=False)  # How many already taken
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    owner = relationship("User", back_populates="medications")


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
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


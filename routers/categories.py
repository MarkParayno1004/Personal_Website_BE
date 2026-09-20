from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from database import get_db
from dependencies import get_current_user
from models import Category, Expense, ExpenseItem, Medication, TaxDeduction, User
from routers.expenses import build_expense_response, invalidate_user_expenses_cache
from routers.medications import build_medication_response, invalidate_user_medications_cache
from schemas import (
    CategoryCreate,
    CategoryResponse,
    CategoryUpdate,
    ExpenseCreate,
    ExpenseResponse,
    MedicationCreate,
    MedicationResponse,
)

from redis_cache import delete_cache_pattern, get_cache, set_cache

router = APIRouter(prefix="/categories", tags=["Categories"])


def invalidate_user_categories_cache(user_id: int):
    delete_cache_pattern(f"cache:*category*user:{user_id}*")
    invalidate_user_expenses_cache(user_id)
    invalidate_user_medications_cache(user_id)


def build_category_response(category: Category) -> CategoryResponse:
    expenses_res = [build_expense_response(exp) for exp in category.expenses]
    medications_res = [build_medication_response(med) for med in category.medications]

    total_expenses_amount = round(sum(exp.total_expenses for exp in expenses_res), 2)
    total_medications_amount = round(sum(med.total_spent for med in medications_res), 2)
    total_amount = round(total_expenses_amount + total_medications_amount, 2)

    return CategoryResponse(
        id=category.id,
        title=category.title,
        user_id=category.user_id,
        expenses=expenses_res,
        medications=medications_res,
        total_expenses_amount=total_expenses_amount,
        total_medications_amount=total_medications_amount,
        total_amount=total_amount,
        created_at=category.created_at,
    )


@router.post("/", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED)
def create_category(
    category_in: CategoryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Create a new category for the authenticated user, optionally with nested
    expenses and medications initialized inline.
    """
    category = Category(
        title=category_in.title,
        user_id=current_user.id,
    )
    db.add(category)
    db.commit()
    db.refresh(category)

    # Inline creation of expenses if provided
    for exp_in in category_in.expenses:
        total_deductions = sum(d.amount for d in exp_in.tax_deductions)
        if exp_in.net_income is not None:
            computed_net_income = exp_in.net_income
        elif exp_in.gross_income and exp_in.gross_income > 0.0:
            computed_net_income = round(exp_in.gross_income - total_deductions, 2)
        else:
            computed_net_income = 0.0

        expense = Expense(
            title=exp_in.title,
            gross_income=exp_in.gross_income or 0.0,
            net_income=computed_net_income,
            category_id=category.id,
            user_id=current_user.id,
        )
        db.add(expense)
        db.commit()
        db.refresh(expense)

        for item in exp_in.items:
            expense_item = ExpenseItem(
                expense_id=expense.id,
                description=item.description,
                amount=item.amount,
            )
            db.add(expense_item)

        for deduction in exp_in.tax_deductions:
            tax_deduction = TaxDeduction(
                expense_id=expense.id,
                description=deduction.description,
                amount=deduction.amount,
            )
            db.add(tax_deduction)

    # Inline creation of medications if provided
    for med_in in category_in.medications:
        med = Medication(
            name=med_in.name,
            cost=med_in.cost,
            doses_taken=med_in.doses_taken,
            category_id=category.id,
            user_id=current_user.id,
        )
        db.add(med)

    db.commit()
    db.refresh(category)

    invalidate_user_categories_cache(current_user.id)
    return build_category_response(category)


@router.get("/", response_model=list[CategoryResponse])
def get_categories(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve all categories and their nested expenses and medications for the current user."""
    cache_key = f"cache:categories:user:{current_user.id}"
    cached = get_cache(cache_key)
    if cached:
        return [CategoryResponse(**item) for item in cached]

    categories = (
        db.query(Category)
        .filter(Category.user_id == current_user.id)
        .order_by(Category.created_at.desc())
        .all()
    )
    result = [build_category_response(cat) for cat in categories]
    set_cache(cache_key, [item.model_dump(mode="json") for item in result])
    return result


@router.get("/{category_id}", response_model=CategoryResponse)
def get_category(
    category_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve details for a specific category by ID."""
    cache_key = f"cache:category:{category_id}:user:{current_user.id}"
    cached = get_cache(cache_key)
    if cached:
        return CategoryResponse(**cached)

    category = (
        db.query(Category)
        .filter(Category.id == category_id, Category.user_id == current_user.id)
        .first()
    )
    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category not found",
        )
    result = build_category_response(category)
    set_cache(cache_key, result.model_dump(mode="json"))
    return result


@router.patch("/{category_id}", response_model=CategoryResponse)
def update_category(
    category_id: int,
    category_in: CategoryUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update title of an existing category."""
    category = (
        db.query(Category)
        .filter(Category.id == category_id, Category.user_id == current_user.id)
        .first()
    )
    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category not found",
        )

    if category_in.title is not None:
        category.title = category_in.title

    db.commit()
    db.refresh(category)

    invalidate_user_categories_cache(current_user.id)
    return build_category_response(category)


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(
    category_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Delete an entire category and cascade-delete all its associated expenses
    and medications.
    """
    category = (
        db.query(Category)
        .filter(Category.id == category_id, Category.user_id == current_user.id)
        .first()
    )
    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category not found",
        )
    db.delete(category)
    db.commit()

    invalidate_user_categories_cache(current_user.id)
    return None


@router.post("/{category_id}/expenses", response_model=ExpenseResponse, status_code=status.HTTP_201_CREATED)
def create_expense_in_category(
    category_id: int,
    expense_in: ExpenseCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new expense sheet directly inside the specified category."""
    category = (
        db.query(Category)
        .filter(Category.id == category_id, Category.user_id == current_user.id)
        .first()
    )
    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category not found",
        )

    total_deductions = sum(d.amount for d in expense_in.tax_deductions)
    if expense_in.net_income is not None:
        computed_net_income = expense_in.net_income
    elif expense_in.gross_income and expense_in.gross_income > 0.0:
        computed_net_income = round(expense_in.gross_income - total_deductions, 2)
    else:
        computed_net_income = 0.0

    expense = Expense(
        title=expense_in.title,
        gross_income=expense_in.gross_income or 0.0,
        net_income=computed_net_income,
        category_id=category.id,
        user_id=current_user.id,
    )
    db.add(expense)
    db.commit()
    db.refresh(expense)

    for item in expense_in.items:
        expense_item = ExpenseItem(
            expense_id=expense.id,
            description=item.description,
            amount=item.amount,
        )
        db.add(expense_item)

    for deduction in expense_in.tax_deductions:
        tax_deduction = TaxDeduction(
            expense_id=expense.id,
            description=deduction.description,
            amount=deduction.amount,
        )
        db.add(tax_deduction)

    db.commit()
    db.refresh(expense)

    invalidate_user_categories_cache(current_user.id)
    return build_expense_response(expense)


@router.post("/{category_id}/medications", response_model=MedicationResponse, status_code=status.HTTP_201_CREATED)
def create_medication_in_category(
    category_id: int,
    med_in: MedicationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new medication directly inside the specified category."""
    category = (
        db.query(Category)
        .filter(Category.id == category_id, Category.user_id == current_user.id)
        .first()
    )
    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category not found",
        )

    med = Medication(
        name=med_in.name,
        cost=med_in.cost,
        doses_taken=med_in.doses_taken,
        category_id=category.id,
        user_id=current_user.id,
    )
    db.add(med)
    db.commit()
    db.refresh(med)

    invalidate_user_categories_cache(current_user.id)
    return build_medication_response(med)

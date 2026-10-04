from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from database import get_db
from dependencies import get_current_user
from models import Category, Expense, ExpenseItem, Medication, TaxDeduction, User
from routers.expenses import build_expense_response, invalidate_user_expenses_cache
from routers.medications import build_medication_response, invalidate_user_medications_cache
from schemas import (
    CategoryCreate,
    CategoryLinkItems,
    CategoryResponse,
    CategoryUnlinkItems,
    CategoryUpdate,
    ExpenseCreate,
    ExpenseResponse,
    MedicationCreate,
    MedicationResponse,
)

from redis_cache import delete_cache_pattern, get_cache, set_cache

router = APIRouter(prefix="/categories", tags=["Categories"])
HTTP_EXCEPTION_ERROR_EXPENSES = "One or more expenses not found"
HTTP_EXCEPTION_ERROR_MEDICATIONS = "One or more medications not found"
HTTP_EXCEPTION_ERROR_CATEGORY_NOT_FOUND = "Category not found"


def invalidate_user_categories_cache(user_id: int) -> None:
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


def get_user_category_or_404(db: Session, category_id: int, user_id: int) -> Category:
    category = (
        db.query(Category)
        .filter(Category.id == category_id, Category.user_id == user_id)
        .first()
    )
    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=HTTP_EXCEPTION_ERROR_CATEGORY_NOT_FOUND,
        )
    return category


def compute_net_income(gross_income: float | None, net_income: float | None, total_deductions: float) -> float:
    if net_income is not None:
        return net_income
    if gross_income and gross_income > 0.0:
        return round(gross_income - total_deductions, 2)
    return 0.0


def create_inline_expense(db: Session, exp_in: ExpenseCreate, category_id: int, user_id: int) -> Expense:
    total_deductions = sum(d.amount for d in exp_in.tax_deductions)
    computed_net_income = compute_net_income(exp_in.gross_income, exp_in.net_income, total_deductions)

    expense = Expense(
        title=exp_in.title,
        gross_income=exp_in.gross_income or 0.0,
        net_income=computed_net_income,
        category_id=category_id,
        gross_income_id=exp_in.gross_income_id,
        user_id=user_id,
    )
    db.add(expense)
    db.commit()
    db.refresh(expense)

    for item in exp_in.items:
        db.add(ExpenseItem(expense_id=expense.id, description=item.description, amount=item.amount))

    for deduction in exp_in.tax_deductions:
        db.add(TaxDeduction(expense_id=expense.id, description=deduction.description, amount=deduction.amount))

    return expense


def create_inline_medication(db: Session, med_in: MedicationCreate, category_id: int, user_id: int) -> Medication:
    med = Medication(
        name=med_in.name,
        cost=med_in.cost,
        doses_taken=med_in.doses_taken,
        category_id=category_id,
        gross_income_id=med_in.gross_income_id,
        user_id=user_id,
    )
    db.add(med)
    return med


def link_expenses_by_ids(db: Session, expense_ids: list[int], category_id: int, user_id: int) -> None:
    if not expense_ids:
        return
    existing_expenses = (
        db.query(Expense)
        .filter(Expense.id.in_(expense_ids), Expense.user_id == user_id)
        .all()
    )
    if len(existing_expenses) != len(set(expense_ids)):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=HTTP_EXCEPTION_ERROR_EXPENSES,
        )
    for exp in existing_expenses:
        exp.category_id = category_id


def link_medications_by_ids(db: Session, medication_ids: list[int], category_id: int, user_id: int) -> None:
    if not medication_ids:
        return
    existing_medications = (
        db.query(Medication)
        .filter(Medication.id.in_(medication_ids), Medication.user_id == user_id)
        .all()
    )
    if len(existing_medications) != len(set(medication_ids)):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=HTTP_EXCEPTION_ERROR_MEDICATIONS,
        )
    for med in existing_medications:
        med.category_id = category_id


def unlink_expenses_by_ids(db: Session, expense_ids: list[int], category_id: int, user_id: int) -> None:
    if not expense_ids:
        return
    expenses = (
        db.query(Expense)
        .filter(
            Expense.id.in_(expense_ids),
            Expense.category_id == category_id,
            Expense.user_id == user_id,
        )
        .all()
    )
    if len(expenses) != len(set(expense_ids)):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="One or more expenses not found in this category",
        )
    for exp in expenses:
        exp.category_id = None


def unlink_medications_by_ids(db: Session, medication_ids: list[int], category_id: int, user_id: int) -> None:
    if not medication_ids:
        return
    medications = (
        db.query(Medication)
        .filter(
            Medication.id.in_(medication_ids),
            Medication.category_id == category_id,
            Medication.user_id == user_id,
        )
        .all()
    )
    if len(medications) != len(set(medication_ids)):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="One or more medications not found in this category",
        )
    for med in medications:
        med.category_id = None


def update_category_expenses(db: Session, category: Category, expense_ids: list[int] | None, user_id: int) -> None:
    if expense_ids is None:
        return
    if expense_ids:
        link_expenses_by_ids(db, expense_ids, category.id, user_id)
    else:
        for exp in category.expenses:
            exp.category_id = None


def update_category_medications(db: Session, category: Category, medication_ids: list[int] | None, user_id: int) -> None:
    if medication_ids is None:
        return
    if medication_ids:
        link_medications_by_ids(db, medication_ids, category.id, user_id)
    else:
        for med in category.medications:
            med.category_id = None


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

    link_expenses_by_ids(db, category_in.expense_ids, category.id, current_user.id)
    link_medications_by_ids(db, category_in.medication_ids, category.id, current_user.id)

    for exp_in in category_in.expenses:
        create_inline_expense(db, exp_in, category.id, current_user.id)

    for med_in in category_in.medications:
        create_inline_medication(db, med_in, category.id, current_user.id)

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

    category = get_user_category_or_404(db, category_id, current_user.id)
    result = build_category_response(category)
    set_cache(cache_key, result.model_dump(mode="json"))
    return result


@router.patch("/{category_id}", response_model=CategoryResponse)
@router.put("/{category_id}", response_model=CategoryResponse)
def update_category(
    category_id: int,
    category_in: CategoryUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update title or linked items of an existing category."""
    category = get_user_category_or_404(db, category_id, current_user.id)

    if category_in.title is not None:
        category.title = category_in.title

    update_category_expenses(db, category, category_in.expense_ids, current_user.id)
    update_category_medications(db, category, category_in.medication_ids, current_user.id)

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
    category = get_user_category_or_404(db, category_id, current_user.id)
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
    category = get_user_category_or_404(db, category_id, current_user.id)
    expense = create_inline_expense(db, expense_in, category.id, current_user.id)
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
    category = get_user_category_or_404(db, category_id, current_user.id)
    med = create_inline_medication(db, med_in, category.id, current_user.id)
    db.commit()
    db.refresh(med)

    invalidate_user_categories_cache(current_user.id)
    return build_medication_response(med)


@router.post("/{category_id}/link", response_model=CategoryResponse)
@router.post("/{category_id}/import", response_model=CategoryResponse)
def link_items_to_category(
    category_id: int,
    link_in: CategoryLinkItems,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Link existing expenses and medications to a category by their IDs.
    The database records remain intact with only their category_id updated.
    """
    category = get_user_category_or_404(db, category_id, current_user.id)

    link_expenses_by_ids(db, link_in.expense_ids, category.id, current_user.id)
    link_medications_by_ids(db, link_in.medication_ids, category.id, current_user.id)

    db.commit()
    db.refresh(category)

    invalidate_user_categories_cache(current_user.id)
    return build_category_response(category)


@router.post("/{category_id}/unlink", response_model=CategoryResponse)
def unlink_items_from_category(
    category_id: int,
    unlink_in: CategoryUnlinkItems,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Unlink existing expenses and medications from a category, resetting their category_id to None.
    The database records remain intact as uncategorized items.
    """
    category = get_user_category_or_404(db, category_id, current_user.id)

    unlink_expenses_by_ids(db, unlink_in.expense_ids, category.id, current_user.id)
    unlink_medications_by_ids(db, unlink_in.medication_ids, category.id, current_user.id)

    db.commit()
    db.refresh(category)

    invalidate_user_categories_cache(current_user.id)
    return build_category_response(category)

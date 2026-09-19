from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from database import get_db
from dependencies import get_current_user
from models import Expense, ExpenseItem, TaxDeduction, User
from schemas import (
    ExpenseCreate,
    ExpenseItemCreate,
    ExpenseItemResponse,
    ExpenseResponse,
    ExpenseUpdate,
    TaxDeductionCreate,
    TaxDeductionResponse,
)

from redis_cache import delete_cache_pattern, get_cache, set_cache

router = APIRouter(prefix="/expenses", tags=["Expenses"])


def invalidate_user_expenses_cache(user_id: int):
    delete_cache_pattern(f"cache:*expense*user:{user_id}*")


def build_expense_response(expense: Expense) -> ExpenseResponse:
    items_response = [
        ExpenseItemResponse(
            id=item.id,
            description=item.description,
            amount=item.amount,
        )
        for item in expense.items
    ]
    tax_deductions_response = [
        TaxDeductionResponse(
            id=deduction.id,
            description=deduction.description,
            amount=deduction.amount,
        )
        for deduction in expense.tax_deductions
    ]
    total_expenses = sum(item.amount for item in expense.items)
    total_tax_deductions = sum(deduction.amount for deduction in expense.tax_deductions)
    gross_income = expense.gross_income or 0.0

    # If net_income is explicitly set and non-zero, use it.
    # Otherwise, if gross_income > 0, compute net_income = gross_income - total_tax_deductions.
    if expense.net_income is not None and expense.net_income != 0.0:
        net_income = expense.net_income
    elif gross_income > 0.0:
        net_income = round(gross_income - total_tax_deductions, 2)
    else:
        net_income = expense.net_income or 0.0

    remaining_income = round(net_income - total_expenses, 2)

    return ExpenseResponse(
        id=expense.id,
        title=expense.title,
        gross_income=round(gross_income, 2),
        net_income=round(net_income, 2),
        total_tax_deductions=round(total_tax_deductions, 2),
        total_expenses=round(total_expenses, 2),
        total_amount=round(total_expenses, 2),
        remaining_income=round(remaining_income, 2),
        items=items_response,
        tax_deductions=tax_deductions_response,
        created_at=expense.created_at,
    )


@router.post("/", response_model=ExpenseResponse, status_code=status.HTTP_201_CREATED)
def create_expense(
    expense_in: ExpenseCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Create a new expense sheet with title, gross income, net income,
    multiple expense items, and multiple tax deductions.
    """
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

    invalidate_user_expenses_cache(current_user.id)
    return build_expense_response(expense)


@router.get("/", response_model=list[ExpenseResponse])
def get_expenses(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve all expenses with items, tax deductions, and computed totals for the current user."""
    cache_key = f"cache:expenses:user:{current_user.id}"
    cached = get_cache(cache_key)
    if cached:
        return [ExpenseResponse(**item) for item in cached]

    expenses = (
        db.query(Expense)
        .filter(Expense.user_id == current_user.id)
        .order_by(Expense.created_at.desc())
        .all()
    )
    result = [build_expense_response(exp) for exp in expenses]
    set_cache(cache_key, [item.model_dump(mode="json") for item in result])
    return result


@router.get("/{expense_id}", response_model=ExpenseResponse)
def get_expense(
    expense_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve details for a specific expense group by ID."""
    cache_key = f"cache:expense:{expense_id}:user:{current_user.id}"
    cached = get_cache(cache_key)
    if cached:
        return ExpenseResponse(**cached)

    expense = (
        db.query(Expense)
        .filter(Expense.id == expense_id, Expense.user_id == current_user.id)
        .first()
    )
    if not expense:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Expense not found",
        )
    result = build_expense_response(expense)
    set_cache(cache_key, result.model_dump(mode="json"))
    return result


@router.patch("/{expense_id}", response_model=ExpenseResponse)
def update_expense(
    expense_id: int,
    expense_in: ExpenseUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update title, gross income, or net income of an existing expense sheet."""
    expense = (
        db.query(Expense)
        .filter(Expense.id == expense_id, Expense.user_id == current_user.id)
        .first()
    )
    if not expense:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Expense not found",
        )

    if expense_in.title is not None:
        expense.title = expense_in.title
    if expense_in.gross_income is not None:
        expense.gross_income = expense_in.gross_income
    if expense_in.net_income is not None:
        expense.net_income = expense_in.net_income

    db.commit()
    db.refresh(expense)

    invalidate_user_expenses_cache(current_user.id)
    return build_expense_response(expense)


@router.post("/{expense_id}/items", response_model=ExpenseResponse)
def add_item_to_expense(
    expense_id: int,
    item_in: ExpenseItemCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Add an expense item to an existing expense group."""
    expense = (
        db.query(Expense)
        .filter(Expense.id == expense_id, Expense.user_id == current_user.id)
        .first()
    )
    if not expense:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Expense not found",
        )

    new_item = ExpenseItem(
        expense_id=expense.id,
        description=item_in.description,
        amount=item_in.amount,
    )
    db.add(new_item)
    db.commit()
    db.refresh(expense)

    invalidate_user_expenses_cache(current_user.id)
    return build_expense_response(expense)


@router.delete("/{expense_id}/items/{item_id}", response_model=ExpenseResponse)
def delete_expense_item(
    expense_id: int,
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete an expense item from an existing expense group."""
    expense = (
        db.query(Expense)
        .filter(Expense.id == expense_id, Expense.user_id == current_user.id)
        .first()
    )
    if not expense:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Expense not found",
        )

    item = (
        db.query(ExpenseItem)
        .filter(ExpenseItem.id == item_id, ExpenseItem.expense_id == expense.id)
        .first()
    )
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Expense item not found",
        )

    db.delete(item)
    db.commit()
    db.refresh(expense)

    invalidate_user_expenses_cache(current_user.id)
    return build_expense_response(expense)


@router.post("/{expense_id}/tax-deductions", response_model=ExpenseResponse)
def add_tax_deduction_to_expense(
    expense_id: int,
    deduction_in: TaxDeductionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Add a tax deduction item to an existing expense group."""
    expense = (
        db.query(Expense)
        .filter(Expense.id == expense_id, Expense.user_id == current_user.id)
        .first()
    )
    if not expense:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Expense not found",
        )

    old_deductions = sum(d.amount for d in expense.tax_deductions)
    new_deduction = TaxDeduction(
        expense_id=expense.id,
        description=deduction_in.description,
        amount=deduction_in.amount,
    )
    db.add(new_deduction)

    # Keep auto-calculated net_income in sync if it matched gross_income - old_deductions
    if expense.gross_income and expense.net_income == round(expense.gross_income - old_deductions, 2):
        expense.net_income = round(expense.gross_income - (old_deductions + deduction_in.amount), 2)

    db.commit()
    db.refresh(expense)

    invalidate_user_expenses_cache(current_user.id)
    return build_expense_response(expense)


@router.delete("/{expense_id}/tax-deductions/{deduction_id}", response_model=ExpenseResponse)
def delete_tax_deduction(
    expense_id: int,
    deduction_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a tax deduction item from an existing expense group."""
    expense = (
        db.query(Expense)
        .filter(Expense.id == expense_id, Expense.user_id == current_user.id)
        .first()
    )
    if not expense:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Expense not found",
        )

    deduction = (
        db.query(TaxDeduction)
        .filter(TaxDeduction.id == deduction_id, TaxDeduction.expense_id == expense.id)
        .first()
    )
    if not deduction:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tax deduction not found",
        )

    old_deductions = sum(d.amount for d in expense.tax_deductions)
    if expense.gross_income and expense.net_income == round(expense.gross_income - old_deductions, 2):
        expense.net_income = round(expense.gross_income - (old_deductions - deduction.amount), 2)

    db.delete(deduction)
    db.commit()
    db.refresh(expense)

    invalidate_user_expenses_cache(current_user.id)
    return build_expense_response(expense)


@router.delete("/{expense_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_expense(
    expense_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete an entire expense group and its associated items and tax deductions."""
    expense = (
        db.query(Expense)
        .filter(Expense.id == expense_id, Expense.user_id == current_user.id)
        .first()
    )
    if not expense:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Expense not found",
        )
    db.delete(expense)
    db.commit()

    invalidate_user_expenses_cache(current_user.id)
    return None

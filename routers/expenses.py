from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session, selectinload
from database import get_db
from dependencies import get_current_user
from models import Category, Expense, ExpenseItem, GrossIncome, Saving, TaxDeduction, User
from pagination import Page, page_params, paginate
from schemas import (
    ExpenseCreate,
    ExpenseItemCreate,
    ExpenseItemResponse,
    ExpenseResponse,
    ExpenseUpdate,
    SavingItemResponse,
    SavingResponse,
    TaxDeductionCreate,
    TaxDeductionResponse,
)

from redis_cache import delete_cache_pattern, get_cache, set_cache

router = APIRouter(prefix="/expenses", tags=["Expenses"])

# Everything build_expense_response walks; reuse as sub-options wherever expenses are nested.
EXPENSE_LOAD_OPTIONS = (
    selectinload(Expense.items),
    selectinload(Expense.tax_deductions),
    selectinload(Expense.savings).selectinload(Saving.items),
)
HTTP_EXCEPTION_ERROR_EXPENSE_NOT_FOUND = "Expense not found"
HTTP_EXCEPTION_ERROR_CATEGORY_NOT_FOUND = "Category not found"
HTTP_EXCEPTION_ERROR_INCOME_NOT_FOUND = "Gross income record not found"


def invalidate_user_expenses_cache(user_id: int):
    delete_cache_pattern(f"cache:*expense*user:{user_id}*")
    delete_cache_pattern(f"cache:*category*user:{user_id}*")
    delete_cache_pattern(f"cache:*income*user:{user_id}*")
    delete_cache_pattern(f"cache:*saving*user:{user_id}*")


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
    savings_response = [
        SavingResponse(
            id=saving.id,
            title=saving.title,
            expense_id=saving.expense_id,
            user_id=saving.user_id,
            total_amount=round(sum(item.amount for item in (saving.items or [])), 2),
            items=[
                SavingItemResponse(
                    id=item.id,
                    saving_id=item.saving_id,
                    description=item.description,
                    amount=item.amount,
                    created_at=item.created_at,
                )
                for item in (saving.items or [])
            ],
            created_at=saving.created_at,
        )
        for saving in (expense.savings or [])
    ]
    total_expenses = sum(item.amount for item in expense.items)
    total_tax_deductions = sum(deduction.amount for deduction in expense.tax_deductions)
    total_savings = sum(saving.total_amount for saving in savings_response)
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
        category_id=expense.category_id,
        gross_income_id=expense.gross_income_id,
        items=items_response,
        tax_deductions=tax_deductions_response,
        savings=savings_response,
        total_savings=round(total_savings, 2),
        created_at=expense.created_at,
    )


def validate_expense_category(db: Session, category_id: int | None, user_id: int) -> None:
    if category_id is not None:
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


def validate_expense_gross_income(db: Session, gross_income_id: int | None, user_id: int) -> None:
    if gross_income_id is not None:
        gross_inc = (
            db.query(GrossIncome)
            .filter(GrossIncome.id == gross_income_id, GrossIncome.user_id == user_id)
            .first()
        )
        if not gross_inc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=HTTP_EXCEPTION_ERROR_INCOME_NOT_FOUND,
            )


@router.post("/", response_model=ExpenseResponse, status_code=status.HTTP_201_CREATED)
def create_expense(
    expense_in: ExpenseCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Create a new expense sheet with title, optional gross income ID / amount, net income,
    multiple expense items, and multiple tax deductions.
    """
    validate_expense_category(db, expense_in.category_id, current_user.id)
    validate_expense_gross_income(db, expense_in.gross_income_id, current_user.id)

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
        category_id=expense_in.category_id,
        gross_income_id=expense_in.gross_income_id,
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
    response: Response,
    page: Page = Depends(page_params),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List the current user's expenses with items, deductions and totals. Paginated; total in X-Total-Count."""
    query = (
        db.query(Expense)
        .filter(Expense.user_id == current_user.id)
        .options(*EXPENSE_LOAD_OPTIONS)
        .order_by(Expense.created_at.desc(), Expense.id.desc())
    )
    return paginate(
        query, page, response, build_expense_response, ExpenseResponse,
        cache_key=f"cache:expenses:user:{current_user.id}",
    )


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
            detail=HTTP_EXCEPTION_ERROR_EXPENSE_NOT_FOUND,
        )
    result = build_expense_response(expense)
    set_cache(cache_key, result.model_dump(mode="json"))
    return result


@router.patch("/{expense_id}", response_model=ExpenseResponse)
@router.put("/{expense_id}", response_model=ExpenseResponse)
def update_expense(
    expense_id: int,
    expense_in: ExpenseUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update title, gross income, net income, category, gross income link, items, or deductions of an existing expense sheet."""
    expense = (
        db.query(Expense)
        .filter(Expense.id == expense_id, Expense.user_id == current_user.id)
        .first()
    )
    if not expense:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=HTTP_EXCEPTION_ERROR_EXPENSE_NOT_FOUND,
        )

    if expense_in.title is not None:
        expense.title = expense_in.title
    if expense_in.gross_income is not None:
        expense.gross_income = expense_in.gross_income
    if expense_in.net_income is not None:
        expense.net_income = expense_in.net_income

    if "category_id" in expense_in.model_fields_set:
        validate_expense_category(db, expense_in.category_id, current_user.id)
        expense.category_id = expense_in.category_id

    if "gross_income_id" in expense_in.model_fields_set:
        validate_expense_gross_income(db, expense_in.gross_income_id, current_user.id)
        expense.gross_income_id = expense_in.gross_income_id

    if expense_in.items is not None:
        db.query(ExpenseItem).filter(ExpenseItem.expense_id == expense.id).delete()
        for item in expense_in.items:
            db.add(ExpenseItem(expense_id=expense.id, description=item.description, amount=item.amount))

    if expense_in.tax_deductions is not None:
        db.query(TaxDeduction).filter(TaxDeduction.expense_id == expense.id).delete()
        for deduction in expense_in.tax_deductions:
            db.add(TaxDeduction(expense_id=expense.id, description=deduction.description, amount=deduction.amount))

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
            detail=HTTP_EXCEPTION_ERROR_EXPENSE_NOT_FOUND,
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
            detail=HTTP_EXCEPTION_ERROR_EXPENSE_NOT_FOUND,
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
            detail=HTTP_EXCEPTION_ERROR_EXPENSE_NOT_FOUND,
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
            detail=HTTP_EXCEPTION_ERROR_EXPENSE_NOT_FOUND,
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
            detail=HTTP_EXCEPTION_ERROR_EXPENSE_NOT_FOUND,
        )
    db.delete(expense)
    db.commit()

    invalidate_user_expenses_cache(current_user.id)
    return None

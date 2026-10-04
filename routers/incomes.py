from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from database import get_db
from dependencies import get_current_user
from models import Expense, GrossIncome, Medication, TaxDeduction, User
from routers.expenses import build_expense_response, invalidate_user_expenses_cache
from routers.medications import build_medication_response, invalidate_user_medications_cache
from schemas import (
    GrossIncomeCreate,
    GrossIncomeLinkItems,
    GrossIncomeResponse,
    GrossIncomeUnlinkItems,
    GrossIncomeUpdate,
    TaxDeductionCreate,
    TaxDeductionResponse,
)

from redis_cache import delete_cache_pattern, get_cache, set_cache

router = APIRouter(prefix="/incomes", tags=["Gross Incomes"])
HTTP_EXCEPTION_ERROR_INCOME_NOT_FOUND = "Gross income record not found"
HTTP_EXCEPTION_ERROR_EXPENSES = "One or more expenses not found"
HTTP_EXCEPTION_ERROR_MEDICATIONS = "One or more medications not found"
HTTP_EXCEPTION_ERROR_DEDUCTION_NOT_FOUND = "Tax deduction not found"


def invalidate_user_incomes_cache(user_id: int) -> None:
    delete_cache_pattern(f"cache:*income*user:{user_id}*")
    invalidate_user_expenses_cache(user_id)
    invalidate_user_medications_cache(user_id)
    delete_cache_pattern(f"cache:*category*user:{user_id}*")


def build_gross_income_response(income: GrossIncome) -> GrossIncomeResponse:
    tax_deductions_res = [
        TaxDeductionResponse(
            id=d.id,
            description=d.description,
            amount=d.amount,
        )
        for d in income.tax_deductions
    ]
    expenses_res = [build_expense_response(exp) for exp in income.expenses]
    medications_res = [build_medication_response(med) for med in income.medications]

    total_tax_deductions = round(sum(d.amount for d in tax_deductions_res), 2)
    net_income = round((income.amount or 0.0) - total_tax_deductions, 2)
    total_expenses = round(sum(exp.total_expenses for exp in expenses_res), 2)
    total_medications = round(sum(med.total_spent for med in medications_res), 2)
    remaining_income = round(net_income - total_expenses - total_medications, 2)

    return GrossIncomeResponse(
        id=income.id,
        title=income.title,
        amount=round(income.amount or 0.0, 2),
        total_tax_deductions=total_tax_deductions,
        net_income=net_income,
        total_expenses=total_expenses,
        total_medications=total_medications,
        remaining_income=remaining_income,
        user_id=income.user_id,
        tax_deductions=tax_deductions_res,
        expenses=expenses_res,
        medications=medications_res,
        created_at=income.created_at,
    )


def get_user_income_or_404(db: Session, income_id: int, user_id: int) -> GrossIncome:
    income = (
        db.query(GrossIncome)
        .filter(GrossIncome.id == income_id, GrossIncome.user_id == user_id)
        .first()
    )
    if not income:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=HTTP_EXCEPTION_ERROR_INCOME_NOT_FOUND,
        )
    return income


def link_expenses_to_income(db: Session, expense_ids: list[int], income_id: int, user_id: int) -> None:
    if not expense_ids:
        return
    expenses = (
        db.query(Expense)
        .filter(Expense.id.in_(expense_ids), Expense.user_id == user_id)
        .all()
    )
    if len(expenses) != len(set(expense_ids)):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=HTTP_EXCEPTION_ERROR_EXPENSES,
        )
    for exp in expenses:
        exp.gross_income_id = income_id


def link_medications_to_income(db: Session, medication_ids: list[int], income_id: int, user_id: int) -> None:
    if not medication_ids:
        return
    medications = (
        db.query(Medication)
        .filter(Medication.id.in_(medication_ids), Medication.user_id == user_id)
        .all()
    )
    if len(medications) != len(set(medication_ids)):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=HTTP_EXCEPTION_ERROR_MEDICATIONS,
        )
    for med in medications:
        med.gross_income_id = income_id


def unlink_expenses_from_income(db: Session, expense_ids: list[int], income_id: int, user_id: int) -> None:
    if not expense_ids:
        return
    expenses = (
        db.query(Expense)
        .filter(
            Expense.id.in_(expense_ids),
            Expense.gross_income_id == income_id,
            Expense.user_id == user_id,
        )
        .all()
    )
    if len(expenses) != len(set(expense_ids)):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="One or more expenses not found in this income stream",
        )
    for exp in expenses:
        exp.gross_income_id = None


def unlink_medications_from_income(db: Session, medication_ids: list[int], income_id: int, user_id: int) -> None:
    if not medication_ids:
        return
    medications = (
        db.query(Medication)
        .filter(
            Medication.id.in_(medication_ids),
            Medication.gross_income_id == income_id,
            Medication.user_id == user_id,
        )
        .all()
    )
    if len(medications) != len(set(medication_ids)):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="One or more medications not found in this income stream",
        )
    for med in medications:
        med.gross_income_id = None


def update_income_expenses(db: Session, income: GrossIncome, expense_ids: list[int] | None, user_id: int) -> None:
    if expense_ids is None:
        return
    if expense_ids:
        link_expenses_to_income(db, expense_ids, income.id, user_id)
    else:
        for exp in income.expenses:
            exp.gross_income_id = None


def update_income_medications(db: Session, income: GrossIncome, medication_ids: list[int] | None, user_id: int) -> None:
    if medication_ids is None:
        return
    if medication_ids:
        link_medications_to_income(db, medication_ids, income.id, user_id)
    else:
        for med in income.medications:
            med.gross_income_id = None


@router.post("/", response_model=GrossIncomeResponse, status_code=status.HTTP_201_CREATED)
def create_gross_income(
    income_in: GrossIncomeCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Create a centralized gross income record with optional initial tax deductions,
    and optionally link existing expenses and medications.
    """
    income = GrossIncome(
        title=income_in.title,
        amount=income_in.amount or 0.0,
        user_id=current_user.id,
    )
    db.add(income)
    db.commit()
    db.refresh(income)

    for deduction in income_in.tax_deductions:
        tax_deduction = TaxDeduction(
            gross_income_id=income.id,
            description=deduction.description,
            amount=deduction.amount,
        )
        db.add(tax_deduction)

    link_expenses_to_income(db, income_in.expense_ids, income.id, current_user.id)
    link_medications_to_income(db, income_in.medication_ids, income.id, current_user.id)

    db.commit()
    db.refresh(income)

    invalidate_user_incomes_cache(current_user.id)
    return build_gross_income_response(income)


@router.get("/", response_model=list[GrossIncomeResponse])
def get_gross_incomes(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve all gross income streams with deductions and linked expenses/medications for the current user."""
    cache_key = f"cache:incomes:user:{current_user.id}"
    cached = get_cache(cache_key)
    if cached:
        return [GrossIncomeResponse(**item) for item in cached]

    incomes = (
        db.query(GrossIncome)
        .filter(GrossIncome.user_id == current_user.id)
        .order_by(GrossIncome.created_at.desc())
        .all()
    )
    result = [build_gross_income_response(inc) for inc in incomes]
    set_cache(cache_key, [item.model_dump(mode="json") for item in result])
    return result


@router.get("/{income_id}", response_model=GrossIncomeResponse)
def get_gross_income(
    income_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve details for a specific gross income record by ID."""
    cache_key = f"cache:income:{income_id}:user:{current_user.id}"
    cached = get_cache(cache_key)
    if cached:
        return GrossIncomeResponse(**cached)

    income = get_user_income_or_404(db, income_id, current_user.id)
    result = build_gross_income_response(income)
    set_cache(cache_key, result.model_dump(mode="json"))
    return result


@router.patch("/{income_id}", response_model=GrossIncomeResponse)
@router.put("/{income_id}", response_model=GrossIncomeResponse)
def update_gross_income(
    income_id: int,
    income_in: GrossIncomeUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update title, amount, tax deductions, or linked expenses/medications of an existing gross income record."""
    income = get_user_income_or_404(db, income_id, current_user.id)

    if income_in.title is not None:
        income.title = income_in.title
    if income_in.amount is not None:
        income.amount = income_in.amount

    if income_in.tax_deductions is not None:
        db.query(TaxDeduction).filter(TaxDeduction.gross_income_id == income.id).delete()
        for deduction in income_in.tax_deductions:
            db.add(TaxDeduction(gross_income_id=income.id, description=deduction.description, amount=deduction.amount))

    update_income_expenses(db, income, income_in.expense_ids, current_user.id)
    update_income_medications(db, income, income_in.medication_ids, current_user.id)

    db.commit()
    db.refresh(income)

    invalidate_user_incomes_cache(current_user.id)
    return build_gross_income_response(income)


@router.delete("/{income_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_gross_income(
    income_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a gross income stream and cascade-delete its deductions (unlinks linked expenses and medications)."""
    income = get_user_income_or_404(db, income_id, current_user.id)

    for exp in income.expenses:
        exp.gross_income_id = None
    for med in income.medications:
        med.gross_income_id = None

    db.delete(income)
    db.commit()

    invalidate_user_incomes_cache(current_user.id)
    return None


@router.post("/{income_id}/tax-deductions", response_model=GrossIncomeResponse)
def add_tax_deduction_to_gross_income(
    income_id: int,
    deduction_in: TaxDeductionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Add a tax deduction item to a gross income stream."""
    income = get_user_income_or_404(db, income_id, current_user.id)

    new_deduction = TaxDeduction(
        gross_income_id=income.id,
        description=deduction_in.description,
        amount=deduction_in.amount,
    )
    db.add(new_deduction)
    db.commit()
    db.refresh(income)

    invalidate_user_incomes_cache(current_user.id)
    return build_gross_income_response(income)


@router.delete("/{income_id}/tax-deductions/{deduction_id}", response_model=GrossIncomeResponse)
def delete_tax_deduction_from_gross_income(
    income_id: int,
    deduction_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Remove a tax deduction item from a gross income stream."""
    income = get_user_income_or_404(db, income_id, current_user.id)

    deduction = (
        db.query(TaxDeduction)
        .filter(TaxDeduction.id == deduction_id, TaxDeduction.gross_income_id == income.id)
        .first()
    )
    if not deduction:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=HTTP_EXCEPTION_ERROR_DEDUCTION_NOT_FOUND,
        )

    db.delete(deduction)
    db.commit()
    db.refresh(income)

    invalidate_user_incomes_cache(current_user.id)
    return build_gross_income_response(income)


@router.post("/{income_id}/link", response_model=GrossIncomeResponse)
@router.post("/{income_id}/import", response_model=GrossIncomeResponse)
def link_items_to_gross_income(
    income_id: int,
    link_in: GrossIncomeLinkItems,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Link existing expenses and medications to a gross income stream by their IDs."""
    income = get_user_income_or_404(db, income_id, current_user.id)

    link_expenses_to_income(db, link_in.expense_ids, income.id, current_user.id)
    link_medications_to_income(db, link_in.medication_ids, income.id, current_user.id)

    db.commit()
    db.refresh(income)

    invalidate_user_incomes_cache(current_user.id)
    return build_gross_income_response(income)


@router.post("/{income_id}/unlink", response_model=GrossIncomeResponse)
def unlink_items_from_gross_income(
    income_id: int,
    unlink_in: GrossIncomeUnlinkItems,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Unlink existing expenses and medications from a gross income stream, resetting their gross_income_id to None."""
    income = get_user_income_or_404(db, income_id, current_user.id)

    unlink_expenses_from_income(db, unlink_in.expense_ids, income.id, current_user.id)
    unlink_medications_from_income(db, unlink_in.medication_ids, income.id, current_user.id)

    db.commit()
    db.refresh(income)

    invalidate_user_incomes_cache(current_user.id)
    return build_gross_income_response(income)

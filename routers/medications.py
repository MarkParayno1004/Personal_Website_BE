from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session
from database import get_db
from dependencies import get_current_user
from models import Category, GrossIncome, Medication, User
from pagination import Page, page_params, paginate
from schemas import (
    MedicationCreate,
    MedicationDoseLog,
    MedicationResponse,
    MedicationUpdate,
)

from redis_cache import delete_cache_pattern, get_cache, set_cache

router = APIRouter(prefix="/medications", tags=["Medications"])
HTTP_EXCEPTION_ERROR_MEDICATION_NOT_FOUND = "Medication not found"
HTTP_EXCEPTION_ERROR_CATEGORY_NOT_FOUND = "Category not found"
HTTP_EXCEPTION_ERROR_INCOME_NOT_FOUND = "Gross income record not found"


def invalidate_user_medications_cache(user_id: int):
    delete_cache_pattern(f"cache:*medication*user:{user_id}*")
    delete_cache_pattern(f"cache:*category*user:{user_id}*")
    delete_cache_pattern(f"cache:*income*user:{user_id}*")


def build_medication_response(med: Medication) -> MedicationResponse:
    total_spent = round(med.cost * med.doses_taken, 2)
    return MedicationResponse(
        id=med.id,
        name=med.name,
        cost=med.cost,
        doses_taken=med.doses_taken,
        total_spent=total_spent,
        category_id=med.category_id,
        gross_income_id=med.gross_income_id,
    )


def validate_medication_category(db: Session, category_id: int | None, user_id: int) -> None:
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


def validate_medication_gross_income(db: Session, gross_income_id: int | None, user_id: int) -> None:
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


@router.post("/", response_model=MedicationResponse, status_code=status.HTTP_201_CREATED)
def create_medication(
    med_in: MedicationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Register a medication with its cost and initial count of doses already taken,
    with optional category and gross income association.
    """
    validate_medication_category(db, med_in.category_id, current_user.id)
    validate_medication_gross_income(db, med_in.gross_income_id, current_user.id)

    med = Medication(
        name=med_in.name,
        cost=med_in.cost,
        doses_taken=med_in.doses_taken,
        category_id=med_in.category_id,
        gross_income_id=med_in.gross_income_id,
        user_id=current_user.id,
    )
    db.add(med)
    db.commit()
    db.refresh(med)

    invalidate_user_medications_cache(current_user.id)
    return build_medication_response(med)


@router.get("/", response_model=list[MedicationResponse])
def get_medications(
    response: Response,
    page: Page = Depends(page_params),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    List medications tracked by the user, showing medicine cost,
    doses already taken, and total expenditure. Paginated; total in X-Total-Count.
    """
    query = (
        db.query(Medication)
        .filter(Medication.user_id == current_user.id)
        .order_by(Medication.name.asc(), Medication.id.asc())
    )
    return paginate(
        query, page, response, build_medication_response, MedicationResponse,
        cache_key=f"cache:medications:user:{current_user.id}",
    )


@router.get("/{medication_id}", response_model=MedicationResponse)
def get_medication(
    medication_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get details of a specific medication."""
    cache_key = f"cache:medication:{medication_id}:user:{current_user.id}"
    cached = get_cache(cache_key)
    if cached:
        return MedicationResponse(**cached)

    med = (
        db.query(Medication)
        .filter(Medication.id == medication_id, Medication.user_id == current_user.id)
        .first()
    )
    if not med:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=HTTP_EXCEPTION_ERROR_MEDICATION_NOT_FOUND,
        )
    result = build_medication_response(med)
    set_cache(cache_key, result.model_dump(mode="json"))
    return result


@router.post("/{medication_id}/take", response_model=MedicationResponse)
def log_dose_taken(
    medication_id: int,
    log_in: MedicationDoseLog = MedicationDoseLog(),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Log that one or more doses of the medication were taken,
    incrementing the 'doses_taken' counter.
    """
    med = (
        db.query(Medication)
        .filter(Medication.id == medication_id, Medication.user_id == current_user.id)
        .first()
    )
    if not med:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=HTTP_EXCEPTION_ERROR_MEDICATION_NOT_FOUND,
        )

    med.doses_taken += log_in.doses
    db.commit()
    db.refresh(med)

    invalidate_user_medications_cache(current_user.id)
    return build_medication_response(med)


@router.patch("/{medication_id}", response_model=MedicationResponse)
@router.put("/{medication_id}", response_model=MedicationResponse)
def update_medication(
    medication_id: int,
    update_in: MedicationUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update the cost of the medication, total doses taken, category, or gross income link."""
    med = (
        db.query(Medication)
        .filter(Medication.id == medication_id, Medication.user_id == current_user.id)
        .first()
    )
    if not med:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=HTTP_EXCEPTION_ERROR_MEDICATION_NOT_FOUND,
        )

    if update_in.cost is not None:
        med.cost = update_in.cost
    if update_in.doses_taken is not None:
        med.doses_taken = update_in.doses_taken

    if "category_id" in update_in.model_fields_set:
        validate_medication_category(db, update_in.category_id, current_user.id)
        med.category_id = update_in.category_id

    if "gross_income_id" in update_in.model_fields_set:
        validate_medication_gross_income(db, update_in.gross_income_id, current_user.id)
        med.gross_income_id = update_in.gross_income_id

    db.commit()
    db.refresh(med)

    invalidate_user_medications_cache(current_user.id)
    return build_medication_response(med)


@router.delete("/{medication_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_medication(
    medication_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Remove a tracked medication."""
    med = (
        db.query(Medication)
        .filter(Medication.id == medication_id, Medication.user_id == current_user.id)
        .first()
    )
    if not med:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=HTTP_EXCEPTION_ERROR_MEDICATION_NOT_FOUND,
        )
    db.delete(med)
    db.commit()

    invalidate_user_medications_cache(current_user.id)
    return None

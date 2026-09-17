from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from database import get_db
from dependencies import get_current_user
from models import Medication, User
from schemas import (
    MedicationCreate,
    MedicationDoseLog,
    MedicationResponse,
    MedicationUpdate,
)

router = APIRouter(prefix="/medications", tags=["Medications"])


def build_medication_response(med: Medication) -> MedicationResponse:
    total_spent = round(med.cost * med.doses_taken, 2)
    return MedicationResponse(
        id=med.id,
        name=med.name,
        cost=med.cost,
        doses_taken=med.doses_taken,
        total_spent=total_spent,
    )


@router.post("/", response_model=MedicationResponse, status_code=status.HTTP_201_CREATED)
def create_medication(
    med_in: MedicationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Register a medication with its cost and initial count of doses already taken.
    """
    med = Medication(
        name=med_in.name,
        cost=med_in.cost,
        doses_taken=med_in.doses_taken,
        user_id=current_user.id,
    )
    db.add(med)
    db.commit()
    db.refresh(med)
    return build_medication_response(med)


@router.get("/", response_model=list[MedicationResponse])
def get_medications(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    List all medications tracked by the user, showing medicine cost,
    doses already taken, and total expenditure.
    """
    meds = (
        db.query(Medication)
        .filter(Medication.user_id == current_user.id)
        .order_by(Medication.name.asc())
        .all()
    )
    return [build_medication_response(m) for m in meds]


@router.get("/{medication_id}", response_model=MedicationResponse)
def get_medication(
    medication_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get details of a specific medication."""
    med = (
        db.query(Medication)
        .filter(Medication.id == medication_id, Medication.user_id == current_user.id)
        .first()
    )
    if not med:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Medication not found",
        )
    return build_medication_response(med)


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
            detail="Medication not found",
        )

    med.doses_taken += log_in.doses
    db.commit()
    db.refresh(med)
    return build_medication_response(med)


@router.patch("/{medication_id}", response_model=MedicationResponse)
def update_medication(
    medication_id: int,
    update_in: MedicationUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update the cost of the medication or the total doses taken."""
    med = (
        db.query(Medication)
        .filter(Medication.id == medication_id, Medication.user_id == current_user.id)
        .first()
    )
    if not med:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Medication not found",
        )

    if update_in.cost is not None:
        med.cost = update_in.cost
    if update_in.doses_taken is not None:
        med.doses_taken = update_in.doses_taken

    db.commit()
    db.refresh(med)
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
            detail="Medication not found",
        )
    db.delete(med)
    db.commit()
    return None

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from database import get_db
from dependencies import get_current_user
from models import Expense, Saving, SavingItem, User
from schemas import (
    SavingCreate,
    SavingItemCreate,
    SavingItemResponse,
    SavingLinkExpense,
    SavingResponse,
    SavingUpdate,
)

from redis_cache import delete_cache_pattern, get_cache, set_cache

router = APIRouter(prefix="/savings", tags=["Savings"])
HTTP_EXCEPTION_ERROR_SAVING_NOT_FOUND = "Saving record not found"
HTTP_EXCEPTION_ERROR_EXPENSE_NOT_FOUND = "Expense not found"
HTTP_EXCEPTION_ERROR_SAVING_ITEM_NOT_FOUND = "Saving item not found"


def invalidate_user_savings_cache(user_id: int) -> None:
    delete_cache_pattern(f"cache:*saving*user:{user_id}*")
    delete_cache_pattern(f"cache:*expense*user:{user_id}*")
    delete_cache_pattern(f"cache:*category*user:{user_id}*")
    delete_cache_pattern(f"cache:*income*user:{user_id}*")


def build_saving_response(saving: Saving) -> SavingResponse:
    items_response = [
        SavingItemResponse(
            id=item.id,
            saving_id=item.saving_id,
            description=item.description,
            amount=item.amount,
            created_at=item.created_at,
        )
        for item in (saving.items or [])
    ]
    total_amount = round(sum(item.amount for item in (saving.items or [])), 2)

    return SavingResponse(
        id=saving.id,
        title=saving.title,
        expense_id=saving.expense_id,
        user_id=saving.user_id,
        total_amount=total_amount,
        items=items_response,
        created_at=saving.created_at,
    )


def validate_saving_expense(db: Session, expense_id: int | None, user_id: int) -> None:
    if expense_id is not None:
        expense = (
            db.query(Expense)
            .filter(Expense.id == expense_id, Expense.user_id == user_id)
            .first()
        )
        if not expense:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=HTTP_EXCEPTION_ERROR_EXPENSE_NOT_FOUND,
            )


def get_user_saving_or_404(db: Session, saving_id: int, user_id: int) -> Saving:
    saving = (
        db.query(Saving)
        .filter(Saving.id == saving_id, Saving.user_id == user_id)
        .first()
    )
    if not saving:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=HTTP_EXCEPTION_ERROR_SAVING_NOT_FOUND,
        )
    return saving


@router.post("/", response_model=SavingResponse, status_code=status.HTTP_201_CREATED)
def create_saving(
    saving_in: SavingCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Create a new saving record with optional expense association and inline saving items.
    """
    validate_saving_expense(db, saving_in.expense_id, current_user.id)

    saving = Saving(
        title=saving_in.title,
        expense_id=saving_in.expense_id,
        user_id=current_user.id,
    )
    db.add(saving)
    db.commit()
    db.refresh(saving)

    for item in saving_in.items:
        saving_item = SavingItem(
            saving_id=saving.id,
            description=item.description,
            amount=item.amount,
        )
        db.add(saving_item)

    if saving_in.items:
        db.commit()
        db.refresh(saving)

    invalidate_user_savings_cache(current_user.id)
    return build_saving_response(saving)


@router.get("/", response_model=list[SavingResponse])
def get_savings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve all savings records for the current user."""
    cache_key = f"cache:savings:user:{current_user.id}"
    cached = get_cache(cache_key)
    if cached:
        return [SavingResponse(**item) for item in cached]

    savings = (
        db.query(Saving)
        .filter(Saving.user_id == current_user.id)
        .order_by(Saving.created_at.desc())
        .all()
    )
    result = [build_saving_response(s) for s in savings]
    set_cache(cache_key, [item.model_dump(mode="json") for item in result])
    return result


@router.get("/{saving_id}", response_model=SavingResponse)
def get_saving(
    saving_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve details for a specific saving record by ID."""
    cache_key = f"cache:saving:{saving_id}:user:{current_user.id}"
    cached = get_cache(cache_key)
    if cached:
        return SavingResponse(**cached)

    saving = get_user_saving_or_404(db, saving_id, current_user.id)
    result = build_saving_response(saving)
    set_cache(cache_key, result.model_dump(mode="json"))
    return result


@router.patch("/{saving_id}", response_model=SavingResponse)
@router.put("/{saving_id}", response_model=SavingResponse)
def update_saving(
    saving_id: int,
    saving_in: SavingUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update title, expense link, or items of an existing saving record."""
    saving = get_user_saving_or_404(db, saving_id, current_user.id)

    if saving_in.title is not None:
        saving.title = saving_in.title

    if "expense_id" in saving_in.model_fields_set:
        validate_saving_expense(db, saving_in.expense_id, current_user.id)
        saving.expense_id = saving_in.expense_id

    if saving_in.items is not None:
        db.query(SavingItem).filter(SavingItem.saving_id == saving.id).delete()
        for item in saving_in.items:
            db.add(SavingItem(saving_id=saving.id, description=item.description, amount=item.amount))

    db.commit()
    db.refresh(saving)

    invalidate_user_savings_cache(current_user.id)
    return build_saving_response(saving)


@router.delete("/{saving_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_saving(
    saving_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete an entire saving record and its associated items."""
    saving = get_user_saving_or_404(db, saving_id, current_user.id)
    db.delete(saving)
    db.commit()

    invalidate_user_savings_cache(current_user.id)
    return None


@router.post("/{saving_id}/items", response_model=SavingResponse)
def add_item_to_saving(
    saving_id: int,
    item_in: SavingItemCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Add a saving item to an existing saving record."""
    saving = get_user_saving_or_404(db, saving_id, current_user.id)

    new_item = SavingItem(
        saving_id=saving.id,
        description=item_in.description,
        amount=item_in.amount,
    )
    db.add(new_item)
    db.commit()
    db.refresh(saving)

    invalidate_user_savings_cache(current_user.id)
    return build_saving_response(saving)


@router.delete("/{saving_id}/items/{item_id}", response_model=SavingResponse)
def delete_saving_item(
    saving_id: int,
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a saving item from an existing saving record."""
    saving = get_user_saving_or_404(db, saving_id, current_user.id)

    item = (
        db.query(SavingItem)
        .filter(SavingItem.id == item_id, SavingItem.saving_id == saving.id)
        .first()
    )
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=HTTP_EXCEPTION_ERROR_SAVING_ITEM_NOT_FOUND,
        )

    db.delete(item)
    db.commit()
    db.refresh(saving)

    invalidate_user_savings_cache(current_user.id)
    return build_saving_response(saving)


@router.post("/{saving_id}/link", response_model=SavingResponse)
def link_saving_to_expense(
    saving_id: int,
    link_data: SavingLinkExpense,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Link a saving record to a specific expense."""
    saving = get_user_saving_or_404(db, saving_id, current_user.id)
    validate_saving_expense(db, link_data.expense_id, current_user.id)

    saving.expense_id = link_data.expense_id
    db.commit()
    db.refresh(saving)

    invalidate_user_savings_cache(current_user.id)
    return build_saving_response(saving)


@router.post("/{saving_id}/unlink", response_model=SavingResponse)
def unlink_saving_from_expense(
    saving_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Unlink a saving record from its associated expense."""
    saving = get_user_saving_or_404(db, saving_id, current_user.id)

    saving.expense_id = None
    db.commit()
    db.refresh(saving)

    invalidate_user_savings_cache(current_user.id)
    return build_saving_response(saving)
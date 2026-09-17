from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from database import get_db
from dependencies import get_current_admin
from models import Expense, ExpenseItem, Medication, User
from schemas import AdminStats, UserPublic, UserRoleUpdate

router = APIRouter(
    prefix="/admin",
    tags=["Admin"],
    dependencies=[Depends(get_current_admin)],
)


@router.get("/stats", response_model=AdminStats)
def get_admin_dashboard_stats(db: Session = Depends(get_db)):
    """Retrieve high-level system statistics for administrators."""
    total_users = db.query(User).count()
    total_expenses = db.query(Expense).count()
    total_medications = db.query(Medication).count()

    total_amount = sum(
        item.amount for item in db.query(ExpenseItem).all()
    )

    return AdminStats(
        total_users=total_users,
        total_expenses=total_expenses,
        total_medications=total_medications,
        total_expense_amount=float(total_amount),
    )


@router.get("/users", response_model=list[UserPublic])
def list_all_users(db: Session = Depends(get_db)):
    """List all registered users with their roles (passwords omitted)."""
    return db.query(User).all()


@router.patch("/users/{user_id}/role", response_model=UserPublic)
def update_user_role(
    user_id: int,
    role_update: UserRoleUpdate,
    db: Session = Depends(get_db),
    admin_user: User = Depends(get_current_admin),
):
    """Grant or revoke administrative privileges for a user."""
    target_user = db.query(User).filter(User.id == user_id).first()
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Prevent admin from revoking their own admin access accidentally
    if target_user.id == admin_user.id and not role_update.admin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Administrators cannot revoke their own admin rights",
        )

    target_user.admin = role_update.admin
    db.commit()
    db.refresh(target_user)
    return target_user

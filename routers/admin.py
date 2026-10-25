from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import func
from sqlalchemy.orm import Session
from audit import record_audit
from database import get_db
from dependencies import get_current_admin
from models import AuditLog, Category, Expense, ExpenseItem, GrossIncome, Medication, Saving, SavingItem, User
from pagination import Page, page_params, paginate
from schemas import AdminStats, AuditLogResponse, UserPublic, UserRoleUpdate

router = APIRouter(
    prefix="/admin",
    tags=["Admin"],
    dependencies=[Depends(get_current_admin)],
)


@router.get("/stats", response_model=AdminStats)
def get_admin_dashboard_stats(db: Session = Depends(get_db)):
    """Retrieve high-level system statistics for administrators."""
    total_users = db.query(User).count()
    total_categories = db.query(Category).count()
    total_expenses = db.query(Expense).count()
    total_medications = db.query(Medication).count()
    total_gross_incomes = db.query(GrossIncome).count()
    total_savings = db.query(Saving).count()

    total_amount = db.query(func.coalesce(func.sum(ExpenseItem.amount), 0.0)).scalar()
    total_gross_income_amount = db.query(func.coalesce(func.sum(GrossIncome.amount), 0.0)).scalar()
    total_savings_amount = db.query(func.coalesce(func.sum(SavingItem.amount), 0.0)).scalar()

    return AdminStats(
        total_users=total_users,
        total_categories=total_categories,
        total_expenses=total_expenses,
        total_medications=total_medications,
        total_gross_incomes=total_gross_incomes,
        total_savings=total_savings,
        total_expense_amount=float(total_amount),
        total_gross_income_amount=float(total_gross_income_amount),
        total_savings_amount=float(total_savings_amount),
    )


@router.get("/users", response_model=list[UserPublic])
def list_all_users(response: Response, page: Page = Depends(page_params), db: Session = Depends(get_db)):
    """List registered users with their roles (passwords omitted). Paginated; total in X-Total-Count."""
    query = db.query(User).order_by(User.id.asc())
    return paginate(query, page, response, UserPublic.model_validate, UserPublic)


@router.get("/audit-logs", response_model=list[AuditLogResponse])
def list_audit_logs(
    response: Response,
    action: str | None = Query(None, max_length=64),
    page: Page = Depends(page_params),
    db: Session = Depends(get_db),
):
    """Audit trail, newest first, optionally filtered by action. Paginated; total in X-Total-Count."""
    query = db.query(AuditLog)
    if action:
        query = query.filter(AuditLog.action == action)
    query = query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
    return paginate(query, page, response, AuditLogResponse.model_validate, AuditLogResponse)


@router.patch("/users/{user_id}/role", response_model=UserPublic)
def update_user_role(
    user_id: int,
    role_update: UserRoleUpdate,
    request: Request,
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

    previous = target_user.admin
    target_user.admin = role_update.admin
    db.commit()
    record_audit(
        db, request, admin_user, "admin_role_change", "user", target_user.id,
        {"from": previous, "to": role_update.admin},
    )
    db.refresh(target_user)
    return target_user

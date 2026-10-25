from fastapi import Request
from sqlalchemy.orm import Session
from models import AuditLog, User


def record_audit(
    db: Session,
    request: Request | None,
    actor: User | None,
    action: str,
    target_type: str | None = None,
    target_id: int | str | None = None,
    details: dict | None = None,
) -> None:
    """Append and commit one audit row. Never pass passwords or tokens in details."""
    db.add(
        AuditLog(
            actor_user_id=actor.id if actor else None,
            action=action,
            target_type=target_type,
            target_id=str(target_id) if target_id is not None else None,
            details=details,
            ip=request.client.host if request and request.client else None,
        )
    )
    db.commit()

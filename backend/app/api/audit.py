"""Audit trail API."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.database import get_db
from app.models.models import AuditLog
from app.core.security import require_role

router = APIRouter()


@router.get("/{session_id}")
async def get_audit_trail(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_role("nurse", "admin")),
):
    """Return full audit trail for a session - immutable record."""
    result = await db.execute(
        select(AuditLog)
        .where(AuditLog.session_id == session_id)
        .order_by(AuditLog.created_at)
    )
    logs = result.scalars().all()
    return [
        {
            "id": log.id,
            "action": log.action,
            "actor": log.actor,
            "detail": log.detail,
            "timestamp": log.created_at,
        }
        for log in logs
    ]

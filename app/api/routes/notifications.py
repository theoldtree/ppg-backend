"""
Notification endpoints
"""
import json
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from typing import List

from app.db.database import get_db
from app.db.models.measurement import Notification
from app.core.security import decode_access_token

router = APIRouter()
security = HTTPBearer(auto_error=False)


def _get_user_id(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> int:
    if not credentials:
        raise HTTPException(status_code=401, detail="Authentication required")
    payload = decode_access_token(credentials.credentials)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    return int(user_id)


def _serialize(n: Notification) -> dict:
    data = None
    if n.data_json:
        try:
            data = json.loads(n.data_json)
        except Exception:
            pass
    return {
        "id": str(n.id),
        "type": n.type,
        "title": n.title,
        "body": n.message,
        "isRead": n.is_read,
        "createdAt": n.created_at.isoformat() if n.created_at else None,
        "data": data,
    }


@router.get("/", response_model=List[dict])
async def get_notifications(
    limit: int = 50,
    user_id: int = Depends(_get_user_id),
    db: Session = Depends(get_db),
):
    """Return latest notifications for the authenticated user, newest first."""
    notifs = (
        db.query(Notification)
        .filter(Notification.user_id == user_id)
        .order_by(Notification.created_at.desc())
        .limit(limit)
        .all()
    )
    return [_serialize(n) for n in notifs]


@router.patch("/{notif_id}/read")
async def mark_notification_read(
    notif_id: int,
    user_id: int = Depends(_get_user_id),
    db: Session = Depends(get_db),
):
    notif = db.query(Notification).filter(
        Notification.id == notif_id,
        Notification.user_id == user_id,
    ).first()
    if not notif:
        raise HTTPException(status_code=404, detail="Notification not found")
    notif.is_read = True
    db.commit()
    return {"status": "ok"}


@router.post("/mark-all-read")
async def mark_all_notifications_read(
    user_id: int = Depends(_get_user_id),
    db: Session = Depends(get_db),
):
    db.query(Notification).filter(
        Notification.user_id == user_id,
        Notification.is_read == False,  # noqa: E712
    ).update({"is_read": True})
    db.commit()
    return {"status": "ok"}


@router.get("/unread-count")
async def get_unread_count(
    user_id: int = Depends(_get_user_id),
    db: Session = Depends(get_db),
):
    count = db.query(Notification).filter(
        Notification.user_id == user_id,
        Notification.is_read == False,  # noqa: E712
    ).count()
    return {"count": count}

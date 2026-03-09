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


# ── DEV-ONLY: manual scheduler trigger ───────────────────────────────────────

@router.post("/dev/trigger")
async def dev_trigger_notification(
    job: str,
    user_id: int = Depends(_get_user_id),
    db: Session = Depends(get_db),
):
    """DEV ONLY — manually fire a scheduler job for testing.
    job: 'morning' | 'afternoon' | 'weekly'
    """
    import os
    if os.getenv("APP_ENV", "development") == "production":
        raise HTTPException(status_code=403, detail="Not available in production")

    from app.services import notification_service as ns
    from datetime import datetime, timezone

    if job == "morning":
        ns.create_reminder_notification(db=db, user_id=user_id, slot="morning")
    elif job == "afternoon":
        ns.create_reminder_notification(db=db, user_id=user_id, slot="afternoon")
    elif job == "weekly":
        # Minimal inline weekly report for single user
        from app.db.models import Measurement
        from datetime import timedelta
        KST_OFFSET = timedelta(hours=9)
        now_kst = datetime.now(timezone.utc) + KST_OFFSET
        week_ago = (now_kst - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
        two_weeks_ago = (now_kst - timedelta(days=14)).strftime("%Y-%m-%d %H:%M:%S")
        this_week = db.query(Measurement).filter(
            Measurement.user_id == user_id,
            Measurement.status == "completed",
            Measurement.heart_rate.isnot(None),
            Measurement.completed_at >= week_ago,
        ).all()
        if not this_week:
            return {"status": "skipped", "reason": "no measurements this week"}
        avg_hr = sum(m.heart_rate for m in this_week) / len(this_week)
        prev_week = db.query(Measurement).filter(
            Measurement.user_id == user_id,
            Measurement.status == "completed",
            Measurement.heart_rate.isnot(None),
            Measurement.completed_at >= two_weeks_ago,
            Measurement.completed_at < week_ago,
        ).all()
        prev_avg_hr = sum(m.heart_rate for m in prev_week) / len(prev_week) if prev_week else None
        ns.create_weekly_report_notification(
            db=db, user_id=user_id,
            avg_hr=avg_hr, prev_avg_hr=prev_avg_hr,
            measurement_count=len(this_week),
        )
    else:
        raise HTTPException(status_code=400, detail="job must be 'morning', 'afternoon', or 'weekly'")

    return {"status": "ok", "job": job}

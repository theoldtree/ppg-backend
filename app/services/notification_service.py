"""
Notification service — creates notification records in the DB.
All functions are synchronous (called from sync SQLAlchemy sessions).
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from app.db.models.measurement import Notification


def create_notification(
    db: Session,
    user_id: int,
    type: str,
    title: str,
    message: str,
    data: dict | None = None,
) -> Notification:
    notif = Notification(
        user_id=user_id,
        type=type,
        title=title,
        message=message,
        data_json=json.dumps(data, ensure_ascii=False) if data else None,
    )
    db.add(notif)
    db.commit()
    db.refresh(notif)
    return notif


def create_measurement_complete_notification(
    db: Session,
    user_id: int,
    heart_rate: int,
    hrv: int,
    status: str,
    percentile: int,
    measurement_id: int,
) -> Notification:
    status_label = {"excellent": "매우 좋음", "good": "양호", "normal": "보통", "poor": "주의"}.get(status, status)
    now_str = datetime.now(timezone.utc).strftime("%H:%M")
    return create_notification(
        db=db,
        user_id=user_id,
        type="measurement_complete",
        title="측정 완료",
        message=f"{now_str} 측정 완료 — 심박수 {heart_rate} bpm · {status_label} · 상위 {percentile}%",
        data={
            "measurement_id": measurement_id,
            "heartRate": heart_rate,
            "hrv": hrv,
            "status": status,
            "percentile": percentile,
        },
    )


def create_reminder_notification(db: Session, user_id: int, slot: str) -> Notification:
    """slot: 'morning' | 'afternoon'"""
    if slot == "morning":
        title, msg = "오전 측정 알림", "오전 측정 시간이에요. PPG 건강 측정을 시작해보세요."
    else:
        title, msg = "오후 측정 알림", "오늘 오후 측정을 아직 하지 않았어요. 건강 추적을 위해 측정해주세요."
    return create_notification(db=db, user_id=user_id, type="reminder", title=title, message=msg)


def create_weekly_report_notification(
    db: Session,
    user_id: int,
    avg_hr: float,
    prev_avg_hr: float | None,
    measurement_count: int,
) -> Notification:
    trend = "improving" if prev_avg_hr and avg_hr < prev_avg_hr - 1 else \
            "declining"  if prev_avg_hr and avg_hr > prev_avg_hr + 1 else "stable"
    if trend == "improving":
        trend_text = f"지난 주({prev_avg_hr:.0f} bpm) 대비 {prev_avg_hr - avg_hr:.0f} bpm 낮아졌어요."
    elif trend == "declining":
        trend_text = f"지난 주({prev_avg_hr:.0f} bpm) 대비 {avg_hr - prev_avg_hr:.0f} bpm 높아졌어요."
    else:
        trend_text = "지난 주와 비슷한 수준입니다."
    return create_notification(
        db=db,
        user_id=user_id,
        type="weekly_report",
        title="주간 리포트",
        message=f"이번 주 심박수 평균 {avg_hr:.0f} bpm, 총 {measurement_count}회 측정. {trend_text}",
        data={
            "avgHR": round(avg_hr, 1),
            "prevAvgHR": round(prev_avg_hr, 1) if prev_avg_hr else None,
            "trend": trend,
            "measurementCount": measurement_count,
        },
    )

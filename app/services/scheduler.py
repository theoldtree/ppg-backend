"""
Background scheduler for notification triggers.
- Daily 09:00 KST: morning reminder if user hasn't measured today
- Daily 15:00 KST: afternoon reminder if user hasn't measured since morning
- Weekly Mon 09:00 KST: weekly report for all active users
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))
scheduler = BackgroundScheduler(timezone="Asia/Seoul")


def _get_db_session():
    """Return a plain SQLAlchemy session (not a FastAPI dependency)."""
    from app.db.database import SessionLocal
    return SessionLocal()


# ── Daily reminders ───────────────────────────────────────────────────────────

def _check_reminders(slot: str) -> None:
    """Create reminder notifications for users who haven't measured yet today."""
    from app.db.models.measurement import Notification
    from app.db.models.user import User
    from app.db.models import Measurement
    from app.services.notification_service import create_reminder_notification

    db = _get_db_session()
    try:
        today_kst = datetime.now(KST).date()
        # Users who have NOT completed a measurement today
        measured_today_ids = {
            row[0] for row in
            db.query(Measurement.user_id)
            .filter(
                Measurement.status == "completed",
                # SQLite stores naive UTC datetimes; compare as strings for safety
                Measurement.completed_at >= today_kst.strftime("%Y-%m-%d"),
            )
            .all()
        }
        all_users = db.query(User).all()
        for user in all_users:
            if user.id not in measured_today_ids:
                create_reminder_notification(db=db, user_id=user.id, slot=slot)
                logger.info(f"Reminder ({slot}) created for user_id={user.id}")
    except Exception as e:
        logger.error(f"Reminder job failed: {e}")
    finally:
        db.close()


def morning_reminder():
    _check_reminders("morning")


def afternoon_reminder():
    _check_reminders("afternoon")


# ── Weekly report ─────────────────────────────────────────────────────────────

def weekly_report() -> None:
    """Compute last-week stats and create weekly_report notifications."""
    from app.db.models.measurement import Notification
    from app.db.models.user import User
    from app.db.models import Measurement
    from app.services.notification_service import create_weekly_report_notification

    db = _get_db_session()
    try:
        now_kst = datetime.now(KST)
        this_week_start = (now_kst - timedelta(days=7)).strftime("%Y-%m-%d")
        prev_week_start = (now_kst - timedelta(days=14)).strftime("%Y-%m-%d")

        all_users = db.query(User).all()
        for user in all_users:
            # Measurements this past week
            this_week = (
                db.query(Measurement)
                .filter(
                    Measurement.user_id == user.id,
                    Measurement.status == "completed",
                    Measurement.heart_rate.isnot(None),
                    Measurement.completed_at >= this_week_start,
                )
                .all()
            )
            if not this_week:
                continue  # No data this week — skip report

            avg_hr = sum(m.heart_rate for m in this_week) / len(this_week)

            # Previous week avg for comparison
            prev_week = (
                db.query(Measurement)
                .filter(
                    Measurement.user_id == user.id,
                    Measurement.status == "completed",
                    Measurement.heart_rate.isnot(None),
                    Measurement.completed_at >= prev_week_start,
                    Measurement.completed_at < this_week_start,
                )
                .all()
            )
            prev_avg_hr = (
                sum(m.heart_rate for m in prev_week) / len(prev_week) if prev_week else None
            )

            create_weekly_report_notification(
                db=db,
                user_id=user.id,
                avg_hr=avg_hr,
                prev_avg_hr=prev_avg_hr,
                measurement_count=len(this_week),
            )
            logger.info(f"Weekly report created for user_id={user.id}")
    except Exception as e:
        logger.error(f"Weekly report job failed: {e}")
    finally:
        db.close()


# ── Scheduler setup ───────────────────────────────────────────────────────────

def start_scheduler() -> None:
    scheduler.add_job(morning_reminder,   CronTrigger(hour=9,  minute=0, timezone="Asia/Seoul"), id="morning_reminder",   replace_existing=True)
    scheduler.add_job(afternoon_reminder, CronTrigger(hour=15, minute=0, timezone="Asia/Seoul"), id="afternoon_reminder", replace_existing=True)
    scheduler.add_job(weekly_report,      CronTrigger(day_of_week="mon", hour=9, minute=0, timezone="Asia/Seoul"), id="weekly_report", replace_existing=True)
    scheduler.start()
    logger.info("Notification scheduler started (morning 09:00, afternoon 15:00, weekly Mon 09:00 KST)")


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)

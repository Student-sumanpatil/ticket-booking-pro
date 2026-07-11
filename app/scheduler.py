from apscheduler.schedulers.background import BackgroundScheduler

from app.config import settings
from app.database import SessionLocal
from app.booking_logic import release_expired_holds

scheduler = BackgroundScheduler()


def _job():
    db = SessionLocal()
    try:
        release_expired_holds(db)
    finally:
        db.close()


def start_scheduler():
    scheduler.add_job(
        _job,
        "interval",
        seconds=settings.RELEASE_SCHEDULER_INTERVAL_SECONDS,
        id="release_expired_holds",
        replace_existing=True,
    )
    scheduler.start()

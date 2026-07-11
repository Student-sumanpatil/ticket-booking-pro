"""
Central configuration, loaded from environment variables (.env file).
See .env.example for all available settings.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


class Settings:
    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR}/ticketing.db")

    # Auth
    JWT_SECRET: str = os.getenv("JWT_SECRET", "dev-secret-change-me-in-production")
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "120"))

    # Seat hold / waitlist timing
    SEAT_HOLD_TTL_MINUTES: int = int(os.getenv("SEAT_HOLD_TTL_MINUTES", "10"))
    WAITLIST_OFFER_TTL_MINUTES: int = int(os.getenv("WAITLIST_OFFER_TTL_MINUTES", "15"))
    RELEASE_SCHEDULER_INTERVAL_SECONDS: int = int(
        os.getenv("RELEASE_SCHEDULER_INTERVAL_SECONDS", "15")
    )

    # Email delivery
    # "console" (default): emails are logged + saved as .html files in sent_emails/
    #                       so you can open and inspect them without any credentials.
    # "smtp": sends real email via any SMTP provider (Gmail app password, SendGrid, etc.)
    EMAIL_BACKEND: str = os.getenv("EMAIL_BACKEND", "console")
    SMTP_HOST: str = os.getenv("SMTP_HOST", "")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER: str = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
    EMAIL_FROM: str = os.getenv("EMAIL_FROM", "no-reply@cinebook.example")

    # App
    BASE_URL: str = os.getenv("BASE_URL", "http://127.0.0.1:8000")


settings = Settings()

"""
Application configuration settings
"""
import os
from typing import List
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings"""

    # Project info
    PROJECT_NAME: str = "PPG Health API"
    VERSION: str = "1.0.0"

    # API settings
    API_V1_PREFIX: str = "/api/v1"

    # CORS settings
    ALLOWED_ORIGINS: List[str] = [
        "http://localhost:8081",  # React Native Metro
        "http://localhost:19000",  # Expo
        "http://localhost:19006",  # Expo web
    ]

    # Database settings
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql://postgres:password@localhost:5432/ppghealth"
    )

    # Security settings
    SECRET_KEY: str = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days

    # OAuth settings
    KAKAO_CLIENT_ID: str = os.getenv("KAKAO_CLIENT_ID", "")
    KAKAO_REDIRECT_URI: str = os.getenv("KAKAO_REDIRECT_URI", "")
    GOOGLE_CLIENT_ID: str = os.getenv("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET: str = os.getenv("GOOGLE_CLIENT_SECRET", "")
    GOOGLE_REDIRECT_URI: str = os.getenv("GOOGLE_REDIRECT_URI", "")

    # PPG Processing settings
    SAMPLING_RATE: int = 300  # Hz
    WINDOW_SIZE_QC: int = 2  # seconds
    WINDOW_SIZE_ANALYSIS: int = 10  # seconds
    HOP_SIZE_QC: int = 2  # seconds
    HOP_SIZE_ANALYSIS: int = 10  # seconds

    # QC Thresholds
    QC_SNR_MIN: float = 5.0
    QC_PEAK_COUNT_MIN: int = 3
    QC_PEAK_COUNT_MAX: int = 20
    QC_AMPLITUDE_MIN: float = 10.0
    QC_AMPLITUDE_MAX: float = 200.0

    # Analysis thresholds
    HR_MIN: int = 40  # bpm
    HR_MAX: int = 200  # bpm
    HRV_SDNN_MIN: float = 10.0  # ms
    HRV_SDNN_MAX: float = 200.0  # ms

    class Config:
        env_file = ".env"
        case_sensitive = True


# Create settings instance
settings = Settings()

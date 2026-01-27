"""
Test configuration settings
"""
import pytest
from app.core.config import settings


def test_settings_exist():
    """
    Test that all required settings are defined
    """
    assert settings.PROJECT_NAME == "PPG Health API"
    assert settings.VERSION == "1.0.0"
    assert settings.API_V1_PREFIX == "/api/v1"


def test_ppg_settings():
    """
    Test PPG processing settings
    """
    assert settings.SAMPLING_RATE == 300
    assert settings.WINDOW_SIZE_QC == 2
    assert settings.WINDOW_SIZE_ANALYSIS == 10
    assert settings.HOP_SIZE_QC == 2
    assert settings.HOP_SIZE_ANALYSIS == 10


def test_qc_thresholds():
    """
    Test QC threshold values are reasonable
    """
    assert settings.QC_SNR_MIN > 0
    assert settings.QC_PEAK_COUNT_MIN > 0
    assert settings.QC_PEAK_COUNT_MAX > settings.QC_PEAK_COUNT_MIN
    assert settings.QC_AMPLITUDE_MIN > 0
    assert settings.QC_AMPLITUDE_MAX > settings.QC_AMPLITUDE_MIN


def test_analysis_thresholds():
    """
    Test analysis threshold values are reasonable
    """
    assert settings.HR_MIN > 0
    assert settings.HR_MAX > settings.HR_MIN
    assert settings.HR_MIN >= 40  # Minimum healthy heart rate
    assert settings.HR_MAX <= 200  # Maximum reasonable heart rate

    assert settings.HRV_SDNN_MIN > 0
    assert settings.HRV_SDNN_MAX > settings.HRV_SDNN_MIN


def test_allowed_origins():
    """
    Test that CORS origins are configured
    """
    assert isinstance(settings.ALLOWED_ORIGINS, list)
    assert len(settings.ALLOWED_ORIGINS) > 0
    assert any("localhost" in origin for origin in settings.ALLOWED_ORIGINS)

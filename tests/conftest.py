"""
Test configuration and fixtures
"""
import pytest
from fastapi.testclient import TestClient
from main import app


@pytest.fixture
def client():
    """
    Create a test client for the FastAPI app
    """
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def sample_ppg_data():
    """
    Sample PPG data for testing (2 seconds at 300Hz)
    """
    import numpy as np

    # Generate realistic PPG waveform
    sampling_rate = 300
    duration = 2
    t = np.linspace(0, duration, sampling_rate * duration)

    # Simulate PPG signal with heartbeat
    heart_rate = 72  # bpm
    frequency = heart_rate / 60  # Hz

    # PPG waveform (systolic peak + diastolic notch)
    signal = 100 + 30 * np.sin(2 * np.pi * frequency * t)
    signal += 10 * np.sin(4 * np.pi * frequency * t)  # Harmonics
    signal += np.random.normal(0, 2, len(signal))  # Noise

    return signal.tolist()


@pytest.fixture
def sample_measurement_data():
    """
    Sample measurement data for testing
    """
    return {
        "user_id": 1,
        "started_at": "2026-01-27T15:00:00",
        "duration_seconds": 60,
        "notes": "Test measurement",
    }

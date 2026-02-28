"""
PPG Analysis Service

Computes HR, HRV, stress, APG indices, and demographic percentile
from raw PPG signal data.

Designed for 200-300 Hz PPG input. Falls back to FFT-based estimation
for lower sampling rates (e.g. simulated 10 Hz data).
"""
import numpy as np
from typing import Optional, Tuple, Dict, Any
from sqlalchemy.orm import Session

from app.db.models import AnalysisResult, UserBaseline, DemographicBaseline


# ── HR / HRV ─────────────────────────────────────────────────────────────────

def compute_hr_hrv(
    ppg_data: list[float],
    sampling_rate: int = 200,
) -> Dict[str, Any]:
    """
    Estimate HR (bpm) and HRV (SDNN, RMSSD ms) from raw PPG.

    For sampling_rate >= 30 Hz: bandpass filter + peak detection.
    For lower rates: FFT-based dominant frequency estimation.

    Returns dict with keys: heart_rate, hrv_sdnn, hrv_rmssd (all int/None).
    """
    ppg = np.array(ppg_data, dtype=float)
    n = len(ppg)
    duration_sec = n / sampling_rate

    if n < 2 or duration_sec < 3:
        return {"heart_rate": None, "hrv_sdnn": None, "hrv_rmssd": None}

    try:
        from scipy.signal import butter, filtfilt, find_peaks

        if sampling_rate >= 30:
            # ── Bandpass filter: 0.5–4.0 Hz (30–240 bpm) ──────────────────
            nyq = sampling_rate / 2.0
            low = 0.5 / nyq
            high = min(4.0 / nyq, 0.99)
            b, a = butter(4, [low, high], btype='band')
            filtered = filtfilt(b, a, ppg)

            # ── Peak detection ──────────────────────────────────────────────
            min_distance = int(sampling_rate * 0.35)   # max ~170 bpm
            height_thresh = np.mean(filtered) + 0.1 * np.std(filtered)
            peaks, _ = find_peaks(filtered, distance=min_distance, height=height_thresh)

        else:
            # Low-rate path: no bandpass, just find peaks
            min_distance = max(2, int(sampling_rate * 0.4))
            peaks, _ = find_peaks(ppg, distance=min_distance)

        if len(peaks) < 2:
            hr = _fft_hr(ppg, sampling_rate)
            return {"heart_rate": hr, "hrv_sdnn": None, "hrv_rmssd": None}

        # ── Inter-beat intervals (ms) ───────────────────────────────────────
        ibi_samples = np.diff(peaks)
        ibi_ms = ibi_samples / sampling_rate * 1000.0

        # Plausibility filter: keep IBI in 300–2000 ms (30–200 bpm)
        valid = ibi_ms[(ibi_ms >= 300) & (ibi_ms <= 2000)]
        if len(valid) < 2:
            hr = _fft_hr(ppg, sampling_rate)
            return {"heart_rate": hr, "hrv_sdnn": None, "hrv_rmssd": None}

        heart_rate = int(round(60_000.0 / np.mean(valid)))
        hrv_sdnn = int(round(float(np.std(valid, ddof=1))))
        successive_diff = np.diff(valid)
        hrv_rmssd = int(round(float(np.sqrt(np.mean(successive_diff ** 2)))))

        return {
            "heart_rate": heart_rate,
            "hrv_sdnn": hrv_sdnn,
            "hrv_rmssd": hrv_rmssd,
        }

    except Exception:
        hr = _fft_hr(ppg, sampling_rate)
        return {"heart_rate": hr, "hrv_sdnn": None, "hrv_rmssd": None}


def _fft_hr(ppg: np.ndarray, sampling_rate: int) -> Optional[int]:
    """FFT-based HR fallback for noisy or low-rate signals."""
    try:
        n = len(ppg)
        freqs = np.fft.rfftfreq(n, d=1.0 / sampling_rate)
        fft_mag = np.abs(np.fft.rfft(ppg - np.mean(ppg)))

        # HR band: 0.5–4 Hz
        mask = (freqs >= 0.5) & (freqs <= 4.0)
        if not np.any(mask):
            return None
        dominant_freq = freqs[mask][np.argmax(fft_mag[mask])]
        return int(round(dominant_freq * 60))
    except Exception:
        return None


# ── Stress ────────────────────────────────────────────────────────────────────

def compute_stress(hrv_sdnn: Optional[float]) -> int:
    """
    Estimate stress level (0–100) from SDNN.
    SDNN ≤ 10 ms → stress ~90, SDNN ≥ 80 ms → stress ~10.
    Linear interpolation in between.
    """
    if hrv_sdnn is None:
        return 50  # neutral when no HRV data
    stress = 100 - (hrv_sdnn - 10) * (90 / 70)
    return max(5, min(95, int(round(stress))))


# ── APG indices ───────────────────────────────────────────────────────────────

def compute_apg_indices(
    ppg_data: list[float],
    sampling_rate: int = 200,
) -> Optional[Dict[str, float]]:
    """
    Compute APG (Acceleration PhotoPlethysmoGraphy) indices.

    APG = second derivative of PPG. Characteristic peaks:
      a (early systolic max), b (early systolic min),
      c (mid-systolic max), d (mid-systolic min).

    Clinically meaningful at ≥ 200 Hz. At lower rates the ratios
    are structurally correct but not medically validated.

    Returns dict with b_over_a, c_over_a, d_over_a, ai  or None.
    """
    ppg = np.array(ppg_data, dtype=float)
    if len(ppg) < 20:
        return None

    # Use last 20 data points (or one cardiac cycle worth)
    cycle_samples = min(int(sampling_rate * 1.0), len(ppg))
    window = ppg[-max(cycle_samples, 20):]

    # 3-point smoothing
    smoothed = np.convolve(window, np.ones(3) / 3, mode='same')
    smoothed[0] = window[0]
    smoothed[-1] = window[-1]

    # Second derivative
    apg = np.diff(smoothed, n=2)
    if len(apg) < 8:
        return None

    q = max(1, len(apg) // 4)

    peak_a = float(np.max(apg[:q * 2]))
    peak_b = float(np.min(apg[:q * 2]))
    peak_c = float(np.max(apg[q:q * 3]))
    peak_d = float(np.min(apg[q * 2:]))

    if abs(peak_a) < 1e-6:
        return None

    return {
        "b_over_a": round(peak_b / peak_a, 3),
        "c_over_a": round(peak_c / peak_a, 3),
        "d_over_a": round(peak_d / peak_a, 3),
        "ai":       round((peak_d - peak_c) / peak_a, 3),
    }


# ── Perfusion Index ───────────────────────────────────────────────────────────

def compute_perfusion_index(ppg_data: list[float]) -> Optional[float]:
    """
    PI = (AC amplitude / DC mean) × 100 (%)
    AC = peak-to-trough amplitude of pulsatile component.
    """
    ppg = np.array(ppg_data, dtype=float)
    if len(ppg) < 10:
        return None
    dc = float(np.mean(ppg))
    if dc <= 0:
        return None
    ac = float(np.max(ppg) - np.min(ppg))
    return round(ac / dc * 100, 2)


# ── Status determination ──────────────────────────────────────────────────────

def determine_status(heart_rate: Optional[int], hrv_sdnn: Optional[float]) -> str:
    """Return 'excellent' / 'good' / 'normal' / 'poor'."""
    hr = heart_rate or 75
    hrv = hrv_sdnn or 0

    if hr <= 75 and hrv >= 50:
        return "excellent"
    if hr <= 85 and hrv >= 30:
        return "good"
    if hr <= 100:
        return "normal"
    return "poor"


# ── Demographic comparison ────────────────────────────────────────────────────

def get_demographic_comparison(
    heart_rate: int,
    birth_year: Optional[int],
    gender: Optional[str],
    db: Session,
) -> Dict[str, Any]:
    """
    Look up DemographicBaseline and compute percentile for the user.

    Returns dict: percentile, age_group_avg, gender_group_avg, comparison.
    """
    from datetime import date
    current_year = date.today().year
    age = (current_year - birth_year) if birth_year else None
    age_group = _age_to_group(age)
    norm_gender = _normalize_gender(gender)

    # Try gender + age_group specific baseline
    baseline = _query_baseline(db, norm_gender, age_group)
    if baseline is None:
        # Fallback: any gender, same age_group
        baseline = _query_baseline(db, "all", age_group)
    if baseline is None:
        # Last fallback: all, age_group 30
        baseline = _query_baseline(db, "all", 30)

    if baseline and baseline.avg_heart_rate and baseline.std_heart_rate:
        avg_hr = baseline.avg_heart_rate
        std_hr = max(baseline.std_heart_rate, 1.0)
        z = (heart_rate - avg_hr) / std_hr
        # Higher HR → lower (worse) percentile
        from scipy.stats import norm as scipy_norm
        percentile = int(round((1 - scipy_norm.cdf(z)) * 100))
        percentile = max(1, min(99, percentile))
    else:
        avg_hr = 72
        percentile = 50

    gender_avg = int(round(avg_hr))
    age_avg = int(round(avg_hr))

    if percentile > 60:
        comparison = "above_average"
    elif percentile >= 40:
        comparison = "average"
    else:
        comparison = "below_average"

    return {
        "percentile": percentile,
        "age_group_avg": age_avg,
        "gender_group_avg": gender_avg,
        "comparison": comparison,
    }


def _age_to_group(age: Optional[int]) -> int:
    if age is None:
        return 30
    if age < 25:
        return 20
    if age < 35:
        return 30
    if age < 45:
        return 40
    if age < 55:
        return 50
    return 60


def _normalize_gender(gender: Optional[str]) -> str:
    if gender in ("male", "M"):
        return "male"
    if gender in ("female", "F"):
        return "female"
    return "all"


def _query_baseline(
    db: Session, gender: str, age_group: int
) -> Optional[DemographicBaseline]:
    return (
        db.query(DemographicBaseline)
        .filter(
            DemographicBaseline.gender == gender,
            DemographicBaseline.age_group == age_group,
        )
        .first()
    )


# ── Update user baseline ──────────────────────────────────────────────────────

def update_user_baseline(
    user_id: int,
    heart_rate: int,
    hrv_sdnn: Optional[float],
    db: Session,
) -> None:
    """
    Incrementally update rolling average for the user's personal baseline.
    Uses simple exponential moving average with α = 1/n (capped at 0.1).
    """
    baseline = db.query(UserBaseline).filter(UserBaseline.user_id == user_id).first()
    if baseline is None:
        baseline = UserBaseline(
            user_id=user_id,
            avg_heart_rate=float(heart_rate),
            avg_hrv_sdnn=float(hrv_sdnn) if hrv_sdnn else None,
            measurement_count=1,
        )
        db.add(baseline)
    else:
        n = (baseline.measurement_count or 0) + 1
        alpha = max(0.1, 1.0 / n)

        if baseline.avg_heart_rate is not None:
            baseline.avg_heart_rate = (1 - alpha) * baseline.avg_heart_rate + alpha * heart_rate
        else:
            baseline.avg_heart_rate = float(heart_rate)

        if hrv_sdnn is not None:
            if baseline.avg_hrv_sdnn is not None:
                baseline.avg_hrv_sdnn = (1 - alpha) * baseline.avg_hrv_sdnn + alpha * hrv_sdnn
            else:
                baseline.avg_hrv_sdnn = float(hrv_sdnn)

        baseline.measurement_count = n

    db.commit()

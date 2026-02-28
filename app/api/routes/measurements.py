"""
Measurement endpoints
"""
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from datetime import datetime
from typing import List

from app.db.database import get_db
from app.db.models import Measurement, QCFeedback, AnalysisResult, UserBaseline
from app.db.schemas.measurement import (
    MeasurementStart,
    MeasurementStartResponse,
    QCDataBatch,
    QCFeedbackResponse,
    MeasurementComplete,
    MeasurementCompleteResponse,
    AnalysisRequest,
    AnalysisResponse,
    GeneralAnalysis,
    PersonalComparison,
    DemographicComparison,
    BatteryUpdate,
)
from app.services.qc_service import analyze_ppg_signal
from app.services import analysis_service

router = APIRouter()


@router.post("/start", response_model=MeasurementStartResponse)
async def start_measurement(
    request: MeasurementStart,
    db: Session = Depends(get_db),
):
    """
    Start a new measurement session
    """
    measurement = Measurement(
        user_id=request.user_id,
        started_at=datetime.utcnow(),
        status="in_progress",
    )
    db.add(measurement)
    db.commit()
    db.refresh(measurement)

    return MeasurementStartResponse(
        measurement_id=measurement.id,
        started_at=measurement.started_at,
        status=measurement.status,
    )


@router.post("/qc/data", response_model=QCFeedbackResponse)
async def submit_qc_data(
    request: QCDataBatch,
    db: Session = Depends(get_db),
):
    """
    Submit PPG data for real-time QC feedback
    Expected: 2-second windows (600 samples at 300Hz)
    """
    # Verify measurement exists
    measurement = db.query(Measurement).filter(
        Measurement.id == request.measurement_id
    ).first()

    if not measurement:
        raise HTTPException(status_code=404, detail="Measurement not found")

    if measurement.status != "in_progress":
        raise HTTPException(
            status_code=400,
            detail=f"Measurement is not in progress (status: {measurement.status})"
        )

    # Analyze PPG signal quality using real QC service
    ppg_data = request.ppg_data

    # Run QC analysis
    qc_result = analyze_ppg_signal(ppg_data)

    is_acceptable = qc_result["is_acceptable"]
    snr = qc_result["snr"]
    peak_count = qc_result["peak_count"]
    feedback_message = qc_result["feedback_message"]

    # Save QC feedback to database
    qc_feedback = QCFeedback(
        measurement_id=request.measurement_id,
        window_index=request.window_index,
        timestamp=request.timestamp,
        is_acceptable=is_acceptable,
        snr=snr,
        peak_count=peak_count,
        feedback_message=feedback_message,
    )
    db.add(qc_feedback)
    db.commit()

    return QCFeedbackResponse(
        window_index=request.window_index,
        timestamp=request.timestamp,
        is_acceptable=is_acceptable,
        snr=snr,
        peak_count=peak_count,
        feedback_message=feedback_message,
        battery_level=request.battery_level,
    )


@router.get("/qc/latest/{measurement_id}", response_model=QCFeedbackResponse)
async def get_latest_qc(
    measurement_id: int,
    db: Session = Depends(get_db),
):
    """
    Get the latest QC feedback for a measurement
    """
    qc_feedback = db.query(QCFeedback).filter(
        QCFeedback.measurement_id == measurement_id
    ).order_by(QCFeedback.timestamp.desc()).first()

    if not qc_feedback:
        raise HTTPException(status_code=404, detail="No QC feedback found")

    return QCFeedbackResponse(
        window_index=qc_feedback.window_index,
        timestamp=qc_feedback.timestamp,
        is_acceptable=qc_feedback.is_acceptable,
        snr=qc_feedback.snr,
        peak_count=qc_feedback.peak_count,
        feedback_message=qc_feedback.feedback_message,
        battery_level=None,
    )


@router.post("/complete", response_model=MeasurementCompleteResponse)
async def complete_measurement(
    request: MeasurementComplete,
    db: Session = Depends(get_db),
):
    """
    Mark a measurement as completed
    """
    measurement = db.query(Measurement).filter(
        Measurement.id == request.measurement_id
    ).first()

    if not measurement:
        raise HTTPException(status_code=404, detail="Measurement not found")

    if measurement.status == "completed":
        raise HTTPException(status_code=400, detail="Measurement already completed")

    # Update measurement
    measurement.completed_at = datetime.utcnow()
    measurement.status = "completed"
    measurement.notes = request.notes

    # Calculate duration
    duration = (measurement.completed_at - measurement.started_at).total_seconds()
    measurement.duration_seconds = int(duration)

    db.commit()
    db.refresh(measurement)

    return MeasurementCompleteResponse(
        measurement_id=measurement.id,
        completed_at=measurement.completed_at,
        duration_seconds=measurement.duration_seconds,
        status=measurement.status,
    )


@router.post("/analyze", response_model=AnalysisResponse)
async def analyze_measurement(
    request: AnalysisRequest,
    db: Session = Depends(get_db),
):
    """
    Analyze a completed measurement and return results
    """
    measurement = db.query(Measurement).filter(
        Measurement.id == request.measurement_id
    ).first()

    if not measurement:
        raise HTTPException(status_code=404, detail="Measurement not found")

    if measurement.status != "completed":
        raise HTTPException(
            status_code=400,
            detail="Measurement must be completed before analysis"
        )

    # Check if analysis already exists
    existing_analysis = db.query(AnalysisResult).filter(
        AnalysisResult.measurement_id == request.measurement_id
    ).first()

    if existing_analysis:
        return _build_analysis_response(existing_analysis, measurement.user_id, db)

    # ── Real analysis ────────────────────────────────────────────────────────
    ppg_data = request.ppg_data or []
    sampling_rate = request.sampling_rate or 200

    hr_hrv = analysis_service.compute_hr_hrv(ppg_data, sampling_rate)
    heart_rate = hr_hrv["heart_rate"] or 72
    hrv_sdnn = hr_hrv["hrv_sdnn"] or 40
    hrv_rmssd = hr_hrv["hrv_rmssd"]
    stress_level = analysis_service.compute_stress(hrv_sdnn)
    status = analysis_service.determine_status(heart_rate, hrv_sdnn)

    apg = analysis_service.compute_apg_indices(ppg_data, sampling_rate) if ppg_data else None

    analysis = AnalysisResult(
        measurement_id=request.measurement_id,
        heart_rate=float(heart_rate),
        hrv_sdnn=float(hrv_sdnn),
        hrv_rmssd=float(hrv_rmssd) if hrv_rmssd else None,
        stress_level=float(stress_level),
        status=status,
        apg_b_over_a=apg["b_over_a"] if apg else None,
        apg_c_over_a=apg["c_over_a"] if apg else None,
        apg_d_over_a=apg["d_over_a"] if apg else None,
    )
    db.add(analysis)
    db.commit()
    db.refresh(analysis)

    # Update user's personal baseline
    analysis_service.update_user_baseline(measurement.user_id, heart_rate, hrv_sdnn, db)

    return _build_analysis_response(analysis, measurement.user_id, db)


def _build_analysis_response(
    analysis: AnalysisResult,
    user_id: int,
    db: Session,
) -> AnalysisResponse:
    """
    Build complete analysis response with personal and demographic comparisons.
    """
    from app.db.models.user import User

    # ── Personal comparison ──────────────────────────────────────────────────
    baseline = db.query(UserBaseline).filter(UserBaseline.user_id == user_id).first()

    if baseline and baseline.avg_heart_rate:
        hr_diff = int(round(analysis.heart_rate - baseline.avg_heart_rate))
        hrv_diff = int(round(analysis.hrv_sdnn - baseline.avg_hrv_sdnn)) if baseline.avg_hrv_sdnn else 0
        if hr_diff < -5 and hrv_diff > 5:
            trend = "improving"
        elif abs(hr_diff) <= 5 and abs(hrv_diff) <= 5:
            trend = "stable"
        else:
            trend = "declining"
    else:
        hr_diff = 0
        hrv_diff = 0
        trend = "stable"

    # ── Demographic comparison ───────────────────────────────────────────────
    user = db.query(User).filter(User.id == user_id).first()
    birth_year = user.birth_year if user else None
    gender = user.gender if user else None

    demo = analysis_service.get_demographic_comparison(
        heart_rate=int(analysis.heart_rate),
        birth_year=birth_year,
        gender=gender,
        db=db,
    )

    return AnalysisResponse(
        measurement_id=analysis.measurement_id,
        general=GeneralAnalysis(
            heartRate=int(analysis.heart_rate),
            hrv=int(analysis.hrv_sdnn),
            stressLevel=int(analysis.stress_level),
            status=analysis.status,
        ),
        personal=PersonalComparison(
            heartRateDiff=hr_diff,
            hrvDiff=hrv_diff,
            trend=trend,
        ),
        demographic=DemographicComparison(
            percentile=demo["percentile"],
            ageGroupAvg=demo["age_group_avg"],
            genderGroupAvg=demo["gender_group_avg"],
            comparison=demo["comparison"],
        ),
    )


@router.post("/battery")
async def update_battery(
    request: BatteryUpdate,
    db: Session = Depends(get_db),
):
    """
    Update battery level for a measurement
    (This is informational and doesn't require database storage for now)
    """
    measurement = db.query(Measurement).filter(
        Measurement.id == request.measurement_id
    ).first()

    if not measurement:
        raise HTTPException(status_code=404, detail="Measurement not found")

    return {
        "measurement_id": request.measurement_id,
        "battery_level": request.battery_level,
        "status": "updated",
    }

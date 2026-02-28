"""
Measurement endpoints
"""
from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from datetime import datetime, timezone
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
    DiaryUpdateRequest,
    MeasurementHistoryItem,
)
from app.services.qc_service import analyze_ppg_signal
from app.services import analysis_service
from app.core.security import decode_access_token

router = APIRouter()
security = HTTPBearer(auto_error=False)


# ── Auth helper ───────────────────────────────────────────────────────────────

def _get_user_id(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> int:
    """Extract user_id from JWT; raise 401 if invalid."""
    if not credentials:
        raise HTTPException(status_code=401, detail="Authentication required")
    payload = decode_access_token(credentials.credentials)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    return int(user_id)


# ── Start ─────────────────────────────────────────────────────────────────────

@router.post("/start", response_model=MeasurementStartResponse)
async def start_measurement(
    request: MeasurementStart,
    db: Session = Depends(get_db),
):
    measurement = Measurement(
        user_id=request.user_id,
        started_at=datetime.now(timezone.utc),
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


# ── QC data ───────────────────────────────────────────────────────────────────

@router.post("/qc/data", response_model=QCFeedbackResponse)
async def submit_qc_data(
    request: QCDataBatch,
    db: Session = Depends(get_db),
):
    measurement = db.query(Measurement).filter(
        Measurement.id == request.measurement_id
    ).first()
    if not measurement:
        raise HTTPException(status_code=404, detail="Measurement not found")
    if measurement.status != "in_progress":
        raise HTTPException(status_code=400, detail=f"Measurement not in progress (status: {measurement.status})")

    qc_result = analyze_ppg_signal(request.ppg_data)
    is_acceptable = qc_result["is_acceptable"]
    snr = qc_result["snr"]
    peak_count = qc_result["peak_count"]
    feedback_message = qc_result["feedback_message"]

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
async def get_latest_qc(measurement_id: int, db: Session = Depends(get_db)):
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


# ── Complete ──────────────────────────────────────────────────────────────────

@router.post("/complete", response_model=MeasurementCompleteResponse)
async def complete_measurement(
    request: MeasurementComplete,
    db: Session = Depends(get_db),
):
    measurement = db.query(Measurement).filter(
        Measurement.id == request.measurement_id
    ).first()
    if not measurement:
        raise HTTPException(status_code=404, detail="Measurement not found")
    if measurement.status == "completed":
        raise HTTPException(status_code=400, detail="Measurement already completed")

    measurement.completed_at = datetime.now(timezone.utc)
    measurement.status = "completed"
    measurement.notes = request.notes
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


# ── Analyze ───────────────────────────────────────────────────────────────────

@router.post("/analyze", response_model=AnalysisResponse)
async def analyze_measurement(
    request: AnalysisRequest,
    db: Session = Depends(get_db),
):
    measurement = db.query(Measurement).filter(
        Measurement.id == request.measurement_id
    ).first()
    if not measurement:
        raise HTTPException(status_code=404, detail="Measurement not found")
    if measurement.status != "completed":
        raise HTTPException(status_code=400, detail="Measurement must be completed before analysis")

    existing = db.query(AnalysisResult).filter(
        AnalysisResult.measurement_id == request.measurement_id
    ).first()
    if existing:
        return _build_analysis_response(existing, measurement, db)

    ppg_data = request.ppg_data or []
    sampling_rate = request.sampling_rate or 200

    hr_hrv = analysis_service.compute_hr_hrv(ppg_data, sampling_rate)
    heart_rate = hr_hrv["heart_rate"] or 72
    hrv_sdnn   = hr_hrv["hrv_sdnn"] or 40
    hrv_rmssd  = hr_hrv["hrv_rmssd"]
    stress_level = analysis_service.compute_stress(hrv_sdnn)
    status = analysis_service.determine_status(heart_rate, hrv_sdnn)

    # Perfusion Index
    pi_val = analysis_service.compute_perfusion_index(ppg_data) if ppg_data else None
    ppg_arr = ppg_data or []
    ac_val = float(max(ppg_arr) - min(ppg_arr)) if len(ppg_arr) >= 2 else 0.0
    dc_val = float(sum(ppg_arr) / len(ppg_arr)) if ppg_arr else 0.0

    apg = analysis_service.compute_apg_indices(ppg_data, sampling_rate) if ppg_data else None

    analysis = AnalysisResult(
        measurement_id=request.measurement_id,
        heart_rate=float(heart_rate),
        hrv_sdnn=float(hrv_sdnn),
        hrv_rmssd=float(hrv_rmssd) if hrv_rmssd else None,
        stress_level=float(stress_level),
        pi=float(pi_val) if pi_val is not None else None,
        ac=round(ac_val, 2),
        dc=round(dc_val, 2),
        status=status,
        apg_b_over_a=apg["b_over_a"] if apg else None,
        apg_c_over_a=apg["c_over_a"] if apg else None,
        apg_d_over_a=apg["d_over_a"] if apg else None,
    )
    db.add(analysis)
    db.commit()
    db.refresh(analysis)

    analysis_service.update_user_baseline(measurement.user_id, heart_rate, hrv_sdnn, db)
    return _build_analysis_response(analysis, measurement, db)


def _build_analysis_response(
    analysis: AnalysisResult,
    measurement: Measurement,
    db: Session,
) -> AnalysisResponse:
    from app.db.models.user import User

    # Personal comparison
    baseline = db.query(UserBaseline).filter(
        UserBaseline.user_id == measurement.user_id
    ).first()
    if baseline and baseline.avg_heart_rate:
        hr_diff  = int(round(analysis.heart_rate - baseline.avg_heart_rate))
        hrv_diff = int(round(analysis.hrv_sdnn - baseline.avg_hrv_sdnn)) if baseline.avg_hrv_sdnn else 0
        if hr_diff < -5 and hrv_diff > 5:
            trend = "improving"
        elif abs(hr_diff) <= 5 and abs(hrv_diff) <= 5:
            trend = "stable"
        else:
            trend = "declining"
    else:
        hr_diff = hrv_diff = 0
        trend = "stable"

    # Demographic comparison
    user = db.query(User).filter(User.id == measurement.user_id).first()
    birth_year = user.birth_year if user else None
    gender     = user.gender     if user else None
    demo = analysis_service.get_demographic_comparison(
        heart_rate=int(analysis.heart_rate),
        birth_year=birth_year,
        gender=gender,
        db=db,
    )

    # Auto-advice based on results
    hr  = int(analysis.heart_rate)
    hrv = int(analysis.hrv_sdnn)
    hr_ok  = 60 <= hr <= 100
    hrv_ok = hrv >= 30
    if hr_ok and hrv_ok:
        advice = "심박수와 HRV가 모두 정상 범위입니다. 현재 컨디션이 좋아요. 규칙적인 측정을 유지하세요."
    elif hr_ok:
        advice = f"HRV({hrv} ms)가 다소 낮습니다. 충분한 수면과 휴식을 권장합니다."
    elif hrv_ok:
        advice = f"심박수({hr} bpm)가 정상 범위를 벗어났습니다. 안정 후 재측정을 권장합니다."
    else:
        advice = "심박수와 HRV 모두 주의가 필요합니다. 규칙적인 운동과 충분한 휴식을 취하세요."

    return AnalysisResponse(
        measurement_id=analysis.measurement_id,
        general=GeneralAnalysis(
            heartRate=int(analysis.heart_rate),
            hrv=int(analysis.hrv_sdnn),
            pi=round(float(analysis.pi or 0), 2),
            ac=round(float(analysis.ac or 0), 2),
            dc=round(float(analysis.dc or 0), 2),
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
        advice=advice,
    )


# ── Diary: save notes/tags/advice ─────────────────────────────────────────────

@router.patch("/{measurement_id}/diary")
async def save_diary_entry(
    measurement_id: int,
    request: DiaryUpdateRequest,
    user_id: int = Depends(_get_user_id),
    db: Session = Depends(get_db),
):
    """Save user's diary notes, tags, and advice for a completed measurement."""
    measurement = db.query(Measurement).filter(
        Measurement.id == measurement_id,
        Measurement.user_id == user_id,
    ).first()
    if not measurement:
        raise HTTPException(status_code=404, detail="Measurement not found")

    if request.notes is not None:
        measurement.notes = request.notes
    if request.advice is not None:
        measurement.advice = request.advice
    if request.tags is not None:
        measurement.tags = ",".join(request.tags)

    db.commit()
    return {"status": "saved"}


# ── History ───────────────────────────────────────────────────────────────────

@router.get("/history", response_model=List[MeasurementHistoryItem])
async def get_measurement_history(
    user_id: int = Depends(_get_user_id),
    db: Session = Depends(get_db),
):
    """Return all completed measurements for the authenticated user, newest first."""
    measurements = (
        db.query(Measurement)
        .filter(
            Measurement.user_id == user_id,
            Measurement.status == "completed",
        )
        .order_by(Measurement.completed_at.desc())
        .all()
    )

    items: List[MeasurementHistoryItem] = []
    for m in measurements:
        analysis_result = db.query(AnalysisResult).filter(
            AnalysisResult.measurement_id == m.id
        ).first()

        started = m.started_at
        analysis_dict = None
        if analysis_result:
            # Personal comparison
            baseline = db.query(UserBaseline).filter(
                UserBaseline.user_id == m.user_id
            ).first()
            hr_diff = hrv_diff = 0
            trend = "stable"
            if baseline and baseline.avg_heart_rate:
                hr_diff  = int(round(analysis_result.heart_rate - baseline.avg_heart_rate))
                hrv_diff = int(round(analysis_result.hrv_sdnn - baseline.avg_hrv_sdnn)) if baseline.avg_hrv_sdnn else 0
                if hr_diff < -5 and hrv_diff > 5:
                    trend = "improving"
                elif not (abs(hr_diff) <= 5 and abs(hrv_diff) <= 5):
                    trend = "declining"

            # Demographic comparison
            from app.db.models.user import User
            user = db.query(User).filter(User.id == m.user_id).first()
            demo = analysis_service.get_demographic_comparison(
                heart_rate=int(analysis_result.heart_rate),
                birth_year=user.birth_year if user else None,
                gender=user.gender if user else None,
                db=db,
            )

            analysis_dict = {
                "general": {
                    "heartRate": int(analysis_result.heart_rate),
                    "hrv": int(analysis_result.hrv_sdnn),
                    "pi": round(float(analysis_result.pi or 0), 2),
                    "ac": round(float(analysis_result.ac or 0), 2),
                    "dc": round(float(analysis_result.dc or 0), 2),
                    "status": analysis_result.status,
                },
                "personal": {
                    "heartRateDiff": hr_diff,
                    "hrvDiff": hrv_diff,
                    "trend": trend,
                },
                "demographic": {
                    "percentile": demo["percentile"],
                    "ageGroupAvg": demo["age_group_avg"],
                    "genderGroupAvg": demo["gender_group_avg"],
                    "comparison": demo["comparison"],
                },
            }

        tags_list = [t for t in (m.tags or "").split(",") if t] if m.tags else []
        items.append(MeasurementHistoryItem(
            id=str(m.id),
            userId=str(m.user_id),
            date=started.strftime("%Y-%m-%d"),
            time=started.strftime("%H:%M:%S"),
            timestamp=int(started.timestamp() * 1000),
            duration=m.duration_seconds or 60,
            notes=m.notes,
            advice=m.advice,
            tags=tags_list,
            analysis=analysis_dict,
        ))

    return items


# ── Battery ───────────────────────────────────────────────────────────────────

@router.post("/battery")
async def update_battery(
    request: BatteryUpdate,
    db: Session = Depends(get_db),
):
    measurement = db.query(Measurement).filter(
        Measurement.id == request.measurement_id
    ).first()
    if not measurement:
        raise HTTPException(status_code=404, detail="Measurement not found")
    return {"measurement_id": request.measurement_id, "battery_level": request.battery_level, "status": "updated"}

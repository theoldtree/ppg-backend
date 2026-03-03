"""
Measurement endpoints
"""
from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from datetime import datetime, timezone, timedelta

KST = timezone(timedelta(hours=9))
from typing import List

from app.db.database import get_db
from app.db.models import Measurement, QCFeedback, UserBaseline
from app.db.models.measurement import MockPPGSource, MockPPGPacket
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
    SaveMockAnalysisRequest,
    BatteryUpdate,
    DiaryUpdateRequest,
    MeasurementHistoryItem,
)
from app.services.qc_service import analyze_ppg_signal
from app.services import analysis_service
from app.services.notification_service import create_measurement_complete_notification
from app.core.security import decode_access_token

router = APIRouter()
security = HTTPBearer(auto_error=False)


# ── Auth helper ───────────────────────────────────────────────────────────────

def _get_user_id(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> int:
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
        is_dev=request.is_dev,
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
    measurement = db.query(Measurement).filter(Measurement.id == request.measurement_id).first()
    if not measurement:
        raise HTTPException(status_code=404, detail="Measurement not found")
    if measurement.status != "in_progress":
        raise HTTPException(status_code=400, detail=f"Measurement not in progress (status: {measurement.status})")

    qc_result = analyze_ppg_signal(request.ppg_data)
    qc_feedback = QCFeedback(
        measurement_id=request.measurement_id,
        window_index=request.window_index,
        timestamp=request.timestamp,
        is_acceptable=qc_result["is_acceptable"],
        snr=qc_result["snr"],
        peak_count=qc_result["peak_count"],
        feedback_message=qc_result["feedback_message"],
    )
    db.add(qc_feedback)
    db.commit()

    return QCFeedbackResponse(
        window_index=request.window_index,
        timestamp=request.timestamp,
        is_acceptable=qc_result["is_acceptable"],
        snr=qc_result["snr"],
        peak_count=qc_result["peak_count"],
        feedback_message=qc_result["feedback_message"],
        battery_level=request.battery_level,
    )


@router.get("/qc/latest/{measurement_id}", response_model=QCFeedbackResponse)
async def get_latest_qc(measurement_id: int, db: Session = Depends(get_db)):
    qc = db.query(QCFeedback).filter(
        QCFeedback.measurement_id == measurement_id
    ).order_by(QCFeedback.timestamp.desc()).first()
    if not qc:
        raise HTTPException(status_code=404, detail="No QC feedback found")
    return QCFeedbackResponse(
        window_index=qc.window_index,
        timestamp=qc.timestamp,
        is_acceptable=qc.is_acceptable,
        snr=qc.snr,
        peak_count=qc.peak_count,
        feedback_message=qc.feedback_message,
        battery_level=None,
    )


# ── Complete ──────────────────────────────────────────────────────────────────

@router.post("/complete", response_model=MeasurementCompleteResponse)
async def complete_measurement(
    request: MeasurementComplete,
    db: Session = Depends(get_db),
):
    measurement = db.query(Measurement).filter(Measurement.id == request.measurement_id).first()
    if not measurement:
        raise HTTPException(status_code=404, detail="Measurement not found")
    if measurement.status == "completed":
        raise HTTPException(status_code=400, detail="Measurement already completed")

    now = datetime.now(timezone.utc)
    measurement.completed_at = now
    measurement.status = "completed"
    measurement.notes = request.notes
    started = measurement.started_at
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    measurement.duration_seconds = max(1, int((now - started).total_seconds()))
    db.commit()
    db.refresh(measurement)

    return MeasurementCompleteResponse(
        measurement_id=measurement.id,
        completed_at=measurement.completed_at,
        duration_seconds=measurement.duration_seconds,
        status=measurement.status,
    )


# ── Analyze (real BLE path) ───────────────────────────────────────────────────

@router.post("/analyze", response_model=AnalysisResponse)
async def analyze_measurement(
    request: AnalysisRequest,
    db: Session = Depends(get_db),
):
    measurement = db.query(Measurement).filter(Measurement.id == request.measurement_id).first()
    if not measurement:
        raise HTTPException(status_code=404, detail="Measurement not found")
    if measurement.status != "completed":
        raise HTTPException(status_code=400, detail="Measurement must be completed before analysis")

    # Return cached result if already analyzed
    if measurement.heart_rate is not None:
        return _build_analysis_response(measurement, db)

    ppg_data = request.ppg_data or []
    sampling_rate = request.sampling_rate or 200

    hr_hrv = analysis_service.compute_hr_hrv(ppg_data, sampling_rate)
    heart_rate = hr_hrv["heart_rate"] or 72
    hrv_sdnn   = hr_hrv["hrv_sdnn"] or 40
    hrv_rmssd  = hr_hrv["hrv_rmssd"]

    pi_val = analysis_service.compute_perfusion_index(ppg_data) if ppg_data else None
    ppg_arr = ppg_data or []
    ac_val = float(max(ppg_arr) - min(ppg_arr)) if len(ppg_arr) >= 2 else 0.0
    dc_val = float(sum(ppg_arr) / len(ppg_arr)) if ppg_arr else 0.0

    apg = analysis_service.compute_apg_indices(ppg_data, sampling_rate) if ppg_data else None
    stress = analysis_service.compute_stress(hrv_sdnn)
    status = analysis_service.determine_status(heart_rate, hrv_sdnn)

    measurement.heart_rate   = float(heart_rate)
    measurement.hrv_sdnn     = float(hrv_sdnn)
    measurement.hrv_rmssd    = float(hrv_rmssd) if hrv_rmssd else None
    measurement.pi           = float(pi_val) if pi_val is not None else None
    measurement.ac           = round(ac_val, 2)
    measurement.dc           = round(dc_val, 2)
    measurement.apg_b_over_a = apg["b_over_a"] if apg else None
    measurement.apg_c_over_a = apg["c_over_a"] if apg else None
    measurement.apg_d_over_a = apg["d_over_a"] if apg else None
    measurement.stress_level = float(stress)
    measurement.result_status = status
    db.commit()

    if not measurement.is_dev:
        from app.db.models.user import User as _User
        _user = db.query(_User).filter(_User.id == measurement.user_id).first()
        analysis_service.update_user_baseline(measurement.user_id, heart_rate, hrv_sdnn, db)
        analysis_service.update_demographic_baseline(
            heart_rate=heart_rate,
            hrv_sdnn=hrv_sdnn,
            birth_year=_user.birth_year if _user else None,
            gender=_user.gender if _user else None,
            db=db,
        )

    response = _build_analysis_response(measurement, db)

    try:
        create_measurement_complete_notification(
            db=db,
            user_id=measurement.user_id,
            heart_rate=int(heart_rate),
            hrv=int(hrv_sdnn),
            status=status,
            percentile=response.demographic.percentile,
            measurement_id=request.measurement_id,
        )
    except Exception:
        pass

    return response


# ── Save pre-computed analysis (mock/dev path) ────────────────────────────────

@router.post("/{measurement_id}/save-analysis")
async def save_mock_analysis(
    measurement_id: int,
    request: SaveMockAnalysisRequest,
    db: Session = Depends(get_db),
):
    """Save pre-computed analysis values directly (used in mock/dev mode)."""
    measurement = db.query(Measurement).filter(Measurement.id == measurement_id).first()
    if not measurement:
        raise HTTPException(status_code=404, detail="Measurement not found")

    measurement.heart_rate    = float(request.heart_rate)
    measurement.hrv_sdnn      = float(request.hrv_sdnn)
    measurement.hrv_rmssd     = float(request.hrv_rmssd) if request.hrv_rmssd is not None else None
    measurement.pi            = float(request.pi)
    measurement.ac            = float(request.ac)
    measurement.dc            = float(request.dc)
    measurement.apg_b_over_a  = float(request.apg_b_over_a) if request.apg_b_over_a is not None else None
    measurement.stress_level  = float(max(5, min(95, 100 - (request.hrv_sdnn - 10) * (90 / 70))))
    measurement.result_status = request.status
    db.commit()

    # Build response BEFORE updating baseline — first measurement sees no prior baseline (trend="first")
    response = _build_analysis_response(measurement, db)

    # Update both personal and demographic baselines via Welford
    from app.db.models.user import User as _User
    _user = db.query(_User).filter(_User.id == measurement.user_id).first()
    analysis_service.update_user_baseline(measurement.user_id, request.heart_rate, request.hrv_sdnn, db)
    analysis_service.update_demographic_baseline(
        heart_rate=request.heart_rate,
        hrv_sdnn=request.hrv_sdnn,
        birth_year=_user.birth_year if _user else None,
        gender=_user.gender if _user else None,
        db=db,
    )

    return response


# ── Shared response builder ───────────────────────────────────────────────────

def _build_analysis_response(measurement: Measurement, db: Session) -> AnalysisResponse:
    from app.db.models.user import User

    # Personal comparison
    baseline = db.query(UserBaseline).filter(UserBaseline.user_id == measurement.user_id).first()
    if baseline and baseline.avg_heart_rate and (baseline.measurement_count or 0) >= 1:
        hr_diff  = int(round(measurement.heart_rate - baseline.avg_heart_rate))
        hrv_diff = int(round(measurement.hrv_sdnn - baseline.avg_hrv_sdnn)) if baseline.avg_hrv_sdnn else 0
        if hr_diff < -5 and hrv_diff > 5:
            trend = "improving"
        elif abs(hr_diff) <= 5 and abs(hrv_diff) <= 5:
            trend = "stable"
        else:
            trend = "declining"
    else:
        hr_diff = hrv_diff = 0
        trend = "first"

    # Demographic comparison
    user = db.query(User).filter(User.id == measurement.user_id).first()
    demo = analysis_service.get_demographic_comparison(
        heart_rate=int(measurement.heart_rate),
        birth_year=user.birth_year if user else None,
        gender=user.gender if user else None,
        db=db,
    )

    # Auto-advice
    hr  = int(measurement.heart_rate)
    hrv = int(measurement.hrv_sdnn)
    if 60 <= hr <= 100 and hrv >= 30:
        advice = "심박수와 HRV가 모두 정상 범위입니다. 현재 컨디션이 좋아요. 규칙적인 측정을 유지하세요."
    elif 60 <= hr <= 100:
        advice = f"HRV({hrv} ms)가 다소 낮습니다. 충분한 수면과 휴식을 권장합니다."
    elif hrv >= 30:
        advice = f"심박수({hr} bpm)가 정상 범위를 벗어났습니다. 안정 후 재측정을 권장합니다."
    else:
        advice = "심박수와 HRV 모두 주의가 필요합니다. 규칙적인 운동과 충분한 휴식을 취하세요."

    apg_ai = (
        round(float(measurement.apg_d_over_a - measurement.apg_c_over_a), 3)
        if (measurement.apg_d_over_a is not None and measurement.apg_c_over_a is not None)
        else None
    )

    return AnalysisResponse(
        measurement_id=measurement.id,
        general=GeneralAnalysis(
            heartRate=int(measurement.heart_rate),
            hrv=int(measurement.hrv_sdnn),
            hrvRmssd=int(round(measurement.hrv_rmssd)) if measurement.hrv_rmssd is not None else None,
            pi=round(float(measurement.pi or 0), 2),
            ac=round(float(measurement.ac or 0), 2),
            dc=round(float(measurement.dc or 0), 2),
            apgBOverA=round(float(measurement.apg_b_over_a), 3) if measurement.apg_b_over_a is not None else None,
            apgAI=apg_ai,
            status=measurement.result_status or "normal",
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
            apgBOverARef=demo.get("apg_b_over_a_ref"),
            apgBOverAStd=demo.get("apg_b_over_a_std"),
            hrvPercentile=None,
            avgHrvSdnn=demo.get("avg_hrv_sdnn"),
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
    measurements = (
        db.query(Measurement)
        .filter(Measurement.user_id == user_id, Measurement.status == "completed")
        .order_by(Measurement.completed_at.desc())
        .all()
    )

    baseline = db.query(UserBaseline).filter(UserBaseline.user_id == user_id).first()

    from app.db.models.user import User
    user = db.query(User).filter(User.id == user_id).first()

    items: List[MeasurementHistoryItem] = []
    for m in measurements:
        display_utc = m.completed_at or m.started_at
        if display_utc.tzinfo is None:
            display_utc = display_utc.replace(tzinfo=timezone.utc)
        kst = display_utc.astimezone(KST)

        analysis_dict = None
        if m.heart_rate is not None:
            # Personal comparison
            hr_diff = hrv_diff = 0
            trend = "stable"
            if baseline and baseline.avg_heart_rate:
                hr_diff  = int(round(m.heart_rate - baseline.avg_heart_rate))
                hrv_diff = int(round(m.hrv_sdnn - baseline.avg_hrv_sdnn)) if baseline.avg_hrv_sdnn else 0
                if hr_diff < -5 and hrv_diff > 5:
                    trend = "improving"
                elif not (abs(hr_diff) <= 5 and abs(hrv_diff) <= 5):
                    trend = "declining"

            # Demographic comparison
            demo = analysis_service.get_demographic_comparison(
                heart_rate=int(m.heart_rate),
                birth_year=user.birth_year if user else None,
                gender=user.gender if user else None,
                db=db,
            )

            apg_ai = (
                round(float(m.apg_d_over_a - m.apg_c_over_a), 3)
                if (m.apg_d_over_a is not None and m.apg_c_over_a is not None)
                else None
            )
            analysis_dict = {
                "general": {
                    "heartRate": int(m.heart_rate),
                    "hrv": int(m.hrv_sdnn),
                    "hrvRmssd": int(round(m.hrv_rmssd)) if m.hrv_rmssd is not None else None,
                    "pi": round(float(m.pi or 0), 2),
                    "ac": round(float(m.ac or 0), 2),
                    "dc": round(float(m.dc or 0), 2),
                    "apgBOverA": round(float(m.apg_b_over_a), 3) if m.apg_b_over_a is not None else None,
                    "apgAI": apg_ai,
                    "status": m.result_status or "normal",
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
                    "apgBOverARef": demo.get("apg_b_over_a_ref"),
                    "apgBOverAStd": demo.get("apg_b_over_a_std"),
                    "avgHrvSdnn": demo.get("avg_hrv_sdnn"),
                },
            }

        tags_raw = m.tags or ""
        tags_list = [t for t in tags_raw.split(",") if t]
        items.append(MeasurementHistoryItem(
            id=str(m.id),
            userId=str(m.user_id),
            date=kst.strftime("%Y-%m-%d"),
            time=kst.strftime("%H:%M:%S"),
            timestamp=int(kst.timestamp() * 1000),
            duration=m.duration_seconds or 60,
            notes=m.notes,
            advice=m.advice,
            tags=tags_list,
            analysis=analysis_dict,
        ))

    return items


# ── Battery ───────────────────────────────────────────────────────────────────

@router.post("/battery")
async def update_battery(request: BatteryUpdate, db: Session = Depends(get_db)):
    measurement = db.query(Measurement).filter(Measurement.id == request.measurement_id).first()
    if not measurement:
        raise HTTPException(status_code=404, detail="Measurement not found")
    return {"measurement_id": request.measurement_id, "battery_level": request.battery_level, "status": "updated"}


# ── Mock PPG packets (dev-only) ───────────────────────────────────────────────

@router.get("/mock-sources", response_model=List[dict])
async def list_mock_sources(db: Session = Depends(get_db)):
    sources = db.query(MockPPGSource).order_by(MockPPGSource.id).all()
    return [
        {
            "id": s.id,
            "record_id": s.record_id,
            "hr_ref": s.hr_ref,
            "format": s.format,
            "packet_count": db.query(MockPPGPacket).filter(MockPPGPacket.source_id == s.id).count(),
        }
        for s in sources
    ]


@router.get("/mock-packets/{source_id}", response_model=List[dict])
async def get_mock_packets(
    source_id: int,
    offset: int = 0,
    limit: int = 300,
    db: Session = Depends(get_db),
):
    source = db.query(MockPPGSource).filter(MockPPGSource.id == source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Mock source not found")

    packets = (
        db.query(MockPPGPacket)
        .filter(MockPPGPacket.source_id == source_id)
        .order_by(MockPPGPacket.packet_index)
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [
        {
            "packet_index": p.packet_index,
            "sync_byte": p.sync_byte,
            "packet_bytes": list(p.packet_bytes),
            "battery_level": p.battery_level,
            "crc": p.crc,
        }
        for p in packets
    ]

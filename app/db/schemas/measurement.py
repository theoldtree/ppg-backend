"""
Pydantic schemas for measurements
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


# ============================================================================
# Measurement Schemas
# ============================================================================

class MeasurementStart(BaseModel):
    user_id: int = Field(..., description="User ID")
    is_dev: bool = Field(False, description="Dev/test measurement — excluded from baselines")

class MeasurementStartResponse(BaseModel):
    measurement_id: int
    started_at: datetime
    status: str


# ============================================================================
# QC Data Schemas
# ============================================================================

class QCDataBatch(BaseModel):
    measurement_id: int
    window_index: int
    timestamp: float
    ppg_data: List[float] = Field(..., description="PPG values")
    battery_level: Optional[int] = Field(None, ge=0, le=100)

class QCFeedbackResponse(BaseModel):
    window_index: int
    timestamp: float
    is_acceptable: bool
    snr: Optional[float]
    peak_count: Optional[int]
    feedback_message: Optional[str]
    battery_level: Optional[int]


# ============================================================================
# Complete Measurement Schemas
# ============================================================================

class MeasurementComplete(BaseModel):
    measurement_id: int
    notes: Optional[str] = None

class MeasurementCompleteResponse(BaseModel):
    measurement_id: int
    completed_at: datetime
    duration_seconds: int
    status: str


# ============================================================================
# Analysis Schemas
# ============================================================================

class AnalysisRequest(BaseModel):
    measurement_id: int
    ppg_data: Optional[List[float]] = Field(None)
    sampling_rate: Optional[int] = Field(200)

class MockRunRequest(BaseModel):
    """Mock BLE 시뮬레이션 실행 요청"""
    user_id: int
    source_id: int
    is_dev: bool = Field(True, description="True 이면 baseline 업데이트 제외")


class SaveMockAnalysisRequest(BaseModel):
    """Accept pre-computed analysis values directly (for mock/dev mode)."""
    heart_rate: int
    hrv_sdnn: int
    hrv_rmssd: Optional[int] = None
    pi: float
    ac: float
    dc: float
    apg_b_over_a: Optional[float] = None
    apg_ai: Optional[float] = None
    status: str  # 'excellent', 'good', 'normal', 'poor'
    percentile: int
    age_group_avg: int
    gender_group_avg: int

class GeneralAnalysis(BaseModel):
    heartRate: int
    hrv: int         # SDNN ms
    hrvRmssd: Optional[int] = None   # RMSSD ms
    pi: float
    ac: float
    dc: float
    apgBOverA: Optional[float] = None  # b/a ratio (arterial stiffness)
    apgAI: Optional[float] = None      # aging index
    status: str  # 'excellent', 'good', 'normal', 'poor'

class PersonalComparison(BaseModel):
    heartRateDiff: int
    hrvDiff: int
    trend: str  # 'improving', 'stable', 'declining'

class DemographicComparison(BaseModel):
    percentile: int
    ageGroupAvg: int
    genderGroupAvg: int
    comparison: str  # 'above_average', 'average', 'below_average'
    apgBOverARef: Optional[float] = None   # Takazawa reference b/a for this age/gender
    apgBOverAStd: Optional[float] = None   # std of reference
    hrvPercentile: Optional[int] = None
    avgHrvSdnn: Optional[int] = None
    stdHrvSdnn: Optional[float] = None     # HRV SDNN std for this age group

class AnalysisResponse(BaseModel):
    measurement_id: int
    general: GeneralAnalysis
    personal: PersonalComparison
    demographic: DemographicComparison
    advice: Optional[str] = None


# ============================================================================
# Diary Update Schema
# ============================================================================

class DiaryUpdateRequest(BaseModel):
    """Save diary notes, tags, advice after viewing measurement result"""
    notes: Optional[str] = None
    tags: Optional[List[str]] = None  # ["수면부족", "피로"]
    advice: Optional[str] = None


# ============================================================================
# Battery Update Schema
# ============================================================================

class BatteryUpdate(BaseModel):
    measurement_id: int
    battery_level: int = Field(..., ge=0, le=100)


# ============================================================================
# Measurement History Schema
# ============================================================================

class MeasurementHistoryItem(BaseModel):
    """One completed measurement record for the diary screen"""
    id: str
    userId: str
    date: str        # YYYY-MM-DD
    time: str        # HH:mm:ss
    timestamp: int
    duration: int
    notes: Optional[str] = None
    advice: Optional[str] = None
    tags: Optional[List[str]] = None
    analysis: Optional[dict] = None

    class Config:
        from_attributes = True

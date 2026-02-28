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
    """Request schema for starting a measurement"""
    user_id: int = Field(..., description="User ID")


class MeasurementStartResponse(BaseModel):
    """Response schema after starting a measurement"""
    measurement_id: int
    started_at: datetime
    status: str


# ============================================================================
# QC Data Schemas
# ============================================================================

class QCDataBatch(BaseModel):
    """Batch of PPG data for QC processing"""
    measurement_id: int
    window_index: int
    timestamp: float  # seconds from measurement start
    ppg_data: List[float] = Field(..., description="PPG values (400 samples for 2s at 200Hz)")
    battery_level: Optional[int] = Field(None, ge=0, le=100, description="Battery percentage")


class QCFeedbackResponse(BaseModel):
    """QC feedback response"""
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
    """Request schema for completing a measurement"""
    measurement_id: int
    notes: Optional[str] = None


class MeasurementCompleteResponse(BaseModel):
    """Response after completing measurement"""
    measurement_id: int
    completed_at: datetime
    duration_seconds: int
    status: str


# ============================================================================
# Analysis Schemas
# ============================================================================

class AnalysisRequest(BaseModel):
    """Request schema for analysis"""
    measurement_id: int
    ppg_data: Optional[List[float]] = Field(None, description="Raw PPG samples collected during measurement")
    sampling_rate: Optional[int] = Field(200, description="PPG sampling rate in Hz")


class GeneralAnalysis(BaseModel):
    """General health analysis"""
    heartRate: int
    hrv: int
    stressLevel: int
    status: str  # 'excellent', 'good', 'normal', 'poor'


class PersonalComparison(BaseModel):
    """Personal baseline comparison"""
    heartRateDiff: int
    hrvDiff: int
    trend: str  # 'improving', 'stable', 'declining'


class DemographicComparison(BaseModel):
    """Demographic group comparison"""
    percentile: int
    ageGroupAvg: int
    genderGroupAvg: int
    comparison: str  # 'above_average', 'average', 'below_average'


class AnalysisResponse(BaseModel):
    """Complete analysis response"""
    measurement_id: int
    general: GeneralAnalysis
    personal: PersonalComparison
    demographic: DemographicComparison


# ============================================================================
# Battery Update Schema
# ============================================================================

class BatteryUpdate(BaseModel):
    """Battery level update"""
    measurement_id: int
    battery_level: int = Field(..., ge=0, le=100)


# ============================================================================
# Measurement List Schemas
# ============================================================================

class MeasurementListItem(BaseModel):
    """Measurement list item for diary"""
    id: int
    date: str  # YYYY-MM-DD
    time: str  # HH:mm:ss
    timestamp: int
    duration: int
    notes: Optional[str]
    general: Optional[GeneralAnalysis]
    personal: Optional[PersonalComparison]
    demographic: Optional[DemographicComparison]

    class Config:
        from_attributes = True

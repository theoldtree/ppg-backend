"""
Measurement and related models
"""
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text, Boolean, func
from sqlalchemy.orm import relationship
from app.db.database import Base


class Measurement(Base):
    """Measurement session"""

    __tablename__ = "measurements"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    duration_seconds = Column(Integer, nullable=True)
    status = Column(String(20), default="in_progress")  # 'in_progress', 'completed', 'failed'
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    ppg_data = relationship("PPGProcessedData", back_populates="measurement", cascade="all, delete-orphan")
    qc_feedback = relationship("QCFeedback", back_populates="measurement", cascade="all, delete-orphan")
    analysis_results = relationship("AnalysisResult", back_populates="measurement", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Measurement(id={self.id}, user_id={self.user_id}, status='{self.status}')>"


class PPGProcessedData(Base):
    """Processed PPG data storage"""

    __tablename__ = "ppg_processed_data"

    id = Column(Integer, primary_key=True, index=True)
    measurement_id = Column(Integer, ForeignKey("measurements.id", ondelete="CASCADE"), nullable=False)
    window_start = Column(Float, nullable=False)  # seconds from measurement start
    window_end = Column(Float, nullable=False)
    window_type = Column(String(20), nullable=False)  # 'qc' or 'analysis'

    # Processed metrics
    mean_value = Column(Float, nullable=True)
    std_dev = Column(Float, nullable=True)
    peak_count = Column(Integer, nullable=True)
    snr = Column(Float, nullable=True)  # Signal-to-Noise Ratio

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationship
    measurement = relationship("Measurement", back_populates="ppg_data")

    def __repr__(self):
        return f"<PPGProcessedData(id={self.id}, window={self.window_start}-{self.window_end})>"


class QCFeedback(Base):
    """Quality Control feedback"""

    __tablename__ = "qc_feedback"

    id = Column(Integer, primary_key=True, index=True)
    measurement_id = Column(Integer, ForeignKey("measurements.id", ondelete="CASCADE"), nullable=False)
    window_index = Column(Integer, nullable=False)
    timestamp = Column(Float, nullable=False)  # seconds from measurement start

    # QC metrics
    is_acceptable = Column(Boolean, default=True)
    snr = Column(Float, nullable=True)
    peak_count = Column(Integer, nullable=True)
    amplitude_range = Column(Float, nullable=True)
    noise_level = Column(Float, nullable=True)
    signal_stability = Column(Float, nullable=True)

    # Feedback message
    feedback_message = Column(String(255), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationship
    measurement = relationship("Measurement", back_populates="qc_feedback")

    def __repr__(self):
        return f"<QCFeedback(id={self.id}, window={self.window_index}, acceptable={self.is_acceptable})>"


class AnalysisResult(Base):
    """Analysis results (HR, HRV, APG)"""

    __tablename__ = "analysis_results"

    id = Column(Integer, primary_key=True, index=True)
    measurement_id = Column(Integer, ForeignKey("measurements.id", ondelete="CASCADE"), nullable=False)

    # Heart Rate
    heart_rate = Column(Float, nullable=True)  # bpm

    # HRV metrics
    hrv_sdnn = Column(Float, nullable=True)  # ms
    hrv_rmssd = Column(Float, nullable=True)  # ms
    hrv_pnn50 = Column(Float, nullable=True)  # percentage

    # APG metrics
    apg_b_over_a = Column(Float, nullable=True)  # b/a ratio
    apg_c_over_a = Column(Float, nullable=True)  # c/a ratio
    apg_d_over_a = Column(Float, nullable=True)  # d/a ratio
    apg_e_over_a = Column(Float, nullable=True)  # e/a ratio

    # Stress estimation
    stress_level = Column(Float, nullable=True)  # 0-100

    # Anomaly detection
    z_score = Column(Float, nullable=True)
    is_anomaly = Column(Boolean, default=False)

    # Overall status
    status = Column(String(20), nullable=True)  # 'excellent', 'good', 'normal', 'poor'

    analyzed_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationship
    measurement = relationship("Measurement", back_populates="analysis_results")

    def __repr__(self):
        return f"<AnalysisResult(id={self.id}, hr={self.heart_rate}, status='{self.status}')>"


class UserBaseline(Base):
    """User baseline statistics for personal comparison"""

    __tablename__ = "user_baselines"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)

    # Personal averages
    avg_heart_rate = Column(Float, nullable=True)
    avg_hrv_sdnn = Column(Float, nullable=True)
    avg_hrv_rmssd = Column(Float, nullable=True)
    avg_stress_level = Column(Float, nullable=True)

    # Standard deviations
    std_heart_rate = Column(Float, nullable=True)
    std_hrv_sdnn = Column(Float, nullable=True)

    # Sample size
    measurement_count = Column(Integer, default=0)

    # Last update
    last_updated = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<UserBaseline(user_id={self.user_id}, count={self.measurement_count})>"


class Notification(Base):
    """User notifications"""

    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=True)
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<Notification(id={self.id}, user_id={self.user_id}, read={self.is_read})>"

"""
Measurement and related models
"""
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text, Boolean, LargeBinary, func
from sqlalchemy.orm import relationship
from app.db.database import Base


class Measurement(Base):
    """
    Core measurement record — session metadata + analysis results + diary notes.
    All 1:1 child tables (analysis_results, measurement_diary) have been merged here.
    """

    __tablename__ = "measurements"

    # ── Session ───────────────────────────────────────────────────────────────
    id               = Column(Integer, primary_key=True, index=True)
    user_id          = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    mock_source_id   = Column(Integer, ForeignKey("mock_ppg_sources.id", ondelete="SET NULL"), nullable=True)
    started_at       = Column(DateTime(timezone=True), nullable=False)
    completed_at     = Column(DateTime(timezone=True), nullable=True)
    duration_seconds = Column(Integer, nullable=True)
    status           = Column(String(20), default="in_progress")  # in_progress / completed / failed
    is_dev           = Column(Boolean, default=False, nullable=False, server_default="0")
    created_at       = Column(DateTime(timezone=True), server_default=func.now())

    # ── Analysis (merged from analysis_results) ───────────────────────────────
    heart_rate    = Column(Float, nullable=True)   # bpm
    hrv_sdnn      = Column(Float, nullable=True)   # ms SDNN
    hrv_rmssd     = Column(Float, nullable=True)   # ms RMSSD
    pi            = Column(Float, nullable=True)   # Perfusion Index (%)
    ac            = Column(Float, nullable=True)   # AC amplitude
    dc            = Column(Float, nullable=True)   # DC level
    apg_b_over_a  = Column(Float, nullable=True)   # APG b/a (arterial stiffness)
    apg_c_over_a  = Column(Float, nullable=True)
    apg_d_over_a  = Column(Float, nullable=True)
    stress_level  = Column(Float, nullable=True)   # 0–100
    result_status = Column(String(20), nullable=True)  # excellent / good / normal / poor

    # ── Diary (merged from measurement_diary; notes/tags/advice already existed) ─
    notes  = Column(Text, nullable=True)
    tags   = Column(Text, nullable=True)    # comma-separated, e.g. "수면부족,피로"
    advice = Column(Text, nullable=True)    # auto-generated advice

    # ── Relationships ─────────────────────────────────────────────────────────
    qc_feedback = relationship("QCFeedback", back_populates="measurement", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Measurement(id={self.id}, user_id={self.user_id}, status='{self.status}')>"


class QCFeedback(Base):
    """Quality Control feedback (real-time signal quality per window during measurement)"""

    __tablename__ = "qc_feedback"

    id              = Column(Integer, primary_key=True, index=True)
    measurement_id  = Column(Integer, ForeignKey("measurements.id", ondelete="CASCADE"), nullable=False)
    window_index    = Column(Integer, nullable=False)
    timestamp       = Column(Float, nullable=False)   # seconds from measurement start

    is_acceptable   = Column(Boolean, default=True)
    snr             = Column(Float, nullable=True)
    peak_count      = Column(Integer, nullable=True)
    amplitude_range = Column(Float, nullable=True)
    noise_level     = Column(Float, nullable=True)
    signal_stability= Column(Float, nullable=True)
    feedback_message= Column(String(255), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    measurement = relationship("Measurement", back_populates="qc_feedback")

    def __repr__(self):
        return f"<QCFeedback(id={self.id}, window={self.window_index}, ok={self.is_acceptable})>"


class UserBaseline(Base):
    """
    Personal baseline — Welford online statistics (mean + M2) for HR and HRV.
    std = sqrt(M2 / (n-1))  (computed on read, not stored separately)
    """

    __tablename__ = "user_baselines"

    id                = Column(Integer, primary_key=True, index=True)
    user_id           = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    avg_heart_rate    = Column(Float, nullable=True)   # Welford mean
    m2_heart_rate     = Column(Float, nullable=True)   # Welford M2 → std = sqrt(M2/(n-1))
    avg_hrv_sdnn      = Column(Float, nullable=True)
    m2_hrv_sdnn       = Column(Float, nullable=True)
    avg_hrv_rmssd     = Column(Float, nullable=True)
    avg_stress_level  = Column(Float, nullable=True)
    std_heart_rate    = Column(Float, nullable=True)   # kept for legacy reads; updated from M2
    std_hrv_sdnn      = Column(Float, nullable=True)
    measurement_count = Column(Integer, default=0)
    last_updated      = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<UserBaseline(user_id={self.user_id}, count={self.measurement_count})>"


class DemographicBaseline(Base):
    """
    Population baseline — seeded from NHANES (independent-sample survey),
    then updated incrementally via Welford online algorithm as app data accumulates.
    std = sqrt(M2 / (n-1))
    """

    __tablename__ = "demographic_baselines"

    id             = Column(Integer, primary_key=True, index=True)
    gender         = Column(String(10), nullable=False)   # male / female / all
    age_group      = Column(Integer, nullable=False)      # decade: 20 30 40 50 60

    # HR stats — Welford state (seeded from NHANES)
    avg_heart_rate = Column(Float, nullable=True)
    std_heart_rate = Column(Float, nullable=True)   # legacy; derived from M2 when n>1
    m2_heart_rate  = Column(Float, nullable=True)   # Welford M2
    sample_count   = Column(Integer, default=0)

    # APG b/a (Takazawa 1998 — literature, fixed)
    b_over_a_ref   = Column(Float, nullable=True)
    b_over_a_std   = Column(Float, nullable=True)

    # HRV SDNN — Welford state (seeded from Task Force 1996)
    avg_hrv_sdnn   = Column(Float, nullable=True)
    std_hrv_sdnn   = Column(Float, nullable=True)
    m2_hrv_sdnn    = Column(Float, nullable=True)

    source     = Column(String(200), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<DemographicBaseline(gender='{self.gender}', age={self.age_group}, n={self.sample_count})>"


class Notification(Base):
    """User notifications"""

    __tablename__ = "notifications"

    id        = Column(Integer, primary_key=True, index=True)
    user_id   = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    type      = Column(String(50), nullable=False, default="measurement_complete")
    title     = Column(String(255), nullable=False)
    message   = Column(Text, nullable=True)
    data_json = Column(Text, nullable=True)   # JSON string for type-specific payload
    is_read   = Column(Boolean, default=False)
    created_at= Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<Notification(id={self.id}, type={self.type}, read={self.is_read})>"


class MockPPGSource(Base):
    """BUT-PPG dataset recording metadata (dev-only)"""

    __tablename__ = "mock_ppg_sources"

    id        = Column(Integer, primary_key=True, index=True)
    record_id = Column(String(50), unique=True, nullable=False)
    hr_ref    = Column(Float, nullable=True)
    quality   = Column(Integer, default=1)
    format    = Column(String(1), nullable=True)   # 'A' or 'B'
    gender    = Column(String(10), nullable=True)
    age       = Column(Integer, nullable=True)
    notes     = Column(Text, nullable=True)
    created_at= Column(DateTime(timezone=True), server_default=func.now())

    packets = relationship("MockPPGPacket", back_populates="source", cascade="all, delete-orphan")


class MockPPGPacket(Base):
    """BLE-packet-shaped PPG data (dev-only, 12 × 10-bit per row)"""

    __tablename__ = "mock_ppg_packets"

    id           = Column(Integer, primary_key=True, index=True)
    source_id    = Column(Integer, ForeignKey("mock_ppg_sources.id", ondelete="CASCADE"), nullable=False, index=True)
    packet_index = Column(Integer, nullable=False)
    sync_byte    = Column(Integer, default=0xAA)
    packet_bytes = Column(LargeBinary(15), nullable=False)
    battery_level= Column(Integer, default=100)
    crc          = Column(Integer, nullable=True)
    created_at   = Column(DateTime(timezone=True), server_default=func.now())

    source = relationship("MockPPGSource", back_populates="packets")

"""
User model
"""
from sqlalchemy import Column, Integer, String, DateTime, Float, Boolean, func
from app.db.database import Base


class User(Base):
    """User model for authentication and profile"""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    username = Column(String(100), nullable=True)
    hashed_password = Column(String(255), nullable=True)  # Only for email auth

    # OAuth provider info
    provider = Column(String(20), nullable=True)  # 'email', 'kakao', 'google'
    provider_id = Column(String(255), nullable=True)  # OAuth provider's user ID

    # Demographics
    gender = Column(String(10), nullable=True)  # 'male', 'female', 'other'
    birth_year = Column(Integer, nullable=True)

    # Health profile (optional fields)
    height = Column(Float, nullable=True)  # Height in cm
    weight = Column(Float, nullable=True)  # Weight in kg
    has_diabetes = Column(Boolean, nullable=True)  # Diabetes status

    # Profile completion flag
    is_profile_complete = Column(Boolean, default=False, nullable=False)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<User(id={self.id}, email='{self.email}', provider='{self.provider}')>"

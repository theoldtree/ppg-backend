"""
User Pydantic schemas for request/response validation
"""
from typing import Optional
from pydantic import BaseModel, EmailStr, Field
from datetime import datetime


# Base schema with common fields
class UserBase(BaseModel):
    email: EmailStr
    username: Optional[str] = None


# Schema for user creation (signup)
class UserCreate(UserBase):
    password: str = Field(..., min_length=8, description="Password (min 8 characters)")
    gender: Optional[str] = Field(None, pattern="^(male|female|other)$")
    birth_year: Optional[int] = Field(None, ge=1900, le=2024)


# Schema for user update (profile edit)
class UserUpdate(BaseModel):
    username: Optional[str] = None
    gender: Optional[str] = Field(None, pattern="^(male|female|other)$")
    birth_year: Optional[int] = Field(None, ge=1900, le=2024)
    height: Optional[float] = Field(None, ge=50, le=250, description="Height in cm")
    weight: Optional[float] = Field(None, ge=20, le=300, description="Weight in kg")
    has_diabetes: Optional[bool] = None


# Schema for profile completion (first login)
class ProfileComplete(BaseModel):
    height: Optional[float] = Field(None, ge=50, le=250, description="Height in cm")
    weight: Optional[float] = Field(None, ge=20, le=300, description="Weight in kg")
    has_diabetes: Optional[bool] = None


# Schema for user response (what we return to client)
class UserResponse(UserBase):
    id: int
    provider: Optional[str] = None
    gender: Optional[str] = None
    birth_year: Optional[int] = None
    height: Optional[float] = None
    weight: Optional[float] = None
    has_diabetes: Optional[bool] = None
    is_profile_complete: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# Schema for login request
class UserLogin(BaseModel):
    email: EmailStr
    password: str


# Schema for token response
class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


# Schema for OAuth callback data
class OAuthUserData(BaseModel):
    email: EmailStr
    provider: str  # 'kakao' or 'google'
    provider_id: str
    username: Optional[str] = None
    gender: Optional[str] = None
    birth_year: Optional[int] = None

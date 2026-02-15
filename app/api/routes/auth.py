"""
Authentication API routes
"""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from typing import Optional
from datetime import timedelta

from app.db.database import get_db
from app.db.models.user import User
from app.db.schemas.user import (
    UserCreate,
    UserLogin,
    UserResponse,
    TokenResponse,
    ProfileComplete,
    UserUpdate,
)
from app.core.security import (
    get_password_hash,
    verify_password,
    create_access_token,
    decode_access_token,
)
from app.core.config import settings

router = APIRouter(prefix="/auth", tags=["Authentication"])
security = HTTPBearer()


# Helper function to get current user from token
def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    """Get current user from JWT token"""
    token = credentials.credentials
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
        )

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    return user


@router.post("/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def signup(user_data: UserCreate, db: Session = Depends(get_db)):
    """
    Register a new user with email and password

    - **email**: User email (must be unique)
    - **password**: User password (min 8 characters)
    - **username**: Optional username
    - **gender**: Optional gender (male/female/other)
    - **birth_year**: Optional birth year
    """
    # Check if user already exists
    existing_user = db.query(User).filter(User.email == user_data.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    # Create new user
    hashed_password = get_password_hash(user_data.password)
    new_user = User(
        email=user_data.email,
        username=user_data.username,
        hashed_password=hashed_password,
        provider="email",
        gender=user_data.gender,
        birth_year=user_data.birth_year,
        is_profile_complete=False,  # Profile not complete yet
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # Create access token
    access_token = create_access_token(
        data={"sub": str(new_user.id), "email": new_user.email}
    )

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user=UserResponse.from_orm(new_user),
    )


@router.post("/login", response_model=TokenResponse)
def login(credentials: UserLogin, db: Session = Depends(get_db)):
    """
    Login with email and password

    - **email**: User email
    - **password**: User password
    """
    # Find user by email
    user = db.query(User).filter(User.email == credentials.email).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    # Verify password
    if not user.hashed_password or not verify_password(
        credentials.password, user.hashed_password
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    # Create access token
    access_token = create_access_token(
        data={"sub": str(user.id), "email": user.email}
    )

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user=UserResponse.from_orm(user),
    )


@router.get("/me", response_model=UserResponse)
def get_current_user_info(current_user: User = Depends(get_current_user)):
    """
    Get current user information

    Requires authentication token in Authorization header
    """
    return UserResponse.from_orm(current_user)


@router.put("/profile/complete", response_model=UserResponse)
def complete_profile(
    profile_data: ProfileComplete,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Complete user profile (first login)

    - **height**: Height in cm (optional)
    - **weight**: Weight in kg (optional)
    - **has_diabetes**: Diabetes status (optional)
    """
    # Update profile fields
    if profile_data.height is not None:
        current_user.height = profile_data.height
    if profile_data.weight is not None:
        current_user.weight = profile_data.weight
    if profile_data.has_diabetes is not None:
        current_user.has_diabetes = profile_data.has_diabetes

    # Mark profile as complete
    current_user.is_profile_complete = True

    db.commit()
    db.refresh(current_user)

    return UserResponse.from_orm(current_user)


@router.put("/profile", response_model=UserResponse)
def update_profile(
    profile_data: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Update user profile

    - **username**: Username
    - **gender**: Gender (male/female/other)
    - **birth_year**: Birth year
    - **height**: Height in cm
    - **weight**: Weight in kg
    - **has_diabetes**: Diabetes status
    """
    # Update fields that are provided
    update_data = profile_data.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(current_user, field, value)

    db.commit()
    db.refresh(current_user)

    return UserResponse.from_orm(current_user)


@router.post("/logout")
def logout():
    """
    Logout user

    Note: Since we're using JWT tokens, logout is handled on the client side
    by removing the token from storage. This endpoint is for API consistency.
    """
    return {"message": "Successfully logged out"}


# ==============================================================================
# OAuth Routes (Kakao & Google)
# ==============================================================================

from app.services.oauth import KakaoOAuthService, GoogleOAuthService


@router.get("/kakao/url")
async def get_kakao_oauth_url():
    """Get Kakao OAuth authorization URL"""
    auth_url = await KakaoOAuthService.get_authorization_url()
    return {"url": auth_url}


@router.get("/kakao/callback", response_model=TokenResponse)
async def kakao_callback(code: str, db: Session = Depends(get_db)):
    """
    Kakao OAuth callback endpoint

    This endpoint is called by Kakao after user authorization.
    It exchanges the authorization code for user information and creates/logs in the user.
    """
    # Get access token from Kakao
    access_token = await KakaoOAuthService.get_access_token(code)

    # Get user info from Kakao
    kakao_user = await KakaoOAuthService.get_user_info(access_token)

    if not kakao_user.get("email"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email not provided by Kakao. Please allow email access.",
        )

    # Check if user already exists
    existing_user = (
        db.query(User)
        .filter(
            User.provider == "kakao",
            User.provider_id == kakao_user["id"],
        )
        .first()
    )

    if existing_user:
        # User exists, log them in
        user = existing_user
    else:
        # Create new user
        user = User(
            email=kakao_user["email"],
            username=kakao_user.get("nickname"),
            provider="kakao",
            provider_id=kakao_user["id"],
            gender=kakao_user.get("gender"),
            birth_year=kakao_user.get("birth_year"),
            is_profile_complete=False,  # Profile not complete yet
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    # Create access token
    jwt_token = create_access_token(data={"sub": str(user.id), "email": user.email})

    return TokenResponse(
        access_token=jwt_token, token_type="bearer", user=UserResponse.from_orm(user)
    )


@router.get("/google/url")
async def get_google_oauth_url():
    """Get Google OAuth authorization URL"""
    auth_url = await GoogleOAuthService.get_authorization_url()
    return {"url": auth_url}


@router.get("/google/callback", response_model=TokenResponse)
async def google_callback(code: str, db: Session = Depends(get_db)):
    """
    Google OAuth callback endpoint

    This endpoint is called by Google after user authorization.
    It exchanges the authorization code for user information and creates/logs in the user.
    """
    # Get access token from Google
    access_token = await GoogleOAuthService.get_access_token(code)

    # Get user info from Google
    google_user = await GoogleOAuthService.get_user_info(access_token)

    if not google_user.get("email"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email not provided by Google. Please allow email access.",
        )

    # Check if user already exists
    existing_user = (
        db.query(User)
        .filter(
            User.provider == "google",
            User.provider_id == google_user["id"],
        )
        .first()
    )

    if existing_user:
        # User exists, log them in
        user = existing_user
    else:
        # Create new user
        user = User(
            email=google_user["email"],
            username=google_user.get("name"),
            provider="google",
            provider_id=google_user["id"],
            gender=google_user.get("gender"),
            birth_year=google_user.get("birth_year"),
            is_profile_complete=False,  # Profile not complete yet
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    # Create access token
    jwt_token = create_access_token(data={"sub": str(user.id), "email": user.email})

    return TokenResponse(
        access_token=jwt_token, token_type="bearer", user=UserResponse.from_orm(user)
    )

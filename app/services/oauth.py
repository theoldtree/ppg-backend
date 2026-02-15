"""
OAuth service for Kakao and Google authentication
"""
import httpx
from typing import Optional, Dict
from fastapi import HTTPException, status

from app.core.config import settings


class KakaoOAuthService:
    """Kakao OAuth authentication service"""

    AUTH_URL = "https://kauth.kakao.com/oauth/authorize"
    TOKEN_URL = "https://kauth.kakao.com/oauth/token"
    USER_INFO_URL = "https://kapi.kakao.com/v2/user/me"

    @classmethod
    async def get_authorization_url(cls) -> str:
        """Get Kakao OAuth authorization URL"""
        if not settings.KAKAO_CLIENT_ID or not settings.KAKAO_REDIRECT_URI:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Kakao OAuth not configured",
            )

        params = {
            "client_id": settings.KAKAO_CLIENT_ID,
            "redirect_uri": settings.KAKAO_REDIRECT_URI,
            "response_type": "code",
        }

        query_string = "&".join([f"{k}={v}" for k, v in params.items()])
        return f"{cls.AUTH_URL}?{query_string}"

    @classmethod
    async def get_access_token(cls, code: str) -> str:
        """Exchange authorization code for access token"""
        data = {
            "grant_type": "authorization_code",
            "client_id": settings.KAKAO_CLIENT_ID,
            "redirect_uri": settings.KAKAO_REDIRECT_URI,
            "code": code,
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(cls.TOKEN_URL, data=data)

            if response.status_code != 200:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Failed to get access token from Kakao",
                )

            token_data = response.json()
            return token_data["access_token"]

    @classmethod
    async def get_user_info(cls, access_token: str) -> Dict:
        """
        Get user information from Kakao

        Returns:
            Dict with keys: id, email, nickname, gender, birthday (MMDD), birthyear
        """
        headers = {"Authorization": f"Bearer {access_token}"}

        async with httpx.AsyncClient() as client:
            response = await client.get(cls.USER_INFO_URL, headers=headers)

            if response.status_code != 200:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Failed to get user info from Kakao",
                )

            user_data = response.json()

            # Extract user information
            kakao_account = user_data.get("kakao_account", {})
            profile = kakao_account.get("profile", {})

            # Parse gender
            gender = None
            if kakao_account.get("gender"):
                gender_value = kakao_account["gender"]
                gender = "male" if gender_value == "male" else "female"

            # Parse birth year
            birth_year = None
            if kakao_account.get("birthyear"):
                try:
                    birth_year = int(kakao_account["birthyear"])
                except ValueError:
                    pass

            return {
                "id": str(user_data["id"]),
                "email": kakao_account.get("email"),
                "nickname": profile.get("nickname"),
                "gender": gender,
                "birth_year": birth_year,
            }


class GoogleOAuthService:
    """Google OAuth authentication service"""

    AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
    TOKEN_URL = "https://oauth2.googleapis.com/token"
    USER_INFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"
    PEOPLE_API_URL = "https://people.googleapis.com/v1/people/me"

    @classmethod
    async def get_authorization_url(cls) -> str:
        """Get Google OAuth authorization URL"""
        if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_REDIRECT_URI:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Google OAuth not configured",
            )

        params = {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "redirect_uri": settings.GOOGLE_REDIRECT_URI,
            "response_type": "code",
            "scope": "openid email profile https://www.googleapis.com/auth/user.birthday.read https://www.googleapis.com/auth/user.gender.read",
            "access_type": "offline",
        }

        query_string = "&".join([f"{k}={v}" for k, v in params.items()])
        return f"{cls.AUTH_URL}?{query_string}"

    @classmethod
    async def get_access_token(cls, code: str) -> str:
        """Exchange authorization code for access token"""
        data = {
            "grant_type": "authorization_code",
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "redirect_uri": settings.GOOGLE_REDIRECT_URI,
            "code": code,
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(cls.TOKEN_URL, data=data)

            if response.status_code != 200:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Failed to get access token from Google",
                )

            token_data = response.json()
            return token_data["access_token"]

    @classmethod
    async def get_user_info(cls, access_token: str) -> Dict:
        """
        Get user information from Google

        Returns:
            Dict with keys: id, email, name, gender, birth_year
        """
        headers = {"Authorization": f"Bearer {access_token}"}

        async with httpx.AsyncClient() as client:
            # Get basic user info
            response = await client.get(cls.USER_INFO_URL, headers=headers)

            if response.status_code != 200:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Failed to get user info from Google",
                )

            user_data = response.json()

            # Get additional info (gender, birthday) from People API
            params = {"personFields": "genders,birthdays"}
            people_response = await client.get(
                cls.PEOPLE_API_URL, headers=headers, params=params
            )

            gender = None
            birth_year = None

            if people_response.status_code == 200:
                people_data = people_response.json()

                # Extract gender
                genders = people_data.get("genders", [])
                if genders and len(genders) > 0:
                    gender_value = genders[0].get("value", "").lower()
                    if gender_value in ["male", "female"]:
                        gender = gender_value
                    elif gender_value:
                        gender = "other"

                # Extract birth year
                birthdays = people_data.get("birthdays", [])
                if birthdays and len(birthdays) > 0:
                    date = birthdays[0].get("date", {})
                    year = date.get("year")
                    if year:
                        birth_year = year

            return {
                "id": user_data["id"],
                "email": user_data.get("email"),
                "name": user_data.get("name"),
                "gender": gender,
                "birth_year": birth_year,
            }

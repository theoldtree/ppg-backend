"""
Generate a long-lived JWT for the DEV_MOCK_USER (user id=1).
Usage: cd ppg-backend && python scripts/gen_token.py

Paste the output token into AuthContext.tsx as DEV_MOCK_TOKEN.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta
from jose import jwt
from app.core.config import settings

data = {"sub": "1", "email": "yjeongmu@gmail.com"}
token = jwt.encode(
    {**data, "exp": datetime.utcnow() + timedelta(days=365)},
    settings.SECRET_KEY,
    algorithm=settings.ALGORITHM,
)
print(token)

import secrets
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
from uuid import uuid4

from jose import jwt, JWTError
from passlib.context import CryptContext
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.user import User, RefreshToken, UserRole


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class AuthService:
    def __init__(self, db: AsyncSession):
        self.db = db

    def hash_password(self, password: str) -> str:
        return pwd_context.hash(password)

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        return pwd_context.verify(plain_password, hashed_password)

    def create_access_token(self, user_id: str, role: str) -> Tuple[str, int]:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        to_encode = {
            "sub": user_id,
            "role": role,
            "exp": expire,
            "type": "access"
        }
        encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
        expires_in = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
        return encoded_jwt, expires_in

    def create_refresh_token(self) -> str:
        return secrets.token_urlsafe(64)

    def hash_refresh_token(self, token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    async def store_refresh_token(
        self,
        user_id: str,
        token: str,
        expires_at: datetime
    ) -> RefreshToken:
        token_hash = self.hash_refresh_token(token)
        refresh_token = RefreshToken(
            id=str(uuid4()),
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
            revoked=False,
        )
        self.db.add(refresh_token)
        await self.db.commit()
        await self.db.refresh(refresh_token)
        return refresh_token

    async def validate_refresh_token(self, token: str) -> Optional[RefreshToken]:
        token_hash = self.hash_refresh_token(token)
        result = await self.db.execute(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        )
        stored_token = result.scalar_one_or_none()

        if not stored_token:
            return None

        if stored_token.revoked:
            return None

        if stored_token.expires_at < datetime.now(timezone.utc):
            return None

        return stored_token

    async def revoke_refresh_token(self, token: str) -> bool:
        token_hash = self.hash_refresh_token(token)
        result = await self.db.execute(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        )
        stored_token = result.scalar_one_or_none()

        if not stored_token:
            return False

        stored_token.revoked = True
        await self.db.commit()
        return True

    async def revoke_all_user_tokens(self, user_id: str) -> int:
        result = await self.db.execute(
            select(RefreshToken).where(
                RefreshToken.user_id == user_id,
                RefreshToken.revoked == False
            )
        )
        tokens = result.scalars().all()
        count = 0
        for token in tokens:
            token.revoked = True
            count += 1
        await self.db.commit()
        return count

    def decode_access_token(self, token: str) -> Optional[dict]:
        try:
            payload = jwt.decode(
                token,
                settings.SECRET_KEY,
                algorithms=[settings.ALGORITHM]
            )
            if payload.get("type") != "access":
                return None
            return payload
        except JWTError:
            return None

    async def authenticate_user(self, email: str, password: str) -> Optional[User]:
        result = await self.db.execute(
            select(User).where(User.email == email)
        )
        user = result.scalar_one_or_none()

        if not user:
            return None

        if not self.verify_password(password, user.hashed_password):
            return None

        return user

    async def get_user_by_id(self, user_id: str) -> Optional[User]:
        result = await self.db.execute(
            select(User).where(User.id == user_id)
        )
        return result.scalar_one_or_none()

    async def register_user(
        self,
        email: str,
        password: str,
        role: str = "auditor"
    ) -> User:
        existing = await self.db.execute(
            select(User).where(User.email == email)
        )
        if existing.scalar_one_or_none():
            raise ValueError("Email already registered")

        hashed_password = self.hash_password(password)
        user = User(
            id=str(uuid4()),
            email=email,
            hashed_password=hashed_password,
            role=UserRole(role),
            is_active=True,
        )
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def cleanup_expired_tokens(self) -> int:
        result = await self.db.execute(
            delete(RefreshToken).where(RefreshToken.expires_at < datetime.now(timezone.utc))
        )
        await self.db.commit()
        return result.rowcount or 0
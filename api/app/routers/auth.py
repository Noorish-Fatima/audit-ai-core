from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request, Response, Body
from fastapi.security import HTTPBearer
from pydantic import EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.session import get_session
from app.services.auth_service import AuthService
from app.services.rate_limiter import login_rate_limit, add_rate_limit_headers
from app.dependencies.auth import get_current_user, get_current_user_optional, require_role
from app.schemas.auth import (
    UserRegister,
    UserLogin,
    TokenResponse,
    RefreshTokenRequest,
    AuthResponse,
    UserResponse,
    MessageResponse,
)
from app.models.user import UserRole


router = APIRouter(prefix="/auth", tags=["auth"])
security = HTTPBearer(auto_error=False)


@router.post(
    "/register",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user"
)
async def register(
    request: Request,
    response: Response,
    user_data: UserRegister,
    db: AsyncSession = Depends(get_session),
    auth_service: AuthService = Depends(lambda db=Depends(get_session): AuthService(db))
):
    if settings.ENVIRONMENT == "production" and not settings.ALLOW_REGISTRATION_IN_DEV:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Registration is not allowed in production"
        )

    try:
        user = await auth_service.register_user(
            email=user_data.email,
            password=user_data.password,
            role=user_data.role
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

    access_token, expires_in = auth_service.create_access_token(user.id, user.role)
    refresh_token = auth_service.create_refresh_token()
    refresh_expires = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    await auth_service.store_refresh_token(user.id, refresh_token, refresh_expires)

    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=settings.ENVIRONMENT == "production",
        samesite="strict",
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        path="/api/v1/auth"
    )

    return AuthResponse(
        user=UserResponse.model_validate(user),
        access_token=access_token,
        expires_in=expires_in
    )


@router.post(
    "/login",
    response_model=AuthResponse,
    summary="Login with email and password"
)
async def login(
    request: Request,
    response: Response,
    credentials: UserLogin,
    db: AsyncSession = Depends(get_session),
    auth_service: AuthService = Depends(lambda db=Depends(get_session): AuthService(db)),
):
    await login_rate_limit(request, credentials.email)

    user = await auth_service.authenticate_user(credentials.email, credentials.password)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account is disabled"
        )

    access_token, expires_in = auth_service.create_access_token(user.id, user.role)
    refresh_token = auth_service.create_refresh_token()
    refresh_expires = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    await auth_service.store_refresh_token(user.id, refresh_token, refresh_expires)

    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=settings.ENVIRONMENT == "production",
        samesite="strict",
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        path="/api/v1/auth"
    )

    add_rate_limit_headers(request, response)

    return AuthResponse(
        user=UserResponse.model_validate(user),
        access_token=access_token,
        expires_in=expires_in
    )


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Refresh access token using refresh token"
)
async def refresh_token(
    request: Request,
    response: Response,
    refresh_token: Optional[str] = Body(None, embed=True),
    db: AsyncSession = Depends(get_session),
    auth_service: AuthService = Depends(lambda db=Depends(get_session): AuthService(db))
):
    cookie_token = request.cookies.get("refresh_token")
    token = refresh_token or cookie_token

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token required"
        )

    stored_token = await auth_service.validate_refresh_token(token)
    if not stored_token:
        response.delete_cookie(key="refresh_token", path="/api/v1/auth")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token"
        )

    user = await auth_service.get_user_by_id(stored_token.user_id)
    if not user or not user.is_active:
        response.delete_cookie(key="refresh_token", path="/api/v1/auth")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or disabled"
        )

    await auth_service.revoke_refresh_token(token)

    access_token, expires_in = auth_service.create_access_token(user.id, user.role)
    new_refresh_token = auth_service.create_refresh_token()
    refresh_expires = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    await auth_service.store_refresh_token(user.id, new_refresh_token, refresh_expires)

    response.set_cookie(
        key="refresh_token",
        value=new_refresh_token,
        httponly=True,
        secure=settings.ENVIRONMENT == "production",
        samesite="strict",
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        path="/api/v1/auth"
    )

    return TokenResponse(
        access_token=access_token,
        expires_in=expires_in
    )


@router.post(
    "/logout",
    response_model=MessageResponse,
    summary="Logout and revoke refresh token"
)
async def logout(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_session),
    auth_service: AuthService = Depends(lambda db=Depends(get_session): AuthService(db)),
    current_user: Optional = Depends(get_current_user_optional)
):
    cookie_token = request.cookies.get("refresh_token")
    if cookie_token:
        await auth_service.revoke_refresh_token(cookie_token)

    response.delete_cookie(key="refresh_token", path="/api/v1/auth")

    return MessageResponse(message="Successfully logged out")


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get current user profile"
)
async def get_me(
    current_user = Depends(get_current_user)
):
    return UserResponse.model_validate(current_user)


@router.post(
    "/logout-all",
    response_model=MessageResponse,
    summary="Logout from all devices"
)
async def logout_all(
    current_user = Depends(get_current_user),
    auth_service: AuthService = Depends(lambda db=Depends(get_session): AuthService(db))
):
    count = await auth_service.revoke_all_user_tokens(current_user.id)
    return MessageResponse(message=f"Revoked {count} refresh tokens")
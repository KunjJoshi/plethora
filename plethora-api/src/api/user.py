from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
import httpx
from logging import getLogger
import os
from dotenv import load_dotenv

from schemas.user import (
    UserCreate, UserInDB, UserCreateWithUUID, UserLogin,
    UserUpdate, PasswordResetRequest, PasswordResetConfirm, RefreshTokenRequest,
)
from services.user_service import (
    insert_into_db_user, verify_login_attempt, verify_or_create_oauth_user,
    get_user_by_id, update_user_profile,
)
from config_api.session import get_db
from config_api.dependencies import get_current_user

load_dotenv()
logger = getLogger(__name__)

router = APIRouter(prefix="/api/v1/users", tags=["Users"])

SUPABASE_URL = os.environ.get("SUPABASE_URL_REST")
ANON_KEY = os.environ.get("SUPABASE_ANON_KEY")

_bearer = HTTPBearer()

# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class UserResponse(BaseModel):
    user: Optional[UserInDB] = None
    success: bool
    message: Optional[str] = None


class LoginResponse(BaseModel):
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    token_type: str = "bearer"
    user: Optional[UserInDB] = None
    success: bool
    message: Optional[str] = None


class MessageResponse(BaseModel):
    success: bool
    message: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _supabase_error(data: dict, fallback: str) -> str:
    return (
        data.get("error_description")
        or data.get("msg")
        or data.get("error")
        or fallback
    )


# ---------------------------------------------------------------------------
# Public endpoints (no auth required)
# ---------------------------------------------------------------------------

@router.post("/register-user", response_model=UserResponse)
async def register_user(user: UserCreate, db: Session = Depends(get_db)) -> UserResponse:
    try:
        async with httpx.AsyncClient() as client:
            auth_response = await client.post(
                f"{SUPABASE_URL}/auth/v1/signup",
                headers={"apikey": ANON_KEY, "Content-Type": "application/json"},
                json={"email": user.email, "password": user.password},
            )

        auth_data = auth_response.json()

        if auth_response.status_code != 200 or "error" in auth_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=_supabase_error(auth_data, "Authentication signup failed"),
            )

        db_data = UserCreateWithUUID(
            id=auth_data["user"]["id"],
            email=user.email,
            username=user.username,
            name=user.name,
            address=user.address,
        )
        result = insert_into_db_user(db, db_data)
        return UserResponse(user=result, success=True, message="User registered successfully")
    except HTTPException:
        raise
    except ValueError as e:
        return UserResponse(success=False, message=str(e))
    except Exception as e:
        logger.error(f"register error: {e}")
        return UserResponse(success=False, message="An error occurred while registering user")


@router.post("/login", response_model=LoginResponse)
async def login_user(user: UserLogin, db: Session = Depends(get_db)) -> LoginResponse:
    try:
        async with httpx.AsyncClient() as client:
            auth_response = await client.post(
                f"{SUPABASE_URL}/auth/v1/token?grant_type=password",
                headers={"apikey": ANON_KEY, "Content-Type": "application/json"},
                json={"email": user.email, "password": user.password},
            )

        auth_data = auth_response.json()

        if auth_response.status_code != 200 or "error" in auth_data:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=_supabase_error(auth_data, "Invalid email or password"),
            )

        db_user = verify_login_attempt(db, email=user.email, token=auth_data["access_token"])
        return LoginResponse(
            access_token=auth_data["access_token"],
            refresh_token=auth_data.get("refresh_token"),
            user=db_user,
            success=True,
            message="Login successful",
        )
    except HTTPException:
        raise
    except ValueError as e:
        return LoginResponse(success=False, message=str(e))
    except Exception as e:
        logger.error(f"login error: {e}")
        return LoginResponse(success=False, message="An error occurred during login")


@router.post("/refresh", response_model=LoginResponse)
async def refresh_token(body: RefreshTokenRequest) -> LoginResponse:
    try:
        async with httpx.AsyncClient() as client:
            auth_response = await client.post(
                f"{SUPABASE_URL}/auth/v1/token?grant_type=refresh_token",
                headers={"apikey": ANON_KEY, "Content-Type": "application/json"},
                json={"refresh_token": body.refresh_token},
            )

        auth_data = auth_response.json()

        if auth_response.status_code != 200 or "error" in auth_data:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=_supabase_error(auth_data, "Invalid or expired refresh token"),
            )

        return LoginResponse(
            access_token=auth_data["access_token"],
            refresh_token=auth_data.get("refresh_token"),
            success=True,
            message="Token refreshed successfully",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"refresh error: {e}")
        return LoginResponse(success=False, message="An error occurred while refreshing token")


@router.post("/reset-password", response_model=MessageResponse)
async def request_password_reset(body: PasswordResetRequest) -> MessageResponse:
    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                f"{SUPABASE_URL}/auth/v1/recover",
                headers={"apikey": ANON_KEY, "Content-Type": "application/json"},
                json={"email": body.email},
            )
        # Always return success — never confirm whether an email exists
        return MessageResponse(success=True, message="If an account exists, a password reset email has been sent")
    except Exception as e:
        logger.error(f"password reset request error: {e}")
        return MessageResponse(success=False, message="An error occurred. Please try again.")


@router.post("/reset-password/confirm", response_model=MessageResponse)
async def confirm_password_reset(body: PasswordResetConfirm) -> MessageResponse:
    try:
        async with httpx.AsyncClient() as client:
            auth_response = await client.put(
                f"{SUPABASE_URL}/auth/v1/user",
                headers={
                    "apikey": ANON_KEY,
                    "Authorization": f"Bearer {body.access_token}",
                    "Content-Type": "application/json",
                },
                json={"password": body.new_password},
            )

        auth_data = auth_response.json()

        if auth_response.status_code != 200 or "error" in auth_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=_supabase_error(auth_data, "Password reset failed"),
            )

        return MessageResponse(success=True, message="Password reset successfully")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"password reset confirm error: {e}")
        return MessageResponse(success=False, message="An error occurred while resetting password")


# ---------------------------------------------------------------------------
# Authenticated endpoints
# ---------------------------------------------------------------------------

@router.post("/logout", response_model=MessageResponse)
async def logout(credentials: HTTPAuthorizationCredentials = Depends(_bearer)) -> MessageResponse:
    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                f"{SUPABASE_URL}/auth/v1/logout",
                headers={
                    "apikey": ANON_KEY,
                    "Authorization": f"Bearer {credentials.credentials}",
                },
            )
        return MessageResponse(success=True, message="Logged out successfully")
    except Exception as e:
        logger.error(f"logout error: {e}")
        return MessageResponse(success=False, message="An error occurred during logout")


@router.get("/me", response_model=UserInDB)
def get_me(current_user: UserInDB = Depends(get_current_user)) -> UserInDB:
    return current_user


@router.patch("/me", response_model=UserInDB)
def update_me(
    update_data: UserUpdate,
    current_user: UserInDB = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserInDB:
    try:
        return update_user_profile(db, str(current_user.id), update_data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


class OAuthCallbackRequest(BaseModel):
    access_token: str


@router.post("/oauth-callback", response_model=LoginResponse)
async def oauth_callback(payload: OAuthCallbackRequest, db: Session = Depends(get_db)) -> LoginResponse:
    try:
        db_user = verify_or_create_oauth_user(db, token=payload.access_token)
        return LoginResponse(
            access_token=payload.access_token,
            token_type="bearer",
            user=db_user,
            success=True,
            message="Login successful",
        )
    except ValueError as e:
        return LoginResponse(success=False, message=str(e))
    except Exception as e:
        logger.error(f"OAuth callback error: {e}")
        return LoginResponse(success=False, message="An error occurred during OAuth login")


# Must be last — path param /{user_id} would otherwise capture static routes above
@router.get("/{user_id}", response_model=UserInDB)
def get_user(
    user_id: str,
    db: Session = Depends(get_db),
    _: UserInDB = Depends(get_current_user),
) -> UserInDB:
    try:
        return get_user_by_id(db, user_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

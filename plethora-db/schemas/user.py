from pydantic import BaseModel, EmailStr
from typing import Optional
from uuid import UUID
from datetime import datetime
from models.user import UserType, UserStatus


class UserBase(BaseModel):
    email: EmailStr
    username: str
    name: Optional[str] = None
    address: Optional[str] = None


class UserInDB(UserBase):
    id: UUID
    user_type: UserType
    user_status: UserStatus
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class UserCreate(UserBase):
    password: str

class UserCreateWithUUID(UserBase):
    id: UUID

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserUpdate(BaseModel):
    username: Optional[str] = None
    name: Optional[str] = None
    address: Optional[str] = None

class PasswordResetRequest(BaseModel):
    email: EmailStr

class PasswordResetConfirm(BaseModel):
    access_token: str  # recovery token extracted from the Supabase reset link
    new_password: str

class RefreshTokenRequest(BaseModel):
    refresh_token: str

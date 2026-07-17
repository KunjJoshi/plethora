import enum
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean, Enum, func
from sqlalchemy.dialects.postgresql import UUID
from database import Base

class UserType(str, enum.Enum):
    SINGLE_USER = "single-user"
    ORG_MEMBER = "org-member"
    ORG_ADMIN = "org-admin"

class UserStatus(str, enum.Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    DELETED = "deleted"
    ACCOUNT_NOT_CREATED = "account-not-created"
    ACCOUNT_NOT_VERIFIED = "account-not-verified"


class User(Base):
    __tablename__ = "users"
    
    id = Column(UUID(as_uuid=True), primary_key=True)
    username = Column(String, nullable=False, unique=True)
    email = Column(String, nullable=False, unique=True)
    name = Column(String)
    address = Column(String)
    user_type = Column(Enum(UserType), nullable=False)
    user_status = Column(Enum(UserStatus), default=UserStatus.ACCOUNT_NOT_CREATED)
    is_active = Column(Boolean, server_default='false')
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

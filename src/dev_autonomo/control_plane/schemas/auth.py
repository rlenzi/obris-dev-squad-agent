"""Schemas Pydantic de auth/me."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from dev_autonomo.common.enums import UserRole


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=256)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_seconds: int


class UserPublic(BaseModel):
    id: UUID
    email: str
    full_name: str
    is_system_admin: bool
    active: bool
    created_at: datetime
    last_login_at: datetime | None = None


class ClientMembershipPublic(BaseModel):
    client_id: UUID
    client_slug: str
    client_name: str
    role: UserRole


class MeResponse(BaseModel):
    user: UserPublic
    memberships: list[ClientMembershipPublic]

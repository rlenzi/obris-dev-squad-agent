"""Schemas Pydantic de users e memberships."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from dev_autonomo.common.enums import UserRole


class UserPublic(BaseModel):
    """Vista publica de um user (sem hash de senha)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr
    full_name: str
    is_system_admin: bool
    active: bool
    last_login_at: datetime | None = None
    created_at: datetime


class ClientUserPublic(BaseModel):
    """User + role no contexto de um tenant especifico."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr
    full_name: str
    role: UserRole
    active: bool
    last_login_at: datetime | None = None
    membership_id: UUID
    created_at: datetime


class AdminClientUserCreate(BaseModel):
    """Criacao de user pelo system_admin: vincula a um cliente existente.

    Role default = CLIENT_ADMIN porque essa rota e usada pra dar a chave
    inicial de acesso ao tenant.
    """

    email: EmailStr
    full_name: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    role: UserRole = UserRole.CLIENT_ADMIN


class ClientUserInvite(BaseModel):
    """Convite/criacao de user pelo client_admin no proprio tenant.

    Roles permitidas: CLIENT_ADMIN, CLIENT_REVIEWER, CLIENT_VIEWER.
    """

    email: EmailStr
    full_name: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    role: UserRole = UserRole.CLIENT_VIEWER


class ClientUserUpdate(BaseModel):
    """Update parcial de user (client_admin)."""

    role: UserRole | None = None
    active: bool | None = None

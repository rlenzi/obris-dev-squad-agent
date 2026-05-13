"""Schemas Pydantic de credentials (encrypted_secrets)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from dev_autonomo.common.enums import SecretKind


class CredentialCreate(BaseModel):
    kind: SecretKind
    name: str = Field(..., min_length=1, max_length=255)
    value: str = Field(..., min_length=1, max_length=4096)


class CredentialRotate(BaseModel):
    value: str = Field(..., min_length=1, max_length=4096)


class CredentialPublic(BaseModel):
    """Sem o valor — segredos NUNCA voltam pra resposta da API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    client_id: UUID | None
    kind: SecretKind
    name: str
    last_rotated_at: datetime | None
    last_used_at: datetime | None
    created_at: datetime
    updated_at: datetime

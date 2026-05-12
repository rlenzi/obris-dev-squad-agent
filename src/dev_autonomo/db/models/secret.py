"""Vault interno: segredos criptografados com Fernet (encrypt-at-rest)."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, LargeBinary, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from dev_autonomo.common.enums import SecretKind
from dev_autonomo.db.base import Base
from dev_autonomo.db.mixins import TimestampMixin


class EncryptedSecret(Base, TimestampMixin):
    """Secret criptografado. client_id NULL = secret system-level."""

    __tablename__ = "encrypted_secrets"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), index=True
    )

    name: Mapped[str] = mapped_column(String(255))
    kind: Mapped[SecretKind] = mapped_column(Enum(SecretKind, name="secret_kind_enum"))
    encrypted_value: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)

    last_rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

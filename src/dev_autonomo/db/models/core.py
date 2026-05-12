"""Tabelas core de multi-tenancy: Client, User, Membership, BillingPlan."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from dev_autonomo.common.enums import BillingPlanKind, UserRole
from dev_autonomo.db.base import Base
from dev_autonomo.db.mixins import TimestampMixin

if TYPE_CHECKING:
    from dev_autonomo.db.models.squad import Squad


class Client(Base, TimestampMixin):
    __tablename__ = "clients"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)

    jira_workspace_url: Mapped[str | None] = mapped_column(String(255))
    jira_email: Mapped[str | None] = mapped_column(String(255))
    jira_credential_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("encrypted_secrets.id", ondelete="SET NULL", use_alter=True, name="fk_clients_jira_credential_id_encrypted_secrets")
    )

    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    squads: Mapped[list["Squad"]] = relationship(back_populates="client", cascade="all, delete-orphan")
    memberships: Mapped[list["ClientMembership"]] = relationship(
        back_populates="client", cascade="all, delete-orphan"
    )
    billing_plan: Mapped["ClientBillingPlan | None"] = relationship(
        back_populates="client", uselist=False, cascade="all, delete-orphan"
    )


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255))
    hashed_password: Mapped[str | None] = mapped_column(String(255))

    is_system_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    memberships: Mapped[list["ClientMembership"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class ClientMembership(Base, TimestampMixin):
    __tablename__ = "client_memberships"
    __table_args__ = (UniqueConstraint("client_id", "user_id", name="uq_client_user"),)

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[UserRole] = mapped_column(Enum(UserRole, name="user_role_enum"), nullable=False)

    client: Mapped["Client"] = relationship(back_populates="memberships")
    user: Mapped["User"] = relationship(back_populates="memberships")


class ClientBillingPlan(Base, TimestampMixin):
    __tablename__ = "client_billing_plans"

    client_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), primary_key=True
    )
    plan_kind: Mapped[BillingPlanKind] = mapped_column(
        Enum(BillingPlanKind, name="billing_plan_kind_enum"), default=BillingPlanKind.HYBRID
    )

    base_fee_monthly_brl: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    included_quota_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    included_quota_tasks: Mapped[int] = mapped_column(Integer, default=0)
    overage_markup_pct: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=Decimal("0"))

    starts_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    client: Mapped["Client"] = relationship(back_populates="billing_plan")

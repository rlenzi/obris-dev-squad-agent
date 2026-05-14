"""Task (espelho interno do Jira do cliente) e CrossSquadRequest."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from dev_autonomo.common.enums import OutcomeStatus, TaskStage, TaskStatus
from dev_autonomo.db.base import Base
from dev_autonomo.db.mixins import TimestampMixin


class Task(Base, TimestampMixin):
    """Espelho local de uma task que vive no Jira do cliente."""

    __tablename__ = "tasks"
    __table_args__ = (
        UniqueConstraint(
            "jira_workspace_url", "jira_issue_key", name="uq_task_jira_external_id"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), index=True
    )
    squad_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("squads.id", ondelete="SET NULL"), index=True
    )

    jira_workspace_url: Mapped[str] = mapped_column(String(255))
    jira_issue_key: Mapped[str] = mapped_column(String(64))

    title: Mapped[str] = mapped_column(String(512))
    demand_payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    ba_spec: Mapped[dict | None] = mapped_column(JSONB)
    architect_plan: Mapped[dict | None] = mapped_column(JSONB)

    current_stage: Mapped[TaskStage] = mapped_column(
        Enum(TaskStage, name="task_stage_enum"), default=TaskStage.DEMAND_RECEIVED
    )
    status: Mapped[TaskStatus] = mapped_column(
        Enum(TaskStatus, name="task_status_enum"), default=TaskStatus.PENDING
    )

    parent_task_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="SET NULL")
    )
    assigned_agent_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("agent_instances.id", ondelete="SET NULL")
    )

    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # URL do PR no GitHub criado por esta task (preenchido pelo agente
    # quando chama github_create_pr). Link direto em vez de search.
    pr_url: Mapped[str | None] = mapped_column(String(512))

    # Managed Agents — session da Anthropic criada por managed_runner.
    # Promovido de demand_payload['anthropic_session_id'] pra coluna
    # queryable. Painel usa pra deep-link e debug.
    anthropic_session_id: Mapped[str | None] = mapped_column(String(64), index=True)

    # Outcomes (Anthropic grader) — populado durante stream via
    # span.outcome_evaluation_*. SKIPPED quando task rodou sem outcome
    # definido (legado ou opt-out).
    outcome_status: Mapped[OutcomeStatus] = mapped_column(
        Enum(OutcomeStatus, name="outcome_status_enum", create_type=False),
        default=OutcomeStatus.SKIPPED,
        nullable=False,
    )
    outcome_iterations: Mapped[int] = mapped_column(default=0, nullable=False)
    # Path no repo OU hash identificando a rubric usada (rubric textual
    # nao fica inteira aqui pra evitar payload grande).
    outcome_rubric_ref: Mapped[str | None] = mapped_column(String(255))

    parent: Mapped["Task | None"] = relationship(
        "Task",
        remote_side="Task.id",
        back_populates="subtasks",
        foreign_keys=[parent_task_id],
    )
    subtasks: Mapped[list["Task"]] = relationship(
        "Task",
        back_populates="parent",
        foreign_keys=[parent_task_id],
    )


class CrossSquadRequest(Base, TimestampMixin):
    """Pedido de mudanca de uma squad em territorio de outra squad."""

    __tablename__ = "cross_squad_requests"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    source_client_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), index=True
    )
    source_squad_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("squads.id", ondelete="CASCADE")
    )
    target_client_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), index=True
    )
    target_squad_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("squads.id", ondelete="CASCADE")
    )
    requesting_task_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE")
    )

    need_description: Mapped[str] = mapped_column(String(2048))
    proposed_contract: Mapped[dict | None] = mapped_column(JSONB)

    status: Mapped[str] = mapped_column(String(32), default="pending")
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

"""StackProfile — catalogo de stacks que a plataforma conhece.

Cada stack tem um base_prompt_template (Claude knowledge sobre a stack)
que e usado por propose_skill_from_stack() pra gerar skills dinamicamente
quando o OA detecta a stack no repo do cliente.

Stacks com RAG vazia ainda podem rodar — agente usa knowledge embutido
do Claude + base_prompt_template. Conforme `stack_patterns:{slug}` for
povoada (vetores 1/2/3 da feature de Knowledge of Stacks), qualidade
melhora.
"""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from dev_autonomo.db.base import Base
from dev_autonomo.db.mixins import TimestampMixin

if TYPE_CHECKING:
    from dev_autonomo.db.models.skill import SkillTemplate


class StackProfile(Base, TimestampMixin):
    """Stack reconhecida pela plataforma (ex: python-fastapi, java-hybris)."""

    __tablename__ = "stack_profiles"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1024))

    # System prompt base que vira a "fundacao" dos skill_templates gerados
    # dinamicamente pra essa stack. Pode usar variaveis Jinja2:
    #   {{ stack_version }}, {{ build_command }}, {{ framework_secondary }}, etc.
    # Caller passa template_variables ao renderizar.
    base_prompt_template: Mapped[str] = mapped_column(Text, nullable=False)

    # Tools que skills dessa stack costumam habilitar por default
    # (override possivel no skill_template gerado).
    default_tools: Mapped[list] = mapped_column(JSONB, default=list)

    # Modelo Claude default pra agentes dessa stack (ex: claude-sonnet-4-6
    # pra dev, claude-opus-4-7 pra architect). Skill gerado pode trocar.
    default_model_alias: Mapped[str] = mapped_column(String(64), nullable=False)

    # Sementes de convencoes/decisoes conhecidas dessa stack — usado pelo
    # propose_skill_from_stack pra injetar contexto adicional.
    # Schema flexivel: {"build_systems": [...], "test_frameworks": [...],
    #                   "lint_tools": [...], "common_pitfalls": [...]}
    conventions_seed: Mapped[dict] = mapped_column(JSONB, default=dict)

    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Skills que foram geradas a partir desse profile (rastreabilidade).
    spawned_skills: Mapped[list["SkillTemplate"]] = relationship(
        back_populates="parent_stack_profile",
        foreign_keys="SkillTemplate.parent_stack_profile_id",
    )

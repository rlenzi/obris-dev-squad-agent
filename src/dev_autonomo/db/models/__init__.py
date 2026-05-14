"""Registra todos os models para Alembic descobrir o metadata."""

from dev_autonomo.db.models.agent import AgentInstance, AgentMessage
from dev_autonomo.db.models.audit import ToolAuthorizationAttempt
from dev_autonomo.db.models.core import (
    Client,
    ClientBillingPlan,
    ClientMembership,
    User,
)
from dev_autonomo.db.models.cost import BillingPeriod, ExternalApiCall
from dev_autonomo.db.models.knowledge import (
    KnowledgeIndexingJob,
    OnboardingRun,
    PlaybookEntry,
)
from dev_autonomo.db.models.secret import EncryptedSecret
from dev_autonomo.db.models.skill import SkillTemplate
from dev_autonomo.db.models.squad import Manifest, Squad
from dev_autonomo.db.models.squad_memory_store import SquadMemoryStore
from dev_autonomo.db.models.task import CrossSquadRequest, Task

__all__ = [
    "AgentInstance",
    "AgentMessage",
    "BillingPeriod",
    "Client",
    "ClientBillingPlan",
    "ClientMembership",
    "CrossSquadRequest",
    "EncryptedSecret",
    "ExternalApiCall",
    "KnowledgeIndexingJob",
    "Manifest",
    "OnboardingRun",
    "PlaybookEntry",
    "SkillTemplate",
    "Squad",
    "SquadMemoryStore",
    "Task",
    "ToolAuthorizationAttempt",
    "User",
]

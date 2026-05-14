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
from dev_autonomo.db.models.dream_job import DreamJob
from dev_autonomo.db.models.knowledge import (
    KnowledgeIndexingJob,
    OnboardingRun,
    PlaybookEntry,
)
from dev_autonomo.db.models.secret import EncryptedSecret
from dev_autonomo.db.models.skill import SkillTemplate
from dev_autonomo.db.models.rag_audit_log import RagAuditLog
from dev_autonomo.db.models.rag_source import RagSource
from dev_autonomo.db.models.squad import Manifest, Squad
from dev_autonomo.db.models.squad_memory_store import SquadMemoryStore
from dev_autonomo.db.models.stack import Stack
from dev_autonomo.db.models.stack_profile import StackProfile
from dev_autonomo.db.models.task import CrossSquadRequest, Task

__all__ = [
    "AgentInstance",
    "AgentMessage",
    "BillingPeriod",
    "Client",
    "ClientBillingPlan",
    "ClientMembership",
    "CrossSquadRequest",
    "DreamJob",
    "EncryptedSecret",
    "ExternalApiCall",
    "KnowledgeIndexingJob",
    "Manifest",
    "OnboardingRun",
    "PlaybookEntry",
    "RagAuditLog",
    "RagSource",
    "SkillTemplate",
    "Squad",
    "SquadMemoryStore",
    "Stack",
    "StackProfile",
    "Task",
    "ToolAuthorizationAttempt",
    "User",
]

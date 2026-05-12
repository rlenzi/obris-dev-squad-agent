"""Enums compartilhados do dominio."""

from enum import StrEnum


class AgentTier(StrEnum):
    BA = "ba"
    ARCHITECT = "architect"
    DEV = "dev"
    ONBOARDING_ANALYST = "onboarding_analyst"


class SquadStatus(StrEnum):
    PROVISIONING = "provisioning"
    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"


class AgentInstanceStatus(StrEnum):
    IDLE = "idle"
    BUSY = "busy"
    PAUSED = "paused"
    DISABLED = "disabled"


class TaskStage(StrEnum):
    DEMAND_RECEIVED = "demand_received"
    BA_REFINING = "ba_refining"
    BA_SPEC_AWAITING_APPROVAL = "ba_spec_awaiting_approval"
    ARCHITECT_PLANNING = "architect_planning"
    PLAN_AWAITING_APPROVAL = "plan_awaiting_approval"
    DEV_EXECUTING = "dev_executing"
    PR_OPENED = "pr_opened"
    HUMAN_REVIEW = "human_review"
    MERGED = "merged"
    CANCELLED = "cancelled"
    FAILED = "failed"


class TaskStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    DONE = "done"
    CANCELLED = "cancelled"
    FAILED = "failed"


class UserRole(StrEnum):
    SYSTEM_ADMIN = "system_admin"
    CLIENT_ADMIN = "client_admin"
    CLIENT_REVIEWER = "client_reviewer"
    CLIENT_VIEWER = "client_viewer"


class SecretKind(StrEnum):
    GITHUB_TOKEN = "github_token"
    GITLAB_TOKEN = "gitlab_token"
    JIRA_TOKEN = "jira_token"
    GENERIC = "generic"


class BillingPlanKind(StrEnum):
    FIXED = "fixed"
    PAY_PER_USE = "pay_per_use"
    HYBRID = "hybrid"

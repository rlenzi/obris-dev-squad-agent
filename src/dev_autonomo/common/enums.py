"""Enums compartilhados do dominio."""

from enum import StrEnum


class AgentTier(StrEnum):
    BA = "ba"
    ARCHITECT = "architect"
    DEV = "dev"
    ONBOARDING_ANALYST = "onboarding_analyst"
    REVIEWER = "reviewer"


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


class ApiProvider(StrEnum):
    """Provider externo cuja chamada gera custo a ser rastreado."""
    ANTHROPIC = "anthropic"
    VOYAGE = "voyage"
    OPENAI = "openai"
    GITHUB = "github"
    JIRA = "jira"
    OTHER = "other"


class ApiCallKind(StrEnum):
    """Tipo de chamada externa (afeta calculo de custo)."""
    CHAT = "chat"
    EMBEDDING = "embedding"
    TOOL = "tool"
    WEBHOOK = "webhook"
    OTHER = "other"
    SKILL_PROPOSAL = "skill_proposal"  # propose_skill_from_stack (Bloco D)


class OutcomeStatus(StrEnum):
    """Status de uma rubric/outcome associada a uma task.

    - PENDING: outcome definido mas grader ainda nao avaliou.
    - SATISFIED: grader retornou result=satisfied.
    - FAILED: grader retornou result=failed apos max_iterations.
    - SKIPPED: task rodou sem outcome definido (legado ou opt-out).
    """
    PENDING = "pending"
    SATISFIED = "satisfied"
    FAILED = "failed"
    SKIPPED = "skipped"


class MemoryStoreKind(StrEnum):
    """Tipo de memory_store associado a uma squad.

    Sao colecoes separadas com proposito proprio. Squad pode ter varios.
    """
    INSIGHTS = "insights"            # consolidacao via Dreaming
    PLAYBOOK = "playbook"            # convencoes/padroes aprendidos
    CONVENTIONS = "conventions"      # decisoes explicitas registradas
    ONBOARDING = "onboarding"        # outputs do OA durante setup
    STACK_PATTERNS = "stack_patterns"  # padroes da stack (cross-tenant ou privado)


class RagSourceKind(StrEnum):
    """Forma de ingest da fonte na RAG."""
    FILE_UPLOAD = "file_upload"    # PDF/MD/TXT/DOCX subido via painel
    URL_FETCH = "url_fetch"        # backend faz fetch da URL e extrai texto
    PASTED_TEXT = "pasted_text"    # texto colado direto no painel
    FEEDBACK_LOOP = "feedback_loop"  # extracao automatica de PRs mergeados
    DREAMING = "dreaming"          # output de consolidacao via Dreaming


class RagSourceScope(StrEnum):
    """Quem pode ler chunks dessa fonte."""
    CROSS_TENANT = "cross_tenant"      # qualquer cliente daquela stack
    CLIENT_PRIVATE = "client_private"  # apenas a squad daquele client_id


class RagSourceLicense(StrEnum):
    """Direitos sobre o conteudo da fonte."""
    REDISTRIBUTABLE = "redistributable"  # publico ou licenca clara pra redistribuir
    PARTNER_ONLY = "partner_only"        # acesso de parceiro, nao redistribuir
    CLIENT_INTERNAL = "client_internal"  # interno do cliente, jamais cross-tenant
    INTERNAL_DERIVED = "internal_derived"  # conteudo derivado/anonimizado (feedback loop)
    UNKNOWN = "unknown"


class RagSourceQuality(StrEnum):
    """Indicador de confiabilidade da fonte (afeta rerank boost)."""
    OFFICIAL = "official"              # doc oficial do fornecedor
    ORBIS_CURATED = "orbis_curated"    # experiencia da Orbis (admin Rubens)
    PARTNER = "partner"                # parceiro/terceiro confiavel
    FIELD_PROVEN = "field_proven"      # extraido de PR mergeado (feedback loop)
    COMMUNITY = "community"            # blog/stackoverflow/comunidade
    INTERNAL = "internal"              # runbook interno do cliente


class RagSourceStatus(StrEnum):
    """Estado do pipeline de ingest da fonte."""
    PENDING = "pending"          # criada, ainda nao processada
    EXTRACTING = "extracting"    # extraindo texto (PDF/URL)
    EMBEDDING = "embedding"      # embeddando chunks via Voyage
    INDEXED = "indexed"          # OK, consultavel
    FAILED = "failed"            # falhou em alguma etapa (ver error_message)


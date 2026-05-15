import axios, { AxiosError, type InternalAxiosRequestConfig } from 'axios';

export const API_BASE_URL =
  import.meta.env.VITE_API_URL ?? 'http://127.0.0.1:9000';

const TOKEN_KEY = 'devauto.admin.token';
const CLIENT_CTX_KEY = 'devauto.admin.client_id';

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}
export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}
export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(CLIENT_CTX_KEY);
}

export function getClientContext(): string | null {
  return localStorage.getItem(CLIENT_CTX_KEY);
}
export function setClientContext(clientId: string): void {
  localStorage.setItem(CLIENT_CTX_KEY, clientId);
}

export const api = axios.create({
  baseURL: API_BASE_URL,
  headers: { 'Content-Type': 'application/json' },
});

api.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = getToken();
  if (token) {
    config.headers.set('Authorization', `Bearer ${token}`);
  }
  const clientCtx = getClientContext();
  if (clientCtx) {
    config.headers.set('X-Client-Id', clientCtx);
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    if (error.response?.status === 401) {
      clearToken();
      if (window.location.pathname !== '/login') {
        window.location.href = '/login';
      }
    }
    return Promise.reject(error);
  },
);

// ---- Types ----

export interface User {
  id: string;
  email: string;
  full_name: string;
  is_system_admin: boolean;
  active: boolean;
  created_at: string;
  last_login_at: string | null;
}

export interface Membership {
  client_id: string;
  client_slug: string;
  client_name: string;
  role: string;
}

export interface MeResponse {
  user: User;
  memberships: Membership[];
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in_seconds: number;
}

export interface Client {
  id: string;
  slug: string;
  name: string;
  status: string;
  jira_workspace_url: string | null;
  jira_email: string | null;
  created_at: string;
  updated_at: string;
  archived_at: string | null;
}

export interface ClientCreate {
  slug: string;
  name: string;
  jira_workspace_url?: string;
  jira_email?: string;
}

export interface ClientUpdate {
  name?: string;
  status?: string;
  jira_workspace_url?: string | null;
  jira_email?: string | null;
}

export interface BillingPlan {
  client_id: string;
  plan_kind: string;
  base_fee_monthly_brl: string;
  included_quota_tokens: number;
  included_quota_tasks: number;
  overage_markup_pct: string;
  infra_overhead_pct: string;
  fixed_overhead_brl_per_task: string;
  usd_to_brl_rate: string;
  starts_at: string;
  ends_at: string | null;
}

export interface BillingPlanUpdate {
  plan_kind?: string;
  base_fee_monthly_brl?: number | string;
  included_quota_tokens?: number;
  included_quota_tasks?: number;
  overage_markup_pct?: number | string;
  infra_overhead_pct?: number | string;
  fixed_overhead_brl_per_task?: number | string;
  usd_to_brl_rate?: number | string;
}

export interface CostBreakdown {
  direct_cost_usd: string;
  direct_cost_brl: string;
  infra_overhead_brl: string;
  fixed_overhead_brl: string;
  full_cost_brl: string;
  num_tasks: number;
  num_calls: number;
  total_input_tokens: number;
  total_output_tokens: number;
}

export interface CostPeriod {
  client_id: string;
  period_start: string;
  period_end: string;
  breakdown: CostBreakdown;
}

export interface CostByClientItem {
  client_id: string;
  client_slug: string;
  client_name: string;
  breakdown: CostBreakdown;
}

// ---- API functions ----

export async function login(email: string, password: string) {
  const { data } = await api.post<TokenResponse>('/auth/login', { email, password });
  return data;
}

export async function fetchMe() {
  const { data } = await api.get<MeResponse>('/me');
  return data;
}

// Clients
export async function fetchClients() {
  const { data } = await api.get<Client[]>('/admin/clients');
  return data;
}
export async function fetchClient(id: string) {
  const { data } = await api.get<Client>(`/admin/clients/${id}`);
  return data;
}
export async function createClient(payload: ClientCreate) {
  const { data } = await api.post<Client>('/admin/clients', payload);
  return data;
}
export async function updateClient(id: string, payload: ClientUpdate) {
  const { data } = await api.patch<Client>(`/admin/clients/${id}`, payload);
  return data;
}

// Billing plan
export async function fetchBillingPlan(clientId: string) {
  const { data } = await api.get<BillingPlan>(`/admin/clients/${clientId}/billing-plan`);
  return data;
}
export async function updateBillingPlan(clientId: string, payload: BillingPlanUpdate) {
  const { data } = await api.put<BillingPlan>(`/admin/clients/${clientId}/billing-plan`, payload);
  return data;
}

// ---- Credentials ----

export type CredentialKind = 'github_token' | 'gitlab_token' | 'jira_token' | 'generic';

export interface Credential {
  id: string;
  client_id: string | null;
  kind: CredentialKind;
  name: string;
  last_rotated_at: string | null;
  last_used_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface CredentialCreate {
  kind: CredentialKind;
  name: string;
  value: string;
}

export interface CredentialRotate {
  value: string;
}

// Credentials usam o namespace /client/ (tenant resolvido via JWT).
// O clientId continua aceito na assinatura por compatibilidade mas e ignorado.

export async function fetchCredentials(_clientId: string) {
  const { data } = await api.get<Credential[]>('/client/credentials');
  return data;
}

export async function createCredential(
  _clientId: string,
  payload: CredentialCreate,
) {
  const { data } = await api.post<Credential>('/client/credentials', payload);
  return data;
}

export async function rotateCredential(
  _clientId: string,
  credentialId: string,
  payload: CredentialRotate,
) {
  const { data } = await api.post<Credential>(
    `/client/credentials/${credentialId}/rotate`,
    payload,
  );
  return data;
}

export async function deleteCredential(_clientId: string, credentialId: string) {
  await api.delete(`/client/credentials/${credentialId}`);
}

// ---- Squads / Manifest / Agents / SkillTemplates ----

export type SquadStatus = 'provisioning' | 'active' | 'paused' | 'archived';

export interface Squad {
  id: string;
  client_id: string;
  slug: string;
  name: string;
  description: string | null;
  domain: string | null;
  status: SquadStatus;
  current_manifest_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface SquadCreate {
  slug: string;
  name: string;
  description?: string;
  domain?: string;
}

export interface SquadUpdate {
  name?: string;
  description?: string;
  domain?: string;
  status?: SquadStatus;
}

export interface Manifest {
  id: string;
  squad_id: string;
  client_id: string;
  version: number;
  content: ManifestContent;
  created_by_user_id: string | null;
  created_at: string;
}

export interface ManifestContent {
  owns: {
    repos?: string[];
    modules_in_shared_repos?: string[];
    database?: { schemas?: string[] };
    database_schemas?: string[];
    jira_projects?: string[];
    apis?: { publishes?: string[]; consumes?: string[] };
    events?: { publishes?: string[]; consumes?: string[] };
  };
  humans_embedded?: {
    tech_lead?: string;
    reviewers?: string[];
  };
}

export type AgentTier = 'ba' | 'architect' | 'dev' | 'onboarding_analyst' | 'reviewer';
export type AgentInstanceStatus = 'idle' | 'busy' | 'paused' | 'disabled';

export interface SkillTemplate {
  id: string;
  client_id: string | null;
  slug: string;
  name: string;
  description: string | null;
  version: number;
  tier: AgentTier;
  model_alias: string;
  stack_primary: Record<string, any>;
  stack_secondary: any[];
  system_prompt_ref: string;
  tools_enabled: any[];
  knowledge_partitions: any[];
  active: boolean;
}

export interface AgentInstance {
  id: string;
  client_id: string;
  squad_id: string;
  skill_template_id: string;
  name: string;
  domain_business: string | null;
  status: AgentInstanceStatus;
  config_overrides: Record<string, any>;
  last_active_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface AgentInstanceCreate {
  skill_template_id: string;
  name: string;
  domain_business?: string;
  config_overrides?: Record<string, any>;
}

export async function fetchSquadsForClient(clientId: string) {
  const { data } = await api.get<Squad[]>('/client/squads', {
    headers: { 'X-Client-Id': clientId },
  });
  return data;
}

export async function createSquad(clientId: string, payload: SquadCreate) {
  const { data } = await api.post<Squad>('/client/squads', payload, {
    headers: { 'X-Client-Id': clientId },
  });
  return data;
}

export async function fetchSquad(clientId: string, squadId: string) {
  const { data } = await api.get<Squad>(`/client/squads/${squadId}`, {
    headers: { 'X-Client-Id': clientId },
  });
  return data;
}

export async function updateSquad(clientId: string, squadId: string, payload: SquadUpdate) {
  const { data } = await api.patch<Squad>(`/client/squads/${squadId}`, payload, {
    headers: { 'X-Client-Id': clientId },
  });
  return data;
}

export async function fetchManifest(clientId: string, squadId: string) {
  const { data } = await api.get<Manifest>(`/client/squads/${squadId}/manifest`, {
    headers: { 'X-Client-Id': clientId },
  });
  return data;
}

export async function updateManifest(
  clientId: string,
  squadId: string,
  content: ManifestContent,
) {
  const { data } = await api.put<Manifest>(
    `/client/squads/${squadId}/manifest`,
    { content },
    { headers: { 'X-Client-Id': clientId } },
  );
  return data;
}

export async function fetchAgents(clientId: string, squadId: string) {
  const { data } = await api.get<AgentInstance[]>(`/client/squads/${squadId}/agents`, {
    headers: { 'X-Client-Id': clientId },
  });
  return data;
}

export async function createAgent(
  clientId: string,
  squadId: string,
  payload: AgentInstanceCreate,
) {
  const { data } = await api.post<AgentInstance>(
    `/client/squads/${squadId}/agents`,
    payload,
    { headers: { 'X-Client-Id': clientId } },
  );
  return data;
}

export async function fetchSkillTemplates() {
  const { data } = await api.get<SkillTemplate[]>('/skill-templates');
  return data;
}

export async function fetchSkillTemplate(id: string) {
  const { data } = await api.get<SkillTemplate>(`/skill-templates/${id}`);
  return data;
}

export interface AgentPromptUpdate {
  system_prompt: string;
  model_alias?: string;
}

export async function updateAgentPrompt(
  clientId: string,
  squadId: string,
  agentId: string,
  payload: AgentPromptUpdate,
) {
  const { data } = await api.patch<AgentInstance>(
    `/client/squads/${squadId}/agents/${agentId}/prompt`,
    payload,
    { headers: { 'X-Client-Id': clientId } },
  );
  return data;
}

export async function deleteAgent(
  clientId: string,
  squadId: string,
  agentId: string,
) {
  await api.delete(`/client/squads/${squadId}/agents/${agentId}`, {
    headers: { 'X-Client-Id': clientId },
  });
}

// ---- Jira integration (S-7) ----

export interface JiraStageMappingEntry {
  stage: string;
  target_status: string;
  message_preview: string;
}

export interface JiraIntegration {
  connected: boolean;
  workspace_url: string | null;
  email: string | null;
  webhook_url: string;
  stage_mapping: JiraStageMappingEntry[];
  supported_events: string[];
}

export async function fetchJiraIntegration(clientId: string) {
  const { data } = await api.get<JiraIntegration>('/client/jira/integration', {
    headers: { 'X-Client-Id': clientId },
  });
  return data;
}

// ---- Squad knowledge search (S-8) ----

export interface RetrievalHit {
  content: string;
  source_id: string | null;
  score: number;
  scope: string;
  source_quality: string;
  license: string;
  source_uri: string | null;
  stack_version: string | null;
  collection_slug: string;
  metadata: Record<string, any>;
}

export interface RetrievalResponse {
  hits: RetrievalHit[];
  total: number;
}

export async function searchSquadKnowledge(
  clientId: string,
  squadId: string,
  query: string,
  top_k: number = 10,
) {
  const { data } = await api.post<RetrievalResponse>(
    `/client/squads/${squadId}/retrieval/search`,
    { query, top_k },
    { headers: { 'X-Client-Id': clientId } },
  );
  return data;
}

// ---- Client members (S-8 Settings) ----

export interface ClientMember {
  id: string;
  email: string;
  full_name: string;
  role: string;
  active: boolean;
  last_login_at: string | null;
  membership_id: string;
  created_at: string;
}

export async function fetchClientMembers(clientId: string) {
  const { data } = await api.get<ClientMember[]>('/client/users', {
    headers: { 'X-Client-Id': clientId },
  });
  return data;
}

// === Agent Runs (LEO-26 / LEO-29) ===

export type RunStatus = 'completed' | 'failed' | 'in_progress';

export type OutcomeStatus = 'pending' | 'satisfied' | 'failed' | 'skipped';

export interface AgentRunItem {
  task_id: string;
  jira_issue_key: string | null;
  title: string | null;
  tool_calls_count: number;
  total_cost_usd: string; // Decimal serializado como string
  started_at: string;
  ended_at: string | null;
  status: RunStatus;
  outcome_status: OutcomeStatus;
  outcome_iterations: number;
}

export interface AgentRunsPage {
  items: AgentRunItem[];
  total: number;
  offset: number;
  limit: number;
}

export async function fetchAgentRuns(
  clientId: string,
  agentId: string,
  opts: { offset?: number; limit?: number } = {},
): Promise<AgentRunsPage> {
  const params = new URLSearchParams();
  if (opts.offset !== undefined) params.set('offset', String(opts.offset));
  if (opts.limit !== undefined) params.set('limit', String(opts.limit));
  const qs = params.toString();
  const url = `/clients/${clientId}/agents/${agentId}/runs${qs ? '?' + qs : ''}`;
  const { data } = await api.get<AgentRunsPage>(url, {
    headers: { 'X-Client-Id': clientId },
  });
  return data;
}

export interface AgentRunTriggerRequest {
  jira_issue_key: string;
}

export interface AgentRunTriggerResponse {
  task_id: string;
  jira_issue_key: string;
  agent_id: string;
  tier: string;
  pid: number;
  log_path: string;
  status: 'started';
}

export async function triggerAgentRun(
  clientId: string,
  agentId: string,
  payload: AgentRunTriggerRequest,
): Promise<AgentRunTriggerResponse> {
  const { data } = await api.post<AgentRunTriggerResponse>(
    `/clients/${clientId}/agents/${agentId}/runs`,
    payload,
    { headers: { 'X-Client-Id': clientId } },
  );
  return data;
}

// === Agent Run Detail (drill-down) ===

export interface ExternalCallItem {
  id: string;
  occurred_at: string;
  provider: string; // ANTHROPIC | VOYAGE
  kind: string; // CHAT | EMBED
  model: string | null;
  input_tokens: number;
  output_tokens: number;
  cache_creation_input_tokens: number;
  cache_read_input_tokens: number;
  cost_usd: string;
  latency_ms: number | null;
  request_id: string | null;
  error: string | null;
}

export interface AgentRunDetail {
  task_id: string;
  agent_instance_id: string;
  title: string | null;
  jira_issue_key: string | null;
  jira_issue_url: string | null;
  pr_search_url: string | null;
  status: RunStatus;
  started_at: string;
  ended_at: string | null;
  duration_ms: number | null;
  tool_calls_count: number;
  total_cost_usd: string;
  total_input_tokens: number;
  total_output_tokens: number;
  total_cache_creation_tokens: number;
  total_cache_read_tokens: number;
  error_count: number;
  /** Sessão Anthropic Managed Agents (T7). */
  anthropic_session_id: string | null;
  outcome_status: OutcomeStatus;
  outcome_iterations: number;
  outcome_rubric_ref: string | null;
  calls: ExternalCallItem[];
  calls_total: number;
  calls_offset: number;
  calls_limit: number;
}

// === Cost (admin) ===

export interface CostBreakdownResponse {
  direct_cost_usd: string;
  direct_cost_brl: string;
  infra_overhead_brl: string;
  fixed_overhead_brl: string;
  full_cost_brl: string;
  num_tasks: number;
  num_calls: number;
  total_input_tokens: number;
  total_output_tokens: number;
}

export interface CostPeriodResponse {
  client_id: string;
  period_start: string; // ISO date YYYY-MM-DD
  period_end: string;
  breakdown: CostBreakdownResponse;
}

export interface CostByClientItem {
  client_id: string;
  client_slug: string;
  client_name: string;
  breakdown: CostBreakdownResponse;
}

export async function fetchCostByClient(
  opts: { period_start?: string; period_end?: string; limit?: number } = {},
): Promise<CostByClientItem[]> {
  const params = new URLSearchParams();
  if (opts.period_start) params.set('period_start', opts.period_start);
  if (opts.period_end) params.set('period_end', opts.period_end);
  if (opts.limit !== undefined) params.set('limit', String(opts.limit));
  const qs = params.toString();
  const { data } = await api.get<CostByClientItem[]>(
    `/admin/cost/by-client${qs ? '?' + qs : ''}`,
  );
  return data;
}

/**
 * Custo do proprio tenant (cliente logado). Backend resolve via JWT.
 * O clientId fica na assinatura por compat com call sites antigos —
 * nao e enviado.
 */
export async function fetchClientCost(
  _clientId: string,
  opts: { period_start?: string; period_end?: string } = {},
): Promise<CostPeriodResponse> {
  const params = new URLSearchParams();
  if (opts.period_start) params.set('period_start', opts.period_start);
  if (opts.period_end) params.set('period_end', opts.period_end);
  const qs = params.toString();
  const { data } = await api.get<CostPeriodResponse>(
    `/client/cost/summary${qs ? '?' + qs : ''}`,
  );
  return data;
}

export async function fetchAgentRunDetail(
  clientId: string,
  agentId: string,
  taskId: string,
  opts: { offset?: number; limit?: number } = {},
): Promise<AgentRunDetail> {
  const params = new URLSearchParams();
  if (opts.offset !== undefined) params.set('offset', String(opts.offset));
  if (opts.limit !== undefined) params.set('limit', String(opts.limit));
  const qs = params.toString();
  const { data } = await api.get<AgentRunDetail>(
    `/clients/${clientId}/agents/${agentId}/runs/${taskId}${qs ? '?' + qs : ''}`,
    { headers: { 'X-Client-Id': clientId } },
  );
  return data;
}


// =============================================================================
// Squad Knowledge (Bloco C — RAG sources privadas da squad)
// =============================================================================

export type RagSourceKindClient =
  | 'file_upload' | 'pasted_text' | 'feedback_loop' | 'dreaming' | 'url_fetch';
export type RagSourceQualityClient =
  | 'official' | 'orbis_curated' | 'partner' | 'field_proven' | 'community' | 'internal';
export type RagSourceStatusClient =
  | 'pending' | 'extracting' | 'embedding' | 'indexed' | 'failed';

export interface SquadRagSource {
  id: string;
  collection_slug: string;
  kind: RagSourceKindClient;
  source_uri: string | null;
  source_hash: string;
  source_quality: RagSourceQualityClient;
  stack_version: string | null;
  indexed_chunks: number;
  status: RagSourceStatusClient;
  error_message: string | null;
  tags: string[];
  created_at: string;
}

export interface SquadRagIngestResponse {
  rag_source_id: string;
  status: RagSourceStatusClient;
  indexed_chunks: number;
  source_hash: string;
  error_message: string | null;
  deduplicated: boolean;
}

export async function listSquadKnowledgeSources(
  clientId: string,
  squadId: string,
): Promise<SquadRagSource[]> {
  const { data } = await api.get<SquadRagSource[]>(
    `/client/squads/${squadId}/knowledge/sources`,
    { headers: { 'X-Client-Id': clientId } },
  );
  return data;
}

export async function ingestSquadText(
  clientId: string,
  squadId: string,
  payload: { text: string; source_quality: RagSourceQualityClient; stack_version?: string; tags?: string },
): Promise<SquadRagIngestResponse> {
  const form = new FormData();
  form.append('text', payload.text);
  form.append('source_quality', payload.source_quality);
  if (payload.stack_version) form.append('stack_version', payload.stack_version);
  form.append('tags', payload.tags ?? '');
  const { data } = await api.post<SquadRagIngestResponse>(
    `/client/squads/${squadId}/knowledge/sources/text`, form,
    { headers: { 'X-Client-Id': clientId } },
  );
  return data;
}

export async function ingestSquadFile(
  clientId: string,
  squadId: string,
  payload: { file: File; source_quality: RagSourceQualityClient; stack_version?: string; tags?: string },
): Promise<SquadRagIngestResponse> {
  const form = new FormData();
  form.append('file', payload.file);
  form.append('source_quality', payload.source_quality);
  if (payload.stack_version) form.append('stack_version', payload.stack_version);
  form.append('tags', payload.tags ?? '');
  const { data } = await api.post<SquadRagIngestResponse>(
    `/client/squads/${squadId}/knowledge/sources/file`, form,
    { headers: { 'X-Client-Id': clientId } },
  );
  return data;
}

export async function deleteSquadKnowledgeSource(
  clientId: string,
  squadId: string,
  sourceId: string,
): Promise<void> {
  await api.delete(`/client/squads/${squadId}/knowledge/sources/${sourceId}`, {
    headers: { 'X-Client-Id': clientId },
  });
}

// =============================================================================
// Onboarding analysis + skill proposer (Bloco E)
// =============================================================================

// OnboardingStatusResponse v2 (PR-3 do redesign).
// Backend retorna estado granular da state machine do analyzer v2.
export type OnboardingStatus =
  | 'not_started' | 'in_progress' | 'completed' | 'failed' | 'cancelled';

// Nome curto da etapa atual. Bate com STEP_LABELS do backend.
export type OnboardingStep =
  | 'cloning' | 'scanning' | 'oa_scanning'
  | 'indexing' | 'finalizing' | 'grading'
  | 'completed' | 'failed' | 'cancelled';

export interface OnboardingScanProgress {
  // Contadores granulares — schema flexivel, depende da etapa atual.
  started_at?: string;
  total_files?: number;
  files_excluded?: number;
  files_processed?: number;
  files_indexed?: number;
  chunks_total?: number;
  chunks_indexed?: number;
  chunks_estimated?: number;
  clone_size_bytes?: number;
  embedding_cost_usd?: string;
  oa_iterations?: number;
  stacks_detected?: number;
  agents_recommended?: number;
  completed_at?: string;
  failed_at?: string;
  failure_reason?: string;
  cancelled_at?: string;
  // Aceita campos extras desconhecidos
  [key: string]: unknown;
}

export interface OnboardingStatusResponse {
  task_id: string | null;
  status: OnboardingStatus;
  current_step: OnboardingStep | string | null;
  step_label: string | null;
  scan_progress: OnboardingScanProgress;
  started_at: string | null;
  manifest_ready_at: string | null;
  closed_at: string | null;
  error_message: string | null;
}

export interface CancelAnalysisResponse {
  task_id: string;
  previous_status: string;
  status: 'cancelled' | 'already_finished';
}

export async function cancelOnboardingAnalysis(
  clientId: string,
  squadId: string,
): Promise<CancelAnalysisResponse> {
  const { data } = await api.post<CancelAnalysisResponse>(
    `/client/squads/${squadId}/cancel-onboarding-analysis`,
    {},
    { headers: { 'X-Client-Id': clientId } },
  );
  return data;
}

export interface SkillTemplateDraft {
  slug: string;
  name: string;
  description: string;
  tier: 'ba' | 'architect' | 'dev' | 'onboarding_analyst' | 'reviewer';
  model_alias: string;
  system_prompt: string;
  tools_enabled: any[];
  stack_primary: Record<string, any>;
  stack_secondary: any[];
  knowledge_partitions: any[];
  template_variables: Record<string, any>;
  parent_stack_profile_id: string;
}

export interface ProposeSkillsResponse {
  drafts: SkillTemplateDraft[];
  api_call_cost_usd: string;
  input_tokens: number;
  output_tokens: number;
}

export interface ManifestRepo {
  name: string;
  primary_language: string;
  framework: string;
  stack_secondary?: string[];
  package_manager?: string;
  test_runner?: string | null;
  lint?: string | null;
  build_command?: string | null;
  test_command?: string | null;
  lint_command?: string | null;
  entry_points?: string[];
  key_directories?: string[];
}

export interface RecommendedAgent {
  role: string;
  skill_template_slug: string;
  rationale?: string;
}

export interface OnboardingManifest {
  schema_version?: string;
  detected_at?: string;
  repos: ManifestRepo[];
  recommended_agents?: RecommendedAgent[];
  human_questions?: string[];
}

// ---- GitHub repo status (PR-1 do redesign) ----

export interface RepoStatusResponse {
  url: string;
  valid: boolean;
  owner: string | null;
  repo: string | null;
  is_public: boolean | null;
  accessible: boolean | null;
  default_branch: string | null;
  suggested_slug: string | null;
  error: string | null;
}

export async function getGithubRepoStatus(
  clientId: string,
  url: string,
  token?: string,
): Promise<RepoStatusResponse> {
  const headers: Record<string, string> = { 'X-Client-Id': clientId };
  if (token) {
    headers['X-GitHub-Token'] = `Bearer ${token}`;
  }
  const { data } = await api.get<RepoStatusResponse>(
    '/client/github/repo-status',
    { params: { url }, headers },
  );
  return data;
}


export async function runOnboardingAnalysis(
  clientId: string,
  squadId: string,
  repoUrls: string[],
): Promise<{ task_id: string; status: 'started' | 'already_running' }> {
  const { data } = await api.post(
    `/client/squads/${squadId}/run-onboarding-analysis`,
    { repo_urls: repoUrls },
    { headers: { 'X-Client-Id': clientId } },
  );
  return data;
}

export async function getOnboardingStatus(
  clientId: string,
  squadId: string,
): Promise<OnboardingStatusResponse> {
  const { data } = await api.get<OnboardingStatusResponse>(
    `/client/squads/${squadId}/onboarding-status`,
    { headers: { 'X-Client-Id': clientId } },
  );
  return data;
}

export async function getOnboardingManifest(
  clientId: string,
  squadId: string,
): Promise<OnboardingManifest> {
  const { data } = await api.get(
    `/client/squads/${squadId}/onboarding-manifest`,
    { headers: { 'X-Client-Id': clientId } },
  );
  return data.raw as OnboardingManifest;
}

// ---- Onboarding Result Manifest v2 (PR-3 do redesign) ----
//
// O backend gravar o manifest com schema novo no memory_store ONBOARDING.
// Este type espelha o JSON do OA scan v2. Lido pela Tela 3 do redesign.

export interface AnalysisStackConventions {
  observed_patterns: Record<string, string>;
  recommended_for_agents: Record<string, string>;
}

export interface AnalysisStack {
  slug: string;
  name: string;
  paths: string[];
  framework: string | null;
  framework_version: string | null;
  conventions: AnalysisStackConventions;
}

export interface AnalysisAntiPattern {
  issue: string;
  severity: 'low' | 'medium' | 'high';
  occurrences: string[];
  recommendation: string;
}

export interface AnalysisAgentRec {
  tier: 'ba' | 'architect' | 'dev' | 'reviewer';
  stack_slug: string | null;
  rationale: string;
}

export interface OnboardingResultManifest {
  summary: string;
  stacks: AnalysisStack[];
  jira_projects: string[];
  anti_patterns_detected: AnalysisAntiPattern[];
  recommended_agents: AnalysisAgentRec[];
  tool_calls_summary?: Record<string, unknown>;
  clone_metadata?: Record<string, unknown>;
  saved_at?: string;
}

export async function getOnboardingResult(
  clientId: string,
  squadId: string,
): Promise<OnboardingResultManifest> {
  const { data } = await api.get(
    `/client/squads/${squadId}/onboarding-manifest`,
    { headers: { 'X-Client-Id': clientId } },
  );
  return data.raw as OnboardingResultManifest;
}

export async function proposeSkills(
  clientId: string,
  squadId: string,
  manifest: OnboardingManifest,
  stackSlugs: string[],
): Promise<ProposeSkillsResponse> {
  const { data } = await api.post<ProposeSkillsResponse>(
    `/client/squads/${squadId}/propose-skills`,
    { manifest, stack_slugs: stackSlugs },
    { headers: { 'X-Client-Id': clientId } },
  );
  return data;
}

// ---- Client Tasks (S-2 do redesign) ----

export type TaskStatusType =
  | 'pending' | 'in_progress' | 'blocked' | 'done' | 'cancelled' | 'failed';

export interface TaskListItem {
  id: string;
  squad_id: string;
  squad_slug: string | null;
  jira_issue_key: string | null;
  title: string;
  status: TaskStatusType;
  current_step: string | null;
  step_label: string | null;
  assigned_agent_id: string | null;
  started_at: string | null;
  closed_at: string | null;
  created_at: string;
  pr_url: string | null;
  cost_usd: number;
  outcome_status: string;
}

export interface TasksListResponse {
  items: TaskListItem[];
  total: number;
  offset: number;
  limit: number;
}

export interface TasksListFilters {
  squad_id?: string;
  agent_id?: string;
  status?: TaskStatusType;
  since?: string;
  until?: string;
  limit?: number;
  offset?: number;
}

export async function fetchTasks(
  clientId: string, filters: TasksListFilters = {},
): Promise<TasksListResponse> {
  const params: Record<string, string | number> = {};
  if (filters.squad_id) params.squad_id = filters.squad_id;
  if (filters.agent_id) params.agent_id = filters.agent_id;
  if (filters.status) params.status = filters.status;
  if (filters.since) params.since = filters.since;
  if (filters.until) params.until = filters.until;
  params.limit = filters.limit ?? 50;
  params.offset = filters.offset ?? 0;

  const { data } = await api.get<TasksListResponse>(
    '/client/tasks',
    { params, headers: { 'X-Client-Id': clientId } },
  );
  return data;
}

export interface TaskTimelineEvent {
  kind: string;
  timestamp: string;
  label: string;
  detail: Record<string, unknown>;
}

export interface TaskDetailResponse {
  id: string;
  squad_id: string;
  squad_slug: string | null;
  jira_workspace_url: string;
  jira_issue_key: string | null;
  title: string;
  status: TaskStatusType;
  current_step: string | null;
  step_label: string | null;
  scan_progress: Record<string, unknown>;
  assigned_agent_id: string | null;
  pr_url: string | null;
  anthropic_session_id: string | null;
  started_at: string | null;
  closed_at: string | null;
  created_at: string;
  updated_at: string;
  outcome_status: string;
  outcome_iterations: number;
  cost_usd: number;
  api_calls_count: number;
  timeline: TaskTimelineEvent[];
}

export async function fetchTaskDetail(
  clientId: string, taskId: string,
): Promise<TaskDetailResponse> {
  const { data } = await api.get<TaskDetailResponse>(
    `/client/tasks/${taskId}`,
    { headers: { 'X-Client-Id': clientId } },
  );
  return data;
}

export interface DashboardSummary {
  in_progress_count: number;
  completed_this_month: number;
  completed_last_month: number;
  cost_this_month: number;
  cost_last_month: number;
  active_agents: number;
  failed_recent: number;
  recent_activity: TaskListItem[];
}

export async function fetchDashboardSummary(
  clientId: string,
): Promise<DashboardSummary> {
  const { data } = await api.get<DashboardSummary>(
    '/client/tasks/dashboard-summary',
    { headers: { 'X-Client-Id': clientId } },
  );
  return data;
}


// ---- Cost extras (S-4 do redesign) ----

export interface TopTaskCost {
  task_id: string;
  jira_issue_key: string | null;
  title: string;
  squad_id: string;
  cost_usd: number;
  api_calls_count: number;
}

export async function fetchTopTasksByCost(
  clientId: string,
  params: { period_start?: string; period_end?: string; limit?: number } = {},
): Promise<{ items: TopTaskCost[] }> {
  const { data } = await api.get<{ items: TopTaskCost[] }>(
    '/client/cost/top-tasks',
    { params, headers: { 'X-Client-Id': clientId } },
  );
  return data;
}

export interface DailyCostPoint {
  date: string;
  cost_usd: number;
}

export async function fetchDailyCostSeries(
  clientId: string,
  params: { period_start?: string; period_end?: string } = {},
): Promise<{ items: DailyCostPoint[] }> {
  const { data } = await api.get<{ items: DailyCostPoint[] }>(
    '/client/cost/daily-series',
    { params, headers: { 'X-Client-Id': clientId } },
  );
  return data;
}


export interface FinalizeSkillEntry {
  catalog_skill_slug?: string | null;
  draft_to_materialize?: SkillTemplateDraft | null;
  instance_name?: string;
  domain_business?: string;
}

export async function finalizeSetup(
  clientId: string,
  squadId: string,
  entries: FinalizeSkillEntry[],
): Promise<{ agent_instance_ids: string[]; created_skill_ids: string[] }> {
  const { data } = await api.post(
    `/client/squads/${squadId}/finalize-setup`,
    { skills: entries },
    { headers: { 'X-Client-Id': clientId } },
  );
  return data;
}

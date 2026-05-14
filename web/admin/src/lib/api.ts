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

export async function fetchCredentials(clientId: string) {
  const { data } = await api.get<Credential[]>(
    `/admin/clients/${clientId}/credentials`,
  );
  return data;
}

export async function createCredential(clientId: string, payload: CredentialCreate) {
  const { data } = await api.post<Credential>(
    `/admin/clients/${clientId}/credentials`,
    payload,
  );
  return data;
}

export async function rotateCredential(clientId: string, credentialId: string, payload: CredentialRotate) {
  const { data } = await api.post<Credential>(
    `/admin/clients/${clientId}/credentials/${credentialId}/rotate`,
    payload,
  );
  return data;
}

export async function deleteCredential(clientId: string, credentialId: string) {
  await api.delete(`/admin/clients/${clientId}/credentials/${credentialId}`);
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

// === Agent Runs (LEO-26 / LEO-29) ===

export type RunStatus = 'completed' | 'failed' | 'in_progress';

export interface AgentRunItem {
  task_id: string;
  jira_issue_key: string | null;
  title: string | null;
  tool_calls_count: number;
  total_cost_usd: string; // Decimal serializado como string
  started_at: string;
  ended_at: string | null;
  status: RunStatus;
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

export async function fetchClientCost(
  clientId: string,
  opts: { period_start?: string; period_end?: string } = {},
): Promise<CostPeriodResponse> {
  const params = new URLSearchParams();
  if (opts.period_start) params.set('period_start', opts.period_start);
  if (opts.period_end) params.set('period_end', opts.period_end);
  const qs = params.toString();
  const { data } = await api.get<CostPeriodResponse>(
    `/admin/clients/${clientId}/cost${qs ? '?' + qs : ''}`,
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


import { useEffect, useState, type FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router-dom';
import {
  ArrowLeft, Bot, Code2, GitBranch, Pencil, Plus, Trash2,
} from 'lucide-react';
import {
  api,
  createAgent,
  deleteAgent,
  fetchAgents,
  fetchClient,
  fetchJiraIntegration,
  fetchManifest,
  fetchSkillTemplate,
  fetchSkillTemplates,
  fetchSquad,
  fetchTasks,
  updateAgentPrompt,
  type AgentInstance,
  type AgentInstanceCreate,
  type ManifestContent,
  type SkillTemplate,
  type Squad,
} from '@/lib/api';
import { useClientId } from '@/lib/use-client-id';
import { formatApiError } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import {
  Card, CardContent, CardDescription, CardHeader, CardTitle,
} from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Dialog, DialogContent, DialogDescription, DialogFooter,
  DialogHeader, DialogTitle, DialogTrigger,
} from '@/components/ui/dialog';


interface StackPublic {
  id: string;
  slug: string;
  name: string;
  paths: string[];
  framework: string | null;
  framework_version: string | null;
  status: string;
  detected_at: string | null;
}


export default function SquadDetailPage() {
  const clientId = useClientId();
  const { squadId } = useParams<{ squadId: string }>();
  const navigate = useNavigate();

  const clientQuery = useQuery({
    queryKey: ['client', clientId],
    queryFn: () => fetchClient(clientId!),
    enabled: Boolean(clientId),
  });
  const squadQuery = useQuery({
    queryKey: ['squad', clientId, squadId],
    queryFn: () => fetchSquad(clientId!, squadId!),
    enabled: Boolean(clientId && squadId),
  });

  if (squadQuery.isLoading || !squadQuery.data) {
    return <div className="text-muted-foreground">Carregando squad…</div>;
  }
  const squad = squadQuery.data;
  const client = clientQuery.data;

  return (
    <div className="space-y-6">
      <Button variant="ghost" size="sm" onClick={() => navigate('/dashboard')}>
        <ArrowLeft className="size-4" />
        Voltar pro painel
      </Button>

      <div>
        <h1 className="text-3xl font-semibold tracking-tight">{squad.name}</h1>
        <div className="mt-1 flex items-center gap-2 text-muted-foreground">
          <span className="font-mono text-sm">{squad.slug}</span>
          <StatusBadge status={squad.status} />
          {squad.domain && (
            <span className="text-xs text-muted-foreground">· {squad.domain}</span>
          )}
          {client && (
            <span className="text-xs text-muted-foreground">· {client.name}</span>
          )}
        </div>
      </div>

      <Tabs defaultValue="overview" className="w-full">
        <TabsList>
          <TabsTrigger value="overview">Visão geral</TabsTrigger>
          <TabsTrigger value="agents">Agentes</TabsTrigger>
          <TabsTrigger value="stacks">Stacks</TabsTrigger>
          <TabsTrigger value="repos">Repos</TabsTrigger>
          <TabsTrigger value="jira">Jira</TabsTrigger>
          <TabsTrigger value="config">Config</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="mt-6">
          <OverviewTab clientId={clientId!} squad={squad} />
        </TabsContent>
        <TabsContent value="agents" className="mt-6">
          <AgentsList clientId={clientId!} squad={squad} />
        </TabsContent>
        <TabsContent value="stacks" className="mt-6">
          <StacksTab clientId={clientId!} squadId={squad.id} />
        </TabsContent>
        <TabsContent value="repos" className="mt-6">
          <ReposTab clientId={clientId!} squadId={squad.id} />
        </TabsContent>
        <TabsContent value="jira" className="mt-6">
          <JiraTab clientId={clientId!} squadId={squad.id} client={client} />
        </TabsContent>
        <TabsContent value="config" className="mt-6">
          <ConfigTab clientId={clientId!} squadId={squad.id} />
        </TabsContent>
      </Tabs>
    </div>
  );
}


// ---- Visão geral ----

function OverviewTab({ clientId, squad }: { clientId: string; squad: Squad }) {
  const agentsQuery = useQuery({
    queryKey: ['agents', clientId, squad.id],
    queryFn: () => fetchAgents(clientId, squad.id),
  });
  const tasksQuery = useQuery({
    queryKey: ['squad-tasks', clientId, squad.id],
    queryFn: () => fetchTasks(clientId, { squad_id: squad.id, limit: 10 }),
  });
  const stacksQuery = useQuery({
    queryKey: ['stacks', clientId, squad.id],
    queryFn: async (): Promise<StackPublic[]> => {
      const { data } = await api.get(`/client/squads/${squad.id}/stacks`, {
        headers: { 'X-Client-Id': clientId },
      });
      return data;
    },
  });

  const agents = agentsQuery.data ?? [];
  const tasks = tasksQuery.data?.items ?? [];
  const inProgress = tasks.filter(t => t.status === 'in_progress');
  const stacks = stacksQuery.data ?? [];

  return (
    <div className="space-y-6">
      <div className="grid gap-4 md:grid-cols-3">
        <KpiCard label="Agentes" value={String(agents.length)} icon={<Bot className="size-4" />} />
        <KpiCard label="Stacks detectadas" value={String(stacks.length)} icon={<Code2 className="size-4" />} />
        <KpiCard label="Tasks recentes" value={String(tasks.length)} icon={<GitBranch className="size-4" />} />
      </div>

      {inProgress.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Em curso ({inProgress.length})</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1.5">
            {inProgress.map(t => (
              <a
                key={t.id}
                href={`/tasks/${t.id}`}
                className="block rounded-md border bg-muted/20 px-3 py-2 text-sm hover:bg-muted/40"
              >
                <span className="font-mono text-xs">{t.jira_issue_key ?? t.id.slice(0, 8)}</span>
                {' · '}
                <span className="text-muted-foreground">{t.title.slice(0, 60)}</span>
              </a>
            ))}
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="text-base">Agentes ({agents.length})</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {agents.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              Nenhum agente provisionado ainda.
            </p>
          ) : (
            agents.map(a => (
              <div key={a.id} className="rounded-md border bg-muted/20 px-3 py-2 text-sm">
                <span className="font-medium">{a.name}</span>
                {a.domain_business && (
                  <span className="ml-2 text-xs text-muted-foreground">
                    · {a.domain_business}
                  </span>
                )}
              </div>
            ))
          )}
        </CardContent>
      </Card>
    </div>
  );
}


function KpiCard({
  label, value, icon,
}: { label: string; value: string; icon: React.ReactNode }) {
  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
          {icon} {label}
        </div>
        <div className="mt-2 text-2xl font-semibold">{value}</div>
      </CardContent>
    </Card>
  );
}


// ---- Stacks tab ----

function StacksTab({ clientId, squadId }: { clientId: string; squadId: string }) {
  const stacksQuery = useQuery({
    queryKey: ['stacks', clientId, squadId],
    queryFn: async (): Promise<StackPublic[]> => {
      const { data } = await api.get(`/client/squads/${squadId}/stacks`, {
        headers: { 'X-Client-Id': clientId },
      });
      return data;
    },
  });

  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">
        Stacks detectadas pelo OA + criadas manualmente pelo cliente.
      </p>
      {stacksQuery.data?.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          Nenhuma stack ainda. Stacks são criadas automaticamente pelo onboarding analyzer.
        </p>
      ) : (
        <div className="grid gap-3">
          {stacksQuery.data?.map(s => (
            <Card key={s.id}>
              <CardContent className="p-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="flex items-center gap-2">
                      <h3 className="text-sm font-semibold">{s.name}</h3>
                      <Badge variant="muted">{s.status}</Badge>
                    </div>
                    <p className="mt-1 text-xs text-muted-foreground">
                      <code>{s.paths.join(' · ')}</code>
                      {s.framework && (
                        <>
                          {' · '}{s.framework}
                          {s.framework_version && ` ${s.framework_version}`}
                        </>
                      )}
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
      <p className="text-xs text-muted-foreground">
        💡 Criar stack manual e editar conventions chegam em S-5/S-6.
      </p>
    </div>
  );
}


// ---- Repos tab ----

function ReposTab({ clientId, squadId }: { clientId: string; squadId: string }) {
  const manifestQuery = useQuery({
    queryKey: ['manifest', clientId, squadId],
    queryFn: () => fetchManifest(clientId, squadId),
  });
  const repos: string[] =
    (manifestQuery.data?.content as ManifestContent | undefined)?.owns?.repos ?? [];

  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">
        Repositórios cobertos por essa squad (derivado do manifest).
      </p>
      {repos.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          Nenhum repo associado ainda.
        </p>
      ) : (
        <div className="space-y-2">
          {repos.map(r => (
            <div key={r} className="rounded-md border bg-muted/20 px-3 py-2 text-sm">
              <code className="text-xs">{r}</code>
            </div>
          ))}
        </div>
      )}
      <p className="text-xs text-muted-foreground">
        💡 Adicionar repositório em modo delta e status de indexação visual chegam em S-5.
      </p>
    </div>
  );
}


// ---- Jira tab (S-7) ----

function JiraTab({
  clientId, squadId, client,
}: {
  clientId: string;
  squadId: string;
  client: { jira_workspace_url?: string | null } | undefined;
}) {
  const manifestQuery = useQuery({
    queryKey: ['manifest', clientId, squadId],
    queryFn: () => fetchManifest(clientId, squadId),
  });
  const integrationQuery = useQuery({
    queryKey: ['jira-integration', clientId],
    queryFn: () => fetchJiraIntegration(clientId),
  });
  const projects: string[] =
    (manifestQuery.data?.content as ManifestContent | undefined)?.owns?.jira_projects ?? [];
  const integration = integrationQuery.data;
  const [webhookCopied, setWebhookCopied] = useState(false);

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        Integração Jira da squad. Comentários humanos no Jira aparecem na
        timeline da task; mudanças de estágio do pipeline viram comentários
        + transitions no Jira automaticamente.
      </p>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Conexão</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          <p>
            <span className="text-muted-foreground">Workspace:</span>{' '}
            {client?.jira_workspace_url ? (
              <code className="text-xs">{client.jira_workspace_url}</code>
            ) : (
              <span className="text-muted-foreground">Não conectado</span>
            )}
          </p>
          <p>
            <span className="text-muted-foreground">Conta:</span>{' '}
            {integration?.email ? (
              <code className="text-xs">{integration.email}</code>
            ) : (
              <span className="text-muted-foreground">—</span>
            )}
          </p>
          <p>
            <span className="text-muted-foreground">Projetos cobertos:</span>{' '}
            {projects.length === 0 ? (
              <span className="text-muted-foreground">Nenhum</span>
            ) : (
              projects.map(p => (
                <code key={p} className="ml-1 rounded bg-muted px-1 text-xs">{p}</code>
              ))
            )}
          </p>
        </CardContent>
      </Card>

      {integration && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Webhook</CardTitle>
            <CardDescription>
              Cole essa URL no Jira Cloud em <em>Settings → System →
              WebHooks → Create</em>. Marque os eventos:{' '}
              <code className="text-xs">
                {integration.supported_events.join(', ')}
              </code>.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            <div className="flex items-center gap-2">
              <code className="flex-1 rounded border bg-muted px-2 py-1.5 text-xs break-all">
                {integration.webhook_url}
              </code>
              <Button
                size="sm"
                variant="outline"
                onClick={() => {
                  navigator.clipboard.writeText(integration.webhook_url);
                  setWebhookCopied(true);
                  setTimeout(() => setWebhookCopied(false), 1500);
                }}
              >
                {webhookCopied ? 'Copiado!' : 'Copiar'}
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {integration && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Mapeamento de estágios</CardTitle>
            <CardDescription>
              Quando uma task entra num desses estágios, postamos um
              comentário e tentamos transitar a issue pro status alvo.
              Customização por tenant chega em S-8.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-muted-foreground">
                  <th className="py-1.5">Estágio</th>
                  <th className="py-1.5">Status Jira</th>
                  <th className="py-1.5">Comentário postado</th>
                </tr>
              </thead>
              <tbody>
                {integration.stage_mapping.map(row => (
                  <tr key={row.stage} className="border-t">
                    <td className="py-1.5 pr-3">
                      <code className="text-xs">{row.stage}</code>
                    </td>
                    <td className="py-1.5 pr-3">
                      <Badge variant="outline">{row.target_status}</Badge>
                    </td>
                    <td className="py-1.5 text-xs text-muted-foreground">
                      {row.message_preview}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      )}

      {!integration?.connected && (
        <Card>
          <CardContent className="p-4 text-sm text-muted-foreground">
            <p className="font-medium text-foreground mb-1">
              Sem Jira conectado?
            </p>
            <p>
              Você pode criar demandas direto pelo painel em{' '}
              <a href="/demands" className="underline">/demands</a>{' '}
              — funciona igual, sem precisar do Jira.
            </p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}


// ---- Config tab ----

function ConfigTab({ clientId, squadId }: { clientId: string; squadId: string }) {
  const squadQuery = useQuery({
    queryKey: ['squad', clientId, squadId],
    queryFn: () => fetchSquad(clientId, squadId),
  });

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Identidade</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          <p>Nome: {squadQuery.data?.name}</p>
          <p>Slug: <code className="text-xs">{squadQuery.data?.slug}</code></p>
          <p>Status: <StatusBadge status={squadQuery.data?.status ?? 'active'} /></p>
          <p className="text-xs text-muted-foreground">
            💡 Edição de nome/descrição/domain chega em S-9.
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base text-destructive">Zona perigosa</CardTitle>
          <CardDescription>
            Ações destrutivas. Pensar duas vezes.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-2">
          <Button variant="outline" size="sm" disabled>
            ⏸ Pausar squad (em breve)
          </Button>
          <Button variant="outline" size="sm" disabled>
            📦 Arquivar squad (em breve)
          </Button>
          <p className="text-xs text-muted-foreground">
            💡 Implementação completa de arquivar squad chega em S-9.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}


function StatusBadge({ status }: { status: Squad['status'] | string }) {
  const map: Record<string, { variant: any; label: string }> = {
    provisioning: { variant: 'warning', label: 'Provisionando' },
    active: { variant: 'success', label: 'Ativa' },
    paused: { variant: 'warning', label: 'Pausada' },
    archived: { variant: 'muted', label: 'Arquivada' },
  };
  const m = map[status] ?? { variant: 'outline', label: String(status) };
  return <Badge variant={m.variant}>{m.label}</Badge>;
}


// ---- Agents tab (legacy do PR original) ----

function AgentsList({ clientId, squad }: { clientId: string; squad: Squad }) {
  const queryClient = useQueryClient();
  const agentsQuery = useQuery({
    queryKey: ['agents', clientId, squad.id],
    queryFn: () => fetchAgents(clientId, squad.id),
  });
  const skillsQuery = useQuery({
    queryKey: ['skills'],
    queryFn: () => fetchSkillTemplates(),
  });
  const [openDialog, setOpenDialog] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState<AgentInstanceCreate>({
    skill_template_id: '',
    name: '',
    domain_business: 'general',
  });

  const createMutation = useMutation({
    mutationFn: () => createAgent(clientId, squad.id, form),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['agents', clientId, squad.id] });
      setOpenDialog(false);
      setError(null);
      setForm({ skill_template_id: '', name: '', domain_business: 'general' });
    },
    onError: (err: unknown) => {
      setError(formatApiError(err, 'Falha ao criar agente.'));
    },
  });

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    createMutation.mutate();
  };

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <Dialog open={openDialog} onOpenChange={setOpenDialog}>
          <DialogTrigger asChild>
            <Button size="sm">
              <Plus className="mr-1 size-3" />
              Adicionar agente
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Adicionar agente</DialogTitle>
              <DialogDescription>
                Provisiona um novo agente com skill template do catálogo.
              </DialogDescription>
            </DialogHeader>
            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="space-y-1.5">
                <Label htmlFor="skill">Skill template</Label>
                <select
                  id="skill"
                  value={form.skill_template_id}
                  onChange={(e) =>
                    setForm({ ...form, skill_template_id: e.target.value })
                  }
                  required
                  className="w-full rounded-md border bg-background px-2 py-1.5 text-sm"
                >
                  <option value="">Selecione…</option>
                  {(skillsQuery.data ?? []).map((s: SkillTemplate) => (
                    <option key={s.id} value={s.id}>
                      {s.name} ({s.slug})
                    </option>
                  ))}
                </select>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="name">Nome</Label>
                <Input
                  id="name"
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  placeholder="ex: BA Plataforma"
                  required
                />
              </div>
              {error && (
                <p className="text-xs text-destructive">{error}</p>
              )}
              <DialogFooter>
                <Button type="submit" disabled={createMutation.isPending}>
                  {createMutation.isPending ? 'Criando…' : 'Criar'}
                </Button>
              </DialogFooter>
            </form>
          </DialogContent>
        </Dialog>
      </div>

      {agentsQuery.data?.length === 0 ? (
        <p className="text-sm text-muted-foreground">Nenhum agente ainda.</p>
      ) : (
        <div className="grid gap-3">
          {agentsQuery.data?.map((a: AgentInstance) => (
            <AgentCard
              key={a.id}
              clientId={clientId}
              squadId={squad.id}
              agent={a}
            />
          ))}
        </div>
      )}
    </div>
  );
}


// ---- Agent card com modais Editar prompt + Remover (S-6) ----

function AgentCard({
  clientId, squadId, agent,
}: { clientId: string; squadId: string; agent: AgentInstance }) {
  const queryClient = useQueryClient();
  const [openEdit, setOpenEdit] = useState(false);
  const [openDelete, setOpenDelete] = useState(false);

  const skillQuery = useQuery({
    queryKey: ['skill-template', agent.skill_template_id],
    queryFn: () => fetchSkillTemplate(agent.skill_template_id),
  });
  const skill = skillQuery.data;

  const isCustomized = Boolean(agent.config_overrides?.system_prompt_custom_at);
  const isDisabled = agent.status === 'disabled';

  const deleteMutation = useMutation({
    mutationFn: () => deleteAgent(clientId, squadId, agent.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['agents', clientId, squadId] });
      setOpenDelete(false);
    },
  });

  return (
    <Card className={isDisabled ? 'opacity-50' : ''}>
      <CardContent className="p-4">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 min-w-0">
            <Bot className="size-4 text-muted-foreground shrink-0" />
            <span className="font-medium truncate">{agent.name}</span>
            {skill && (
              <Badge variant="outline" className="shrink-0">
                {skill.tier}
              </Badge>
            )}
            {agent.domain_business && (
              <Badge variant="muted" className="shrink-0">
                {agent.domain_business}
              </Badge>
            )}
            {isCustomized && (
              <Badge variant="success" className="shrink-0">
                Personalizado
              </Badge>
            )}
            {isDisabled && (
              <Badge variant="muted" className="shrink-0">
                Removido
              </Badge>
            )}
          </div>
          {!isDisabled && (
            <div className="flex items-center gap-1 shrink-0">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setOpenEdit(true)}
                title="Editar prompt"
              >
                <Pencil className="size-3.5" />
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setOpenDelete(true)}
                title="Remover agente"
              >
                <Trash2 className="size-3.5 text-destructive" />
              </Button>
            </div>
          )}
        </div>
        {skill && (
          <p className="mt-1.5 text-xs text-muted-foreground font-mono">
            {skill.slug} · v{skill.version} · {skill.model_alias}
          </p>
        )}
      </CardContent>

      {openEdit && skill && (
        <EditPromptDialog
          clientId={clientId}
          squadId={squadId}
          agent={agent}
          skill={skill}
          onClose={() => setOpenEdit(false)}
          onSaved={() => {
            queryClient.invalidateQueries({ queryKey: ['agents', clientId, squadId] });
            setOpenEdit(false);
          }}
        />
      )}

      {openDelete && (
        <Dialog open={openDelete} onOpenChange={setOpenDelete}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Remover {agent.name}?</DialogTitle>
              <DialogDescription>
                {deleteConsequenceText(skill?.tier)}
              </DialogDescription>
            </DialogHeader>
            {deleteMutation.error && (
              <p className="text-xs text-destructive">
                {formatApiError(deleteMutation.error, 'Falha ao remover agente.')}
              </p>
            )}
            <DialogFooter>
              <Button
                variant="outline"
                onClick={() => setOpenDelete(false)}
                disabled={deleteMutation.isPending}
              >
                Cancelar
              </Button>
              <Button
                variant="destructive"
                onClick={() => deleteMutation.mutate()}
                disabled={deleteMutation.isPending}
              >
                {deleteMutation.isPending ? 'Removendo…' : 'Remover'}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}
    </Card>
  );
}


function deleteConsequenceText(tier: string | undefined): string {
  switch (tier) {
    case 'ba':
      return (
        'Sem BA, demandas chegam direto ao Architect sem refinamento ' +
        'estruturado. Demandas vagas terão menos contexto antes do plano.'
      );
    case 'reviewer':
      return (
        'Sem Reviewer, os PRs abertos pelos Devs ficam direto pra revisão ' +
        'humana — sem segunda passada de checagem automática.'
      );
    case 'architect':
      return (
        'Architect é obrigatório. Só será possível remover se houver outro ' +
        'Architect ativo na squad — caso contrário o pipeline trava.'
      );
    case 'dev':
      return (
        'Dev é obrigatório (≥1 por squad). Só será possível remover se houver ' +
        'outro Dev ativo. O agente é desativado, não apagado — pode ser ' +
        'reativado depois.'
      );
    default:
      return 'O agente será desativado (não apagado). Pode ser reativado depois.';
  }
}


// ---- Editar prompt dialog ----

function EditPromptDialog({
  clientId, squadId, agent, skill, onClose, onSaved,
}: {
  clientId: string;
  squadId: string;
  agent: AgentInstance;
  skill: SkillTemplate;
  onClose: () => void;
  onSaved: () => void;
}) {
  const queryClient = useQueryClient();
  const [systemPrompt, setSystemPrompt] = useState('');
  const [modelAlias, setModelAlias] = useState(skill.model_alias);
  const [error, setError] = useState<string | null>(null);

  // Pre-carrega prompt atual: se ja existe system_prompt_template (skill
  // custom), usa esse; senao mostra placeholder pra cliente preencher.
  useEffect(() => {
    const tpl = (skill as any).system_prompt_template;
    if (typeof tpl === 'string' && tpl.length > 0) {
      setSystemPrompt(tpl);
    }
  }, [skill]);

  const saveMutation = useMutation({
    mutationFn: () =>
      updateAgentPrompt(clientId, squadId, agent.id, {
        system_prompt: systemPrompt,
        model_alias: modelAlias !== skill.model_alias ? modelAlias : undefined,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ['skill-template', agent.skill_template_id],
      });
      onSaved();
    },
    onError: (err: unknown) => {
      setError(formatApiError(err, 'Falha ao salvar prompt.'));
    },
  });

  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Editar prompt — {agent.name}</DialogTitle>
          <DialogDescription>
            Sobrescreve o system prompt deste agente. Vira uma versão
            client-scoped: o template original do catálogo continua
            intocado para outros tenants. O agente será re-provisionado na
            Anthropic na próxima execução.
          </DialogDescription>
        </DialogHeader>

        <form
          onSubmit={(e: FormEvent) => {
            e.preventDefault();
            setError(null);
            saveMutation.mutate();
          }}
          className="space-y-4"
        >
          <div className="space-y-1.5">
            <Label htmlFor="model">Modelo</Label>
            <select
              id="model"
              value={modelAlias}
              onChange={(e) => setModelAlias(e.target.value)}
              className="w-full rounded-md border bg-background px-2 py-1.5 text-sm"
            >
              <option value="claude-opus-4-7">Opus 4.7 (mais capaz)</option>
              <option value="claude-sonnet-4-6">Sonnet 4.6 (balanceado)</option>
              <option value="claude-haiku-4-5">Haiku 4.5 (mais barato)</option>
            </select>
            <p className="text-xs text-muted-foreground">
              Atual: <code>{skill.model_alias}</code>. Trocar modelo
              re-provisiona o agente.
            </p>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="prompt">System prompt</Label>
            <textarea
              id="prompt"
              value={systemPrompt}
              onChange={(e) => setSystemPrompt(e.target.value)}
              required
              minLength={10}
              rows={12}
              placeholder="Você é um agente de…"
              className="w-full rounded-md border bg-background px-3 py-2 text-sm font-mono"
            />
            <p className="text-xs text-muted-foreground">
              {systemPrompt.length} caracteres. Mínimo 10.
            </p>
          </div>

          {error && <p className="text-xs text-destructive">{error}</p>}

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={onClose}
              disabled={saveMutation.isPending}
            >
              Cancelar
            </Button>
            <Button
              type="submit"
              disabled={saveMutation.isPending || systemPrompt.length < 10}
            >
              {saveMutation.isPending ? 'Salvando…' : 'Salvar'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

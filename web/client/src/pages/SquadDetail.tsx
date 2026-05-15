import { useState, type FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router-dom';
import {
  ArrowLeft, Bot, Code2, GitBranch, Plus,
} from 'lucide-react';
import {
  api,
  createAgent,
  fetchAgents,
  fetchClient,
  fetchManifest,
  fetchSkillTemplates,
  fetchSquad,
  fetchTasks,
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


// ---- Jira tab ----

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
  const projects: string[] =
    (manifestQuery.data?.content as ManifestContent | undefined)?.owns?.jira_projects ?? [];

  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">
        Integração Jira da squad (workspace + projetos cobertos).
      </p>
      <Card>
        <CardContent className="p-4 space-y-2 text-sm">
          <p>
            <span className="text-muted-foreground">Workspace:</span>{' '}
            {client?.jira_workspace_url ? (
              <code className="text-xs">{client.jira_workspace_url}</code>
            ) : (
              <span className="text-muted-foreground">Não conectado</span>
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
      <p className="text-xs text-muted-foreground">
        💡 Integração Jira bidirecional (webhook, comentários, status mapping) chega em S-7.
      </p>
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
            <Card key={a.id}>
              <CardContent className="p-4">
                <div className="flex items-center gap-2">
                  <Bot className="size-4 text-muted-foreground" />
                  <span className="font-medium">{a.name}</span>
                  {a.domain_business && (
                    <Badge variant="muted">{a.domain_business}</Badge>
                  )}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

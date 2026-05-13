import { useState, type FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, Bot, GitBranch, Plus, Trash2 } from 'lucide-react';
import {
  createAgent,
  fetchAgents,
  fetchClient,
  fetchManifest,
  fetchSkillTemplates,
  fetchSquad,
  updateManifest,
  type AgentInstance,
  type AgentInstanceCreate,
  type ManifestContent,
  type SkillTemplate,
  type Squad,
} from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';

export default function SquadDetailPage() {
  const { clientId, squadId } = useParams<{ clientId: string; squadId: string }>();
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
      <Button variant="ghost" size="sm" onClick={() => navigate(`/clients/${clientId}`)}>
        <ArrowLeft className="size-4" />
        Voltar para {client?.name ?? 'cliente'}
      </Button>

      <div>
        <h1 className="text-3xl font-semibold tracking-tight">{squad.name}</h1>
        <div className="mt-1 flex items-center gap-2 text-muted-foreground">
          <span className="font-mono text-sm">{squad.slug}</span>
          <StatusBadge status={squad.status} />
          {squad.domain && (
            <span className="text-xs text-muted-foreground">· {squad.domain}</span>
          )}
        </div>
      </div>

      <Tabs defaultValue="manifest" className="w-full">
        <TabsList>
          <TabsTrigger value="manifest">Manifest</TabsTrigger>
          <TabsTrigger value="agents">Agentes</TabsTrigger>
        </TabsList>

        <TabsContent value="manifest">
          <ManifestEditor clientId={clientId!} squadId={squadId!} />
        </TabsContent>

        <TabsContent value="agents">
          <AgentsList clientId={clientId!} squad={squad} />
        </TabsContent>
      </Tabs>
    </div>
  );
}

function StatusBadge({ status }: { status: Squad['status'] }) {
  const map: Record<string, { variant: any; label: string }> = {
    provisioning: { variant: 'warning', label: 'Provisionando' },
    active: { variant: 'success', label: 'Ativa' },
    paused: { variant: 'warning', label: 'Pausada' },
    archived: { variant: 'muted', label: 'Arquivada' },
  };
  const m = map[status] ?? { variant: 'outline', label: status };
  return <Badge variant={m.variant}>{m.label}</Badge>;
}

// ---- Manifest editor ----

function ManifestEditor({ clientId, squadId }: { clientId: string; squadId: string }) {
  const queryClient = useQueryClient();
  const manifestQuery = useQuery({
    queryKey: ['manifest', clientId, squadId],
    queryFn: () => fetchManifest(clientId, squadId),
    enabled: Boolean(clientId && squadId),
    retry: false,
  });

  const initial: ManifestContent = manifestQuery.data?.content ?? { owns: {} };
  const [repos, setRepos] = useState<string[]>(initial.owns.repos ?? []);
  const [schemas, setSchemas] = useState<string[]>(
    initial.owns.database?.schemas ?? initial.owns.database_schemas ?? [],
  );
  const [jiraProjects, setJiraProjects] = useState<string[]>(
    initial.owns.jira_projects ?? [],
  );
  const [eventsPublish, setEventsPublish] = useState<string[]>(
    initial.owns.events?.publishes ?? [],
  );
  const [apisPublish, setApisPublish] = useState<string[]>(
    initial.owns.apis?.publishes ?? [],
  );

  // Refresh dos states quando manifest carregar
  const isInitialized = manifestQuery.data?.id;
  const initializedRef = useState({ done: false })[0];
  if (isInitialized && !initializedRef.done) {
    initializedRef.done = true;
    setRepos(manifestQuery.data!.content.owns.repos ?? []);
    setSchemas(
      manifestQuery.data!.content.owns.database?.schemas ??
        manifestQuery.data!.content.owns.database_schemas ??
        [],
    );
    setJiraProjects(manifestQuery.data!.content.owns.jira_projects ?? []);
    setEventsPublish(manifestQuery.data!.content.owns.events?.publishes ?? []);
    setApisPublish(manifestQuery.data!.content.owns.apis?.publishes ?? []);
  }

  const mutation = useMutation({
    mutationFn: () => {
      const content: ManifestContent = {
        owns: {
          repos,
          database: { schemas },
          jira_projects: jiraProjects,
          events: { publishes: eventsPublish },
          apis: { publishes: apisPublish },
        },
        humans_embedded: initial.humans_embedded,
      };
      return updateManifest(clientId, squadId, content);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['manifest', clientId, squadId] });
      queryClient.invalidateQueries({ queryKey: ['squad', clientId, squadId] });
    },
  });

  function handleSave(event: FormEvent) {
    event.preventDefault();
    mutation.mutate();
  }

  if (manifestQuery.isLoading) {
    return <p className="text-sm text-muted-foreground">Carregando manifest…</p>;
  }

  const currentVersion = manifestQuery.data?.version;

  return (
    <form onSubmit={handleSave} className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <GitBranch className="size-4 text-brand-500" />
            Manifest
            {currentVersion !== undefined && (
              <Badge variant="secondary" className="ml-2">
                v{currentVersion}
              </Badge>
            )}
          </CardTitle>
          <CardDescription>
            Define o que a squad pode tocar. Salvar cria uma nova VERSÃO do
            manifest (versões antigas são preservadas).
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <ListEditor
            label="Repos (owns.repos)"
            help="URLs completas: https://github.com/owner/repo"
            value={repos}
            onChange={setRepos}
            placeholder="https://github.com/rlenzi/reco.orbis.ai.api"
          />
          <ListEditor
            label="Schemas de banco (owns.database.schemas)"
            help="Schemas Postgres que a squad pode migrar"
            value={schemas}
            onChange={setSchemas}
            placeholder="payments"
          />
          <ListEditor
            label="Projetos Jira (owns.jira_projects)"
            help="Project keys que a squad opera"
            value={jiraProjects}
            onChange={setJiraProjects}
            placeholder="PAY"
          />
          <ListEditor
            label="Eventos publicados (owns.events.publishes)"
            help="Tópicos/eventos que a squad pode publicar (glob aceito: payment.*)"
            value={eventsPublish}
            onChange={setEventsPublish}
            placeholder="payment.*"
          />
          <ListEditor
            label="APIs publicadas (owns.apis.publishes)"
            help="Rotas HTTP que a squad é dona (glob aceito: /api/payments/*)"
            value={apisPublish}
            onChange={setApisPublish}
            placeholder="/api/payments/*"
          />
          <Button type="submit" disabled={mutation.isPending}>
            {mutation.isPending ? 'Salvando…' : 'Salvar (nova versão)'}
          </Button>
          {mutation.isSuccess && (
            <p className="text-sm text-success">Salvo como nova versão.</p>
          )}
          {mutation.isError && (
            <p className="text-sm text-destructive">
              Erro ao salvar: {(mutation.error as any)?.response?.data?.detail ?? 'desconhecido'}
            </p>
          )}
        </CardContent>
      </Card>
    </form>
  );
}

function ListEditor({
  label,
  help,
  value,
  onChange,
  placeholder,
}: {
  label: string;
  help: string;
  value: string[];
  onChange: (next: string[]) => void;
  placeholder?: string;
}) {
  const [draft, setDraft] = useState('');

  function add() {
    if (!draft.trim()) return;
    if (value.includes(draft.trim())) return;
    onChange([...value, draft.trim()]);
    setDraft('');
  }

  return (
    <div className="space-y-1.5">
      <Label>{label}</Label>
      <p className="text-xs text-muted-foreground">{help}</p>
      <div className="flex gap-2">
        <Input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder={placeholder}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault();
              add();
            }
          }}
        />
        <Button type="button" variant="secondary" onClick={add}>
          Adicionar
        </Button>
      </div>
      {value.length > 0 && (
        <ul className="mt-2 space-y-1">
          {value.map((item, idx) => (
            <li
              key={`${item}-${idx}`}
              className="flex items-center justify-between rounded-md border border-border bg-muted/40 px-3 py-1.5 text-sm font-mono"
            >
              <span className="truncate">{item}</span>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => onChange(value.filter((_, i) => i !== idx))}
              >
                <Trash2 className="size-3.5 text-destructive" />
              </Button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// ---- Agents ----

function AgentsList({ clientId, squad }: { clientId: string; squad: Squad }) {
  const navigate = useNavigate();
  const [openCreate, setOpenCreate] = useState(false);
  const agentsQuery = useQuery({
    queryKey: ['agents', clientId, squad.id],
    queryFn: () => fetchAgents(clientId, squad.id),
  });

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between">
        <div>
          <CardTitle>Agentes desta squad</CardTitle>
          <CardDescription>
            Instâncias provisionadas a partir de skill templates. Cada agente
            tem tier (BA/Architect/Dev/Onboarding) e config própria.
          </CardDescription>
        </div>
        <Dialog open={openCreate} onOpenChange={setOpenCreate}>
          <DialogTrigger asChild>
            <Button size="sm">
              <Plus className="size-4" /> Novo agente
            </Button>
          </DialogTrigger>
          <CreateAgentDialog
            clientId={clientId}
            squadId={squad.id}
            onSuccess={() => setOpenCreate(false)}
          />
        </Dialog>
      </CardHeader>
      <CardContent>
        {agentsQuery.isLoading ? (
          <p className="text-sm text-muted-foreground">Carregando…</p>
        ) : (agentsQuery.data ?? []).length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Nenhum agente nesta squad. Provisione 1 BA + 1 Architect + 1+ Devs
            pra começar.
          </p>
        ) : (
          <ul className="space-y-2">
            {(agentsQuery.data ?? []).map((agent) => (
              <AgentRow key={agent.id} agent={agent} onClick={() => navigate(`/clients/${clientId}/squads/${squad.id}/agents/${agent.id}`)} />
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

function AgentRow({
  agent,
  onClick,
}: {
  agent: AgentInstance;
  onClick: () => void;
}) {
  return (
    <li
      className="flex items-center justify-between rounded-md border border-border p-3 hover:bg-muted/40 cursor-pointer"
      onClick={onClick}
    >
      <div className="flex items-center gap-3">
        <div className="grid size-9 place-items-center rounded-md bg-brand-500/10">
          <Bot className="size-4 text-brand-500" />
        </div>
        <div>
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-medium">{agent.name}</span>
            <AgentStatusBadge status={agent.status} />
          </div>
          <div className="text-xs text-muted-foreground font-mono">
            {agent.domain_business ?? 'sem domínio'} ·{' '}
            {agent.last_active_at
              ? `ativo ${new Date(agent.last_active_at).toLocaleString('pt-BR')}`
              : 'nunca executou'}
          </div>
        </div>
      </div>
    </li>
  );
}

function AgentStatusBadge({ status }: { status: AgentInstance['status'] }) {
  const map: Record<string, { variant: any; label: string }> = {
    idle: { variant: 'muted', label: 'Idle' },
    busy: { variant: 'warning', label: 'Executando' },
    paused: { variant: 'warning', label: 'Pausado' },
    disabled: { variant: 'danger', label: 'Desabilitado' },
  };
  const m = map[status] ?? { variant: 'outline', label: status };
  return <Badge variant={m.variant}>{m.label}</Badge>;
}

function CreateAgentDialog({
  clientId,
  squadId,
  onSuccess,
}: {
  clientId: string;
  squadId: string;
  onSuccess: () => void;
}) {
  const queryClient = useQueryClient();
  const [templateId, setTemplateId] = useState('');
  const [name, setName] = useState('');
  const [domain, setDomain] = useState('');
  const [error, setError] = useState<string | null>(null);

  const templatesQuery = useQuery({
    queryKey: ['skill-templates'],
    queryFn: fetchSkillTemplates,
  });

  const mutation = useMutation({
    mutationFn: (payload: AgentInstanceCreate) =>
      createAgent(clientId, squadId, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['agents', clientId, squadId] });
      onSuccess();
    },
    onError: (err: any) =>
      setError(err?.response?.data?.detail ?? 'Falha ao criar agente'),
  });

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    if (!templateId) {
      setError('Escolha um skill template');
      return;
    }
    mutation.mutate({
      skill_template_id: templateId,
      name,
      domain_business: domain || undefined,
    });
  }

  return (
    <DialogContent>
      <DialogHeader>
        <DialogTitle>Novo agente</DialogTitle>
        <DialogDescription>
          Provisiona uma instância a partir de um skill template existente.
        </DialogDescription>
      </DialogHeader>
      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="space-y-1.5">
          <Label htmlFor="template">Skill template *</Label>
          <select
            id="template"
            value={templateId}
            onChange={(e) => setTemplateId(e.target.value)}
            className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            required
          >
            <option value="">Selecione…</option>
            {(templatesQuery.data ?? []).map((tpl: SkillTemplate) => (
              <option key={tpl.id} value={tpl.id}>
                [{tpl.tier}] {tpl.name} — {tpl.model_alias}
              </option>
            ))}
          </select>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="agentName">Nome do agente *</Label>
          <Input
            id="agentName"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Dev Backend #1"
            required
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="agentDomain">Domínio de negócio (opcional)</Label>
          <Input
            id="agentDomain"
            value={domain}
            onChange={(e) => setDomain(e.target.value)}
            placeholder="pagamentos"
          />
        </div>
        {error && <p className="text-sm text-destructive">{error}</p>}
        <DialogFooter>
          <Button type="submit" disabled={mutation.isPending}>
            {mutation.isPending ? 'Criando…' : 'Provisionar agente'}
          </Button>
        </DialogFooter>
      </form>
    </DialogContent>
  );
}

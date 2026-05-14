import { useState, type FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link, useNavigate, useParams } from 'react-router-dom';
import {
  ArrowLeft,
  Bot,
  Clock,
  Cpu,
  FileCode,
  History,
  KeyRound,
  Layers,
  Play,
  Wrench,
} from 'lucide-react';
import {
  fetchAgentRuns,
  fetchAgents,
  fetchSkillTemplate,
  fetchSquad,
  triggerAgentRun,
  type AgentInstance,
  type AgentRunItem,
  type AgentRunTriggerResponse,
  type RunStatus,
  type SkillTemplate,
} from '@/lib/api';
import { useClientId } from '@/lib/use-client-id';
import { formatApiError } from '@/lib/utils';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

export default function AgentDetailPage() {
  const clientId = useClientId();
  const { squadId, agentId } = useParams<{ squadId: string;
    agentId: string; }>();
  const navigate = useNavigate();

  const squadQuery = useQuery({
    queryKey: ['squad', clientId, squadId],
    queryFn: () => fetchSquad(clientId!, squadId!),
    enabled: Boolean(clientId && squadId),
  });

  const agentsQuery = useQuery({
    queryKey: ['agents', clientId, squadId],
    queryFn: () => fetchAgents(clientId!, squadId!),
    enabled: Boolean(clientId && squadId),
  });

  const agent = (agentsQuery.data ?? []).find((a) => a.id === agentId);

  const tplQuery = useQuery({
    queryKey: ['skill-template', agent?.skill_template_id],
    queryFn: () => fetchSkillTemplate(agent!.skill_template_id),
    enabled: Boolean(agent),
  });

  if (agentsQuery.isLoading || !agent) {
    return <div className="text-muted-foreground">Carregando agente…</div>;
  }

  const tpl = tplQuery.data;

  return (
    <div className="space-y-6">
      <Button
        variant="ghost"
        size="sm"
        onClick={() => navigate(`/squads/${squadId}`)}
      >
        <ArrowLeft className="size-4" />
        Voltar para {squadQuery.data?.name ?? 'squad'}
      </Button>

      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="grid size-14 place-items-center rounded-lg bg-brand-500/10">
            <Bot className="size-7 text-brand-500" />
          </div>
          <div>
            <h1 className="text-3xl font-semibold tracking-tight">{agent.name}</h1>
            <div className="mt-1 flex items-center gap-2 text-muted-foreground">
              <StatusBadge status={agent.status} />
              {tpl && <Badge variant="default">{tpl.tier.toUpperCase()}</Badge>}
              {agent.domain_business && (
                <span className="text-sm">· {agent.domain_business}</span>
              )}
            </div>
          </div>
        </div>
        <div className="flex items-start gap-3">
          <TriggerRunButton agent={agent} clientId={clientId} />
          <div className="text-right text-xs text-muted-foreground">
            <div>id</div>
            <div className="font-mono">{agent.id}</div>
          </div>
        </div>
      </div>

      {/* Sections */}
      <div className="grid gap-4 md:grid-cols-2">
        <InstanceCard agent={agent} />
        {tpl && <SkillTemplateCard tpl={tpl} />}
        {tpl && <ToolsCard tpl={tpl} />}
        {tpl && <KnowledgeCard tpl={tpl} />}
      </div>

      {tpl && (
        <Card>
          <CardHeader className="flex flex-row items-center gap-2 space-y-0">
            <FileCode className="size-5 text-brand-500" />
            <div>
              <CardTitle className="text-base">System prompt</CardTitle>
              <CardDescription>
                Referência ao arquivo de prompt versionado em git.
              </CardDescription>
            </div>
          </CardHeader>
          <CardContent>
            <div className="rounded-md bg-muted px-3 py-2 font-mono text-sm">
              {tpl.system_prompt_ref}
            </div>
            <p className="mt-2 text-xs text-muted-foreground">
              O conteúdo do prompt vive no repo{' '}
              <code className="font-mono">dev-autonomo-config</code> (a ser
              criado). Será carregado em runtime quando o agente for executado.
            </p>
          </CardContent>
        </Card>
      )}

      <RunsCard
        clientId={clientId!}
        squadId={squadId!}
        agentId={agent.id}
      />
    </div>
  );
}

const PAGE_SIZE = 20;

function RunsCard({
  clientId,
  squadId,
  agentId,
}: {
  clientId: string;
  squadId: string;
  agentId: string;
}) {
  const [offset, setOffset] = useState(0);

  const runsQuery = useQuery({
    queryKey: ['agent-runs', clientId, agentId, offset],
    queryFn: () =>
      fetchAgentRuns(clientId, agentId, { offset, limit: PAGE_SIZE }),
    placeholderData: (prev) => prev,
  });

  const page = runsQuery.data;
  const total = page?.total ?? 0;
  const items = page?.items ?? [];
  const pageEnd = Math.min(offset + items.length, total);

  return (
    <Card>
      <CardHeader className="flex flex-row items-center gap-2 space-y-0">
        <History className="size-5 text-brand-500" />
        <div className="flex-1">
          <CardTitle className="text-base">Histórico de execuções</CardTitle>
          <CardDescription>
            Runs do agente agrupados por task_id. Mais recentes primeiro.
          </CardDescription>
        </div>
        {total > 0 && (
          <span className="text-xs text-muted-foreground">
            {offset + 1}–{pageEnd} de {total}
          </span>
        )}
      </CardHeader>
      <CardContent>
        {runsQuery.isError && (
          <p className="text-sm text-destructive">
            Erro ao carregar execuções:{' '}
            {(runsQuery.error as Error)?.message ?? 'desconhecido'}
          </p>
        )}
        {runsQuery.isLoading && !page && (
          <p className="text-sm text-muted-foreground">Carregando…</p>
        )}
        {page && items.length === 0 && (
          <p className="text-sm italic text-muted-foreground">
            Nenhuma execução registrada ainda.
          </p>
        )}
        {items.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-xs uppercase text-muted-foreground">
                  <th className="py-2 pr-3 font-medium">Status</th>
                  <th className="py-2 pr-3 font-medium">Task</th>
                  <th className="py-2 pr-3 text-right font-medium">Tool calls</th>
                  <th className="py-2 pr-3 text-right font-medium">Custo</th>
                  <th className="py-2 pr-3 font-medium">Início</th>
                  <th className="py-2 font-medium">Duração</th>
                </tr>
              </thead>
              <tbody>
                {items.map((run) => (
                  <RunRow
                    key={run.task_id}
                    run={run}
                    squadId={squadId}
                    agentId={agentId}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}

        {total > PAGE_SIZE && (
          <div className="mt-4 flex items-center justify-end gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={offset === 0 || runsQuery.isFetching}
              onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
            >
              Anterior
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={offset + PAGE_SIZE >= total || runsQuery.isFetching}
              onClick={() => setOffset(offset + PAGE_SIZE)}
            >
              Próxima
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function RunRow({
  run,
  squadId,
  agentId,
}: {
  run: AgentRunItem;
  squadId: string;
  agentId: string;
}) {
  const cost = Number(run.total_cost_usd);
  const costFmt = isNaN(cost)
    ? run.total_cost_usd
    : cost.toLocaleString('en-US', {
        style: 'currency',
        currency: 'USD',
        minimumFractionDigits: 4,
      });

  const startedAt = new Date(run.started_at);
  const endedAt = run.ended_at ? new Date(run.ended_at) : null;
  const durationMs = endedAt ? endedAt.getTime() - startedAt.getTime() : null;

  const detailPath = `/squads/${squadId}/agents/${agentId}/runs/${run.task_id}`;

  return (
    <tr className="group border-b last:border-b-0 hover:bg-muted/40">
      <td className="py-2 pr-3">
        <Link to={detailPath} className="block">
          <RunStatusBadge status={run.status} />
        </Link>
      </td>
      <td className="py-2 pr-3">
        <Link to={detailPath} className="block group-hover:text-brand-500">
          {run.jira_issue_key ? (
            <div>
              <div className="font-mono text-xs font-medium group-hover:underline">
                {run.jira_issue_key}
              </div>
              {run.title && (
                <div
                  className="max-w-[36ch] truncate text-xs text-muted-foreground"
                  title={run.title}
                >
                  {run.title}
                </div>
              )}
            </div>
          ) : (
            <code
              className="font-mono text-xs text-muted-foreground group-hover:text-brand-500 group-hover:underline"
              title={run.task_id}
            >
              {run.task_id.slice(0, 8)}…
            </code>
          )}
        </Link>
      </td>
      <td className="py-2 pr-3 text-right font-mono text-xs">
        <Link to={detailPath} className="block">
          {run.tool_calls_count}
        </Link>
      </td>
      <td className="py-2 pr-3 text-right font-mono text-xs">
        <Link to={detailPath} className="block">
          {costFmt}
        </Link>
      </td>
      <td className="py-2 pr-3 text-xs text-muted-foreground">
        <Link to={detailPath} className="block">
          {startedAt.toLocaleString('pt-BR')}
        </Link>
      </td>
      <td className="py-2 text-xs text-muted-foreground">
        <Link to={detailPath} className="block">
          {durationMs !== null ? formatDuration(durationMs) : '—'}
        </Link>
      </td>
    </tr>
  );
}

function TriggerRunButton({
  agent,
  clientId,
}: {
  agent: AgentInstance;
  clientId: string;
}) {
  const [open, setOpen] = useState(false);
  const [issueKey, setIssueKey] = useState('');
  const [result, setResult] = useState<AgentRunTriggerResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const queryClient = useQueryClient();

  const TRIGGERABLE_TIERS = ['ba', 'architect', 'dev', 'reviewer'];
  const tier = agent.domain_business?.toLowerCase();
  const supported = tier ? TRIGGERABLE_TIERS.includes(tier) : false;

  const mutation = useMutation({
    mutationFn: () =>
      triggerAgentRun(clientId, agent.id, {
        jira_issue_key: issueKey.trim().toUpperCase(),
      }),
    onSuccess: (data) => {
      setResult(data);
      setError(null);
      queryClient.invalidateQueries({ queryKey: ['agent-runs', clientId, agent.id] });
    },
    onError: (err) => {
      setError(formatApiError(err, 'Falha ao disparar agente.'));
    },
  });

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!issueKey.trim()) return;
    setError(null);
    setResult(null);
    mutation.mutate();
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        setOpen(v);
        if (!v) {
          setIssueKey('');
          setResult(null);
          setError(null);
        }
      }}
    >
      <DialogTrigger asChild>
        <Button size="sm" disabled={!supported} title={supported ? '' : `Tier ${tier} não suporta trigger pelo painel`}>
          <Play className="size-4" /> Rodar agente
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Rodar {agent.name}</DialogTitle>
          <DialogDescription>
            Dispara o agente contra uma issue do Jira. O run sobe em background;
            acompanhe na aba de execuções abaixo.
          </DialogDescription>
        </DialogHeader>
        {result ? (
          <div className="space-y-2 text-sm">
            <p>
              Disparado! task_id <code className="font-mono">{result.task_id}</code>{' '}
              (pid {result.pid}).
            </p>
            <p className="text-xs text-muted-foreground">
              Log: <code className="font-mono">{result.log_path}</code>
            </p>
            <DialogFooter>
              <Button variant="outline" size="sm" onClick={() => setOpen(false)}>
                Fechar
              </Button>
            </DialogFooter>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-3">
            <div className="space-y-1.5">
              <Label htmlFor="issue">Issue Jira *</Label>
              <Input
                id="issue"
                value={issueKey}
                onChange={(e) => setIssueKey(e.target.value)}
                placeholder="LEO-53"
                required
              />
              <p className="text-xs text-muted-foreground">
                Ex: <code>LEO-53</code>. O agente segue o fluxo do tier dele
                (BA refina, Architect decompõe, Dev implementa, Reviewer revisa).
              </p>
            </div>
            {error && <p className="text-sm text-destructive">{error}</p>}
            <DialogFooter>
              <Button type="submit" disabled={mutation.isPending || !issueKey.trim()}>
                {mutation.isPending ? 'Disparando…' : 'Disparar'}
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}


function RunStatusBadge({ status }: { status: RunStatus }) {
  const map: Record<RunStatus, { variant: any; label: string }> = {
    completed: { variant: 'success', label: 'OK' },
    failed: { variant: 'danger', label: 'Falhou' },
    in_progress: { variant: 'warning', label: 'Rodando' },
  };
  const m = map[status] ?? { variant: 'outline', label: status };
  return <Badge variant={m.variant}>{m.label}</Badge>;
}

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  const s = Math.floor(ms / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  const sr = s % 60;
  return `${m}m${sr.toString().padStart(2, '0')}s`;
}

function StatusBadge({ status }: { status: AgentInstance['status'] }) {
  const map: Record<string, { variant: any; label: string }> = {
    idle: { variant: 'muted', label: 'Idle' },
    busy: { variant: 'warning', label: 'Executando' },
    paused: { variant: 'warning', label: 'Pausado' },
    disabled: { variant: 'danger', label: 'Desabilitado' },
  };
  const m = map[status] ?? { variant: 'outline', label: status };
  return <Badge variant={m.variant}>{m.label}</Badge>;
}

function InstanceCard({ agent }: { agent: AgentInstance }) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center gap-2 space-y-0">
        <Bot className="size-5 text-brand-500" />
        <CardTitle className="text-base">Instância</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2 text-sm">
        <Row label="Status">
          <StatusBadge status={agent.status} />
        </Row>
        <Row label="Domínio" value={agent.domain_business ?? '—'} />
        <Row
          label="Última atividade"
          value={
            <span className="flex items-center gap-1 text-muted-foreground">
              <Clock className="size-3.5" />
              {agent.last_active_at
                ? new Date(agent.last_active_at).toLocaleString('pt-BR')
                : 'nunca executou'}
            </span>
          }
        />
        <Row
          label="Criado em"
          value={new Date(agent.created_at).toLocaleString('pt-BR')}
        />
        {Object.keys(agent.config_overrides ?? {}).length > 0 && (
          <div className="mt-3">
            <div className="mb-1 text-xs text-muted-foreground">Overrides</div>
            <pre className="overflow-x-auto rounded bg-muted p-2 font-mono text-xs">
              {JSON.stringify(agent.config_overrides, null, 2)}
            </pre>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function SkillTemplateCard({ tpl }: { tpl: SkillTemplate }) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center gap-2 space-y-0">
        <Cpu className="size-5 text-brand-500" />
        <CardTitle className="text-base">Skill template</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2 text-sm">
        <Row
          label="Slug"
          value={
            <span className="font-mono text-xs">
              {tpl.slug} (v{tpl.version})
            </span>
          }
        />
        <Row label="Tier">
          <Badge variant="default">{tpl.tier.toUpperCase()}</Badge>
        </Row>
        <Row label="Modelo Claude">
          <code className="font-mono text-xs">{tpl.model_alias}</code>
        </Row>
        {tpl.description && <Row label="Descrição" value={tpl.description} />}
        {Object.keys(tpl.stack_primary).length > 0 && (
          <div className="pt-2">
            <div className="mb-1 flex items-center gap-1 text-xs text-muted-foreground">
              <Layers className="size-3.5" /> Stack primária
            </div>
            <code className="block rounded bg-muted px-2 py-1 font-mono text-xs">
              {Object.entries(tpl.stack_primary)
                .map(([k, v]) => `${k}: ${v}`)
                .join(', ')}
            </code>
          </div>
        )}
        {tpl.stack_secondary.length > 0 && (
          <div className="pt-2">
            <div className="mb-1 text-xs text-muted-foreground">
              Stack secundária
            </div>
            <div className="flex flex-wrap gap-1">
              {tpl.stack_secondary.map((s, i) => (
                <Badge key={i} variant="outline" className="font-mono text-xs">
                  {String(s)}
                </Badge>
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function ToolsCard({ tpl }: { tpl: SkillTemplate }) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center gap-2 space-y-0">
        <Wrench className="size-5 text-brand-500" />
        <div>
          <CardTitle className="text-base">Tools habilitadas</CardTitle>
          <CardDescription>
            Operações que o agente pode chamar durante a execução.
          </CardDescription>
        </div>
      </CardHeader>
      <CardContent>
        {tpl.tools_enabled.length === 0 ? (
          <p className="text-sm italic text-muted-foreground">
            Nenhuma tool habilitada.
          </p>
        ) : (
          <div className="flex flex-wrap gap-1">
            {tpl.tools_enabled.map((t, i) => (
              <Badge key={i} variant="secondary" className="font-mono text-xs">
                {String(t)}
              </Badge>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function KnowledgeCard({ tpl }: { tpl: SkillTemplate }) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center gap-2 space-y-0">
        <KeyRound className="size-5 text-brand-500" />
        <div>
          <CardTitle className="text-base">Knowledge partitions</CardTitle>
          <CardDescription>
            Coleções do Knowledge Hub que o agente consulta.
          </CardDescription>
        </div>
      </CardHeader>
      <CardContent>
        {tpl.knowledge_partitions.length === 0 ? (
          <p className="text-sm italic text-muted-foreground">
            Sem partições configuradas.
          </p>
        ) : (
          <ul className="space-y-1">
            {tpl.knowledge_partitions.map((p, i) => (
              <li
                key={i}
                className="rounded bg-muted px-2 py-1 font-mono text-xs"
              >
                {String(p)}
              </li>
            ))}
          </ul>
        )}
        <p className="mt-2 text-xs text-muted-foreground">
          <code>{'{squad}'}</code> é substituído pelo squad_id em runtime.
        </p>
      </CardContent>
    </Card>
  );
}

function Row({
  label,
  value,
  children,
}: {
  label: string;
  value?: React.ReactNode;
  children?: React.ReactNode;
}) {
  return (
    <div className="flex items-center justify-between gap-2">
      <span className="text-muted-foreground">{label}</span>
      <span className="text-right">{children ?? value}</span>
    </div>
  );
}

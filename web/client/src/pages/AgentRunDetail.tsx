import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router-dom';
import {
  Activity,
  AlertTriangle,
  ArrowLeft,
  Clock,
  CodeXml,
  DollarSign,
  ExternalLink,
  GitPullRequest,
  Hash,
  ListChecks,
} from 'lucide-react';
import {
  fetchAgentRunDetail,
  type ExternalCallItem,
  type RunStatus,
} from '@/lib/api';
import { useClientId } from '@/lib/use-client-id';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';

const CALLS_PAGE_SIZE = 100;

export default function AgentRunDetailPage() {
  const clientId = useClientId();
  const { squadId, agentId, taskId } = useParams<{ squadId: string;
    agentId: string;
    taskId: string; }>();
  const navigate = useNavigate();
  const [callsOffset, setCallsOffset] = useState(0);

  const runQuery = useQuery({
    queryKey: ['agent-run-detail', clientId, agentId, taskId, callsOffset],
    queryFn: () =>
      fetchAgentRunDetail(clientId!, agentId!, taskId!, {
        offset: callsOffset,
        limit: CALLS_PAGE_SIZE,
      }),
    enabled: Boolean(clientId && agentId && taskId),
    placeholderData: (prev) => prev,
  });

  if (runQuery.isLoading && !runQuery.data) {
    return <div className="text-muted-foreground">Carregando execução…</div>;
  }
  if (runQuery.isError) {
    return (
      <div className="text-destructive">
        Erro ao carregar execução:{' '}
        {(runQuery.error as Error)?.message ?? 'desconhecido'}
      </div>
    );
  }
  if (!runQuery.data) return null;

  const run = runQuery.data;
  const totalCost = Number(run.total_cost_usd);
  const costFmt = isNaN(totalCost)
    ? run.total_cost_usd
    : totalCost.toLocaleString('en-US', {
        style: 'currency',
        currency: 'USD',
        minimumFractionDigits: 4,
      });

  const callsTotal = run.calls_total;
  const callsStart = run.calls_offset;
  const callsEnd = Math.min(callsStart + run.calls.length, callsTotal);

  return (
    <div className="space-y-6">
      <Button
        variant="ghost"
        size="sm"
        onClick={() =>
          navigate(
            `/squads/${squadId}/agents/${agentId}`,
          )
        }
      >
        <ArrowLeft className="size-4" />
        Voltar para o agente
      </Button>

      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="grid size-14 place-items-center rounded-lg bg-brand-500/10">
            <Activity className="size-7 text-brand-500" />
          </div>
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">
              Execução {run.jira_issue_key ?? run.task_id.slice(0, 8)}
            </h1>
            <div className="mt-1 flex flex-wrap items-center gap-2 text-muted-foreground">
              <RunStatusBadge status={run.status} />
              {run.outcome_status !== 'skipped' && (
                <OutcomeBadge
                  status={run.outcome_status}
                  iterations={run.outcome_iterations}
                />
              )}
              {run.title && (
                <span className="text-sm">· {run.title}</span>
              )}
            </div>
            {(run.jira_issue_url || run.pr_search_url) && (
              <div className="mt-2 flex flex-wrap items-center gap-2">
                {run.jira_issue_url && (
                  <a
                    href={run.jira_issue_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 rounded-md border bg-card px-2 py-1 text-xs hover:bg-muted"
                  >
                    <ExternalLink className="size-3" />
                    Abrir no Jira
                  </a>
                )}
                {run.pr_search_url && (
                  <a
                    href={run.pr_search_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 rounded-md border bg-card px-2 py-1 text-xs hover:bg-muted"
                  >
                    <GitPullRequest className="size-3" />
                    Ver PR no GitHub
                  </a>
                )}
              </div>
            )}
          </div>
        </div>
        <div className="text-right text-xs text-muted-foreground">
          <div>task_id</div>
          <div className="font-mono">{run.task_id}</div>
        </div>
      </div>

      {/* Stats cards */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <StatCard
          icon={<DollarSign className="size-5 text-brand-500" />}
          label="Custo total"
          value={costFmt}
        />
        <StatCard
          icon={<ListChecks className="size-5 text-brand-500" />}
          label="Tool calls"
          value={String(run.tool_calls_count)}
        />
        <StatCard
          icon={<Clock className="size-5 text-brand-500" />}
          label="Duração"
          value={
            run.duration_ms !== null ? formatDuration(run.duration_ms) : '—'
          }
        />
        <StatCard
          icon={<Hash className="size-5 text-brand-500" />}
          label="Tokens (in/out)"
          value={`${formatNum(run.total_input_tokens)}/${formatNum(run.total_output_tokens)}`}
        />
      </div>

      {/* Cache + erros */}
      {(run.total_cache_creation_tokens > 0 ||
        run.total_cache_read_tokens > 0 ||
        run.error_count > 0) && (
        <Card>
          <CardContent className="flex flex-wrap items-center gap-6 py-4 text-sm">
            {run.total_cache_creation_tokens > 0 && (
              <div>
                <span className="text-muted-foreground">Cache write: </span>
                <span className="font-mono">
                  {formatNum(run.total_cache_creation_tokens)}
                </span>
              </div>
            )}
            {run.total_cache_read_tokens > 0 && (
              <div>
                <span className="text-muted-foreground">Cache hit: </span>
                <span className="font-mono">
                  {formatNum(run.total_cache_read_tokens)}
                </span>
              </div>
            )}
            {run.error_count > 0 && (
              <div className="flex items-center gap-1 text-destructive">
                <AlertTriangle className="size-4" />
                {run.error_count} erro(s) registrado(s)
              </div>
            )}
            <div className="ml-auto text-xs text-muted-foreground">
              {new Date(run.started_at).toLocaleString('pt-BR')}
              {' → '}
              {run.ended_at
                ? new Date(run.ended_at).toLocaleString('pt-BR')
                : '(em curso)'}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Timeline de chamadas */}
      <Card>
        <CardHeader className="flex flex-row items-center gap-2 space-y-0">
          <CodeXml className="size-5 text-brand-500" />
          <div className="flex-1">
            <CardTitle className="text-base">Timeline de chamadas</CardTitle>
            <CardDescription>
              Cada chamada à API Anthropic/Voyage feita durante este run, em
              ordem cronológica.
            </CardDescription>
          </div>
          {callsTotal > 0 && (
            <span className="text-xs text-muted-foreground">
              {callsStart + 1}–{callsEnd} de {callsTotal}
            </span>
          )}
        </CardHeader>
        <CardContent>
          <CallsTable
            calls={run.calls}
            startedAt={new Date(run.started_at)}
            startOffset={callsStart}
          />
          {callsTotal > CALLS_PAGE_SIZE && (
            <div className="mt-4 flex items-center justify-end gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={callsOffset === 0 || runQuery.isFetching}
                onClick={() =>
                  setCallsOffset(Math.max(0, callsOffset - CALLS_PAGE_SIZE))
                }
              >
                Anterior
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={
                  callsOffset + CALLS_PAGE_SIZE >= callsTotal ||
                  runQuery.isFetching
                }
                onClick={() => setCallsOffset(callsOffset + CALLS_PAGE_SIZE)}
              >
                Próxima
              </Button>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function StatCard({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
}) {
  return (
    <Card>
      <CardContent className="flex items-center gap-3 py-4">
        <div className="grid size-10 place-items-center rounded-md bg-muted">
          {icon}
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-xs text-muted-foreground">{label}</div>
          <div className="truncate font-mono text-base">{value}</div>
        </div>
      </CardContent>
    </Card>
  );
}

function CallsTable({
  calls,
  startedAt,
  startOffset,
}: {
  calls: ExternalCallItem[];
  startedAt: Date;
  startOffset: number;
}) {
  if (calls.length === 0) {
    return (
      <p className="text-sm italic text-muted-foreground">
        Sem chamadas registradas.
      </p>
    );
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b text-left text-xs uppercase text-muted-foreground">
            <th className="py-2 pr-3 font-medium">#</th>
            <th className="py-2 pr-3 font-medium">+t</th>
            <th className="py-2 pr-3 font-medium">Provider · Modelo</th>
            <th className="py-2 pr-3 text-right font-medium">Tokens in</th>
            <th className="py-2 pr-3 text-right font-medium">Tokens out</th>
            <th className="py-2 pr-3 text-right font-medium">Custo</th>
            <th className="py-2 pr-3 text-right font-medium">Latência</th>
            <th className="py-2 font-medium">Erro</th>
          </tr>
        </thead>
        <tbody>
          {calls.map((c, i) => {
            const ts = new Date(c.occurred_at);
            const offsetMs = ts.getTime() - startedAt.getTime();
            const cost = Number(c.cost_usd);
            const costFmt = isNaN(cost)
              ? c.cost_usd
              : cost.toLocaleString('en-US', {
                  style: 'currency',
                  currency: 'USD',
                  minimumFractionDigits: 4,
                });
            return (
              <tr
                key={c.id}
                className={
                  'border-b last:border-b-0 hover:bg-muted/40 ' +
                  (c.error ? 'bg-destructive/5' : '')
                }
              >
                <td className="py-2 pr-3 font-mono text-xs">
                  {startOffset + i + 1}
                </td>
                <td className="py-2 pr-3 font-mono text-xs text-muted-foreground">
                  +{formatDuration(offsetMs)}
                </td>
                <td className="py-2 pr-3">
                  <div className="flex items-center gap-2">
                    <Badge variant="outline" className="font-mono text-xs">
                      {c.provider.toLowerCase()}
                    </Badge>
                    <code className="font-mono text-xs text-muted-foreground">
                      {c.model ?? '—'}
                    </code>
                  </div>
                </td>
                <td className="py-2 pr-3 text-right font-mono text-xs">
                  {formatNum(c.input_tokens)}
                  {c.cache_read_input_tokens > 0 && (
                    <span
                      className="ml-1 text-muted-foreground"
                      title={`${c.cache_read_input_tokens} de cache hit`}
                    >
                      (·{formatNum(c.cache_read_input_tokens)})
                    </span>
                  )}
                </td>
                <td className="py-2 pr-3 text-right font-mono text-xs">
                  {formatNum(c.output_tokens)}
                </td>
                <td className="py-2 pr-3 text-right font-mono text-xs">
                  {costFmt}
                </td>
                <td className="py-2 pr-3 text-right font-mono text-xs text-muted-foreground">
                  {c.latency_ms !== null
                    ? formatDuration(c.latency_ms)
                    : '—'}
                </td>
                <td className="py-2 max-w-[24ch] truncate text-xs text-destructive">
                  {c.error ?? ''}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
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

function OutcomeBadge({
  status,
  iterations,
}: {
  status: 'pending' | 'satisfied' | 'failed' | 'skipped';
  iterations: number;
}) {
  const map: Record<typeof status, { variant: any; label: string; emoji: string }> = {
    pending: { variant: 'warning', label: 'Rubric pendente', emoji: '⏳' },
    satisfied: { variant: 'success', label: 'Rubric ✓', emoji: '✓' },
    failed: { variant: 'danger', label: 'Rubric ✗', emoji: '✗' },
    skipped: { variant: 'outline', label: 'Sem rubric', emoji: '—' },
  };
  const m = map[status];
  const suffix = iterations > 0 ? ` (iter ${iterations})` : '';
  return (
    <Badge variant={m.variant} title={`Outcome grader: ${status}${suffix}`}>
      {m.emoji} {m.label}{suffix}
    </Badge>
  );
}

function formatNum(n: number): string {
  return n.toLocaleString('pt-BR');
}

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  const s = Math.floor(ms / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  const sr = s % 60;
  return `${m}m${sr.toString().padStart(2, '0')}s`;
}

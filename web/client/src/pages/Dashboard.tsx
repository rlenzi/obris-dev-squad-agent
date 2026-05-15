import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  Activity, AlertCircle, ArrowRight, Bot,
  CheckCircle2, DollarSign, Loader2, Plus, TrendingDown, TrendingUp,
} from 'lucide-react';

import { useClientId } from '@/lib/use-client-id';
import {
  fetchDashboardSummary, fetchSquadsForClient,
  type TaskListItem,
} from '@/lib/api';
import { formatApiError } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';

/**
 * Dashboard principal (D-02 do redesign / S-2).
 *
 * Pergunta ao cliente em ordem:
 *   1. "Tem algo que precisa de mim agora?"  → seção Atenção (S-7 completará com signals Jira)
 *   2. "O que meus agentes estão fazendo?"  → Em curso
 *   3. "Estamos saudáveis?"  → KPIs
 *
 * Atividade recente = feed cronológico das últimas 10 tasks.
 *
 * Versão S-2: seção "Precisa atenção" mostra apenas tasks FAILED nas
 * últimas 24h (signal mais simples). Quando S-7 chegar (Jira bidirecional),
 * adiciona PRs aguardando revisão + outras pendências.
 */
export default function DashboardPage() {
  const navigate = useNavigate();
  const clientId = useClientId();

  const summaryQuery = useQuery({
    queryKey: ['dashboard-summary', clientId],
    queryFn: () => fetchDashboardSummary(clientId),
    refetchInterval: 30_000,  // polling leve a cada 30s
  });

  const squadsQuery = useQuery({
    queryKey: ['squads', clientId],
    queryFn: () => fetchSquadsForClient(clientId),
  });

  if (summaryQuery.isLoading) {
    return (
      <div className="mx-auto max-w-4xl py-12 px-6 text-center text-sm text-muted-foreground">
        <Loader2 className="mx-auto h-6 w-6 animate-spin" />
        <p className="mt-3">Carregando dashboard…</p>
      </div>
    );
  }

  if (summaryQuery.isError || !summaryQuery.data) {
    return (
      <div className="mx-auto max-w-4xl py-12 px-6">
        <p className="text-sm text-destructive">
          {formatApiError(summaryQuery.error, 'Erro carregando dashboard.')}
        </p>
      </div>
    );
  }

  const s = summaryQuery.data;
  const squads = squadsQuery.data ?? [];
  const inProgressTasks = s.recent_activity.filter(t => t.status === 'in_progress');
  const failedTasks = s.recent_activity.filter(
    t => t.status === 'failed' &&
    t.closed_at &&
    new Date(t.closed_at).getTime() > Date.now() - 86_400_000,
  );

  const costDelta = s.cost_last_month > 0
    ? ((s.cost_this_month - s.cost_last_month) / s.cost_last_month) * 100
    : null;

  const concludedDelta = s.completed_last_month > 0
    ? s.completed_this_month - s.completed_last_month
    : null;

  return (
    <div className="mx-auto max-w-4xl py-12 px-6 space-y-10">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Painel</h1>
        {squads.length > 0 && (
          <p className="text-sm text-muted-foreground">
            {squads.length === 1
              ? `Squad ativa: ${squads[0].name}`
              : `${squads.length} squads ativas`}
          </p>
        )}
      </header>

      {failedTasks.length > 0 && (
        <section className="space-y-3">
          <h2 className="flex items-center gap-2 text-sm font-medium">
            <AlertCircle className="h-4 w-4 text-destructive" />
            Precisa da sua atenção ({failedTasks.length})
          </h2>
          <div className="space-y-2">
            {failedTasks.map(t => (
              <AttentionCard
                key={t.id}
                task={t}
                onClick={() => navigate(`/tasks/${t.id}`)}
              />
            ))}
          </div>
        </section>
      )}

      {inProgressTasks.length > 0 && (
        <section className="space-y-3">
          <h2 className="flex items-center gap-2 text-sm font-medium">
            <Activity className="h-4 w-4 text-primary" />
            Em curso ({inProgressTasks.length})
          </h2>
          <ul className="space-y-1.5">
            {inProgressTasks.map(t => (
              <TaskRow
                key={t.id}
                task={t}
                onClick={() => navigate(`/tasks/${t.id}`)}
              />
            ))}
          </ul>
          <Button
            variant="ghost"
            size="sm"
            className="text-xs text-muted-foreground"
            onClick={() => navigate('/tasks')}
          >
            Ver todas as tasks
            <ArrowRight className="ml-1 h-3 w-3" />
          </Button>
        </section>
      )}

      <section className="space-y-3">
        <h2 className="text-sm font-medium">Visão geral do mês</h2>
        <div className="grid gap-4 md:grid-cols-3">
          <Kpi
            icon={<DollarSign className="h-4 w-4" />}
            title="Custo"
            value={`US$ ${s.cost_this_month.toFixed(2)}`}
            delta={costDelta}
            deltaLabel="vs mês anterior"
            invert
            onClickDetail={() => navigate('/cost')}
            detailLabel="Detalhar"
          />
          <Kpi
            icon={<CheckCircle2 className="h-4 w-4" />}
            title="Concluídas"
            value={String(s.completed_this_month)}
            delta={concludedDelta != null ? concludedDelta : null}
            deltaLabel="vs mês anterior"
          />
          <Kpi
            icon={<Bot className="h-4 w-4" />}
            title="Agentes ativos"
            value={String(s.active_agents)}
            onClickDetail={() => squads.length === 1
              ? navigate(`/squads/${squads[0].id}`)
              : navigate('/squads')}
            detailLabel={squads.length === 1 ? 'Ver squad' : 'Ver squads'}
          />
        </div>
      </section>

      {s.recent_activity.length > 0 && (
        <section className="space-y-3">
          <h2 className="text-sm font-medium">Atividade recente</h2>
          <ul className="space-y-1.5 text-sm">
            {s.recent_activity.slice(0, 10).map(t => (
              <RecentRow
                key={t.id}
                task={t}
                onClick={() => navigate(`/tasks/${t.id}`)}
              />
            ))}
          </ul>
        </section>
      )}

      {inProgressTasks.length === 0 && s.recent_activity.length === 0 && (
        <section className="rounded-md border border-dashed p-8 text-center">
          <p className="text-sm text-muted-foreground mb-4">
            Sua squad está pronta — crie a primeira demanda pra os agentes começarem.
          </p>
          <Button onClick={() => navigate(squads[0]?.id ? `/squads/${squads[0].id}` : '/squads')}>
            <Plus className="mr-2 h-4 w-4" />
            Criar primeira demanda
          </Button>
        </section>
      )}

      <section className="border-t pt-6 flex flex-wrap gap-2">
        <Button
          variant="outline"
          onClick={() => squads.length === 1
            ? navigate(`/squads/${squads[0].id}`)
            : navigate('/squads')}
        >
          {squads.length === 1 ? 'Abrir minha squad' : 'Ver squads'}
        </Button>
        <Button variant="outline" onClick={() => navigate('/setup?new=1')}>
          <Plus className="mr-2 h-4 w-4" />
          Nova squad
        </Button>
        <Button variant="ghost" onClick={() => navigate('/cost')}>
          Ver custos detalhados
        </Button>
      </section>
    </div>
  );
}


function AttentionCard({ task, onClick }: { task: TaskListItem; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="w-full rounded-md border border-destructive/30 bg-destructive/5 p-3 text-left text-sm hover:border-destructive/50"
    >
      <div className="flex items-start gap-2">
        <AlertCircle className="mt-0.5 h-4 w-4 flex-shrink-0 text-destructive" />
        <div className="flex-1">
          <p className="font-medium">
            🔴 Task falhou: {task.jira_issue_key ?? task.id.slice(0, 8)}
          </p>
          <p className="text-xs text-muted-foreground mt-0.5">
            {task.title.slice(0, 80)} — {task.squad_slug ?? '?'}
          </p>
        </div>
      </div>
    </button>
  );
}


function TaskRow({ task, onClick }: { task: TaskListItem; onClick: () => void }) {
  return (
    <li>
      <button
        type="button"
        onClick={onClick}
        className="w-full rounded-md border bg-muted/20 px-3 py-2 text-left text-sm hover:bg-muted/40"
      >
        <div className="flex items-center gap-2">
          <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" />
          <span className="font-medium">{task.jira_issue_key ?? task.id.slice(0, 8)}</span>
          {task.step_label && (
            <span className="text-xs text-muted-foreground truncate">
              · {task.step_label.slice(0, 60)}
            </span>
          )}
          <span className="ml-auto text-xs text-muted-foreground">
            US$ {task.cost_usd.toFixed(2)}
          </span>
        </div>
      </button>
    </li>
  );
}


function RecentRow({ task, onClick }: { task: TaskListItem; onClick: () => void }) {
  const icon = task.status === 'done'
    ? '✓'
    : task.status === 'failed'
      ? '✗'
      : task.status === 'cancelled'
        ? '◌'
        : '🔄';
  const since = task.closed_at ?? task.created_at;
  return (
    <li>
      <button
        type="button"
        onClick={onClick}
        className="w-full text-left text-xs text-muted-foreground hover:text-foreground"
      >
        {icon} {task.jira_issue_key ?? task.id.slice(0, 8)} ·{' '}
        {task.title.slice(0, 60)} ·{' '}
        {since && formatRelative(since)}
      </button>
    </li>
  );
}


function Kpi({
  icon, title, value, delta, deltaLabel, onClickDetail, detailLabel, invert,
}: {
  icon: React.ReactNode;
  title: string;
  value: string;
  delta?: number | null;
  deltaLabel?: string;
  onClickDetail?: () => void;
  detailLabel?: string;
  invert?: boolean;  // pra custo, ↑ é ruim
}) {
  return (
    <Card>
      <CardContent className="p-4 space-y-2">
        <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
          {icon}
          {title}
        </div>
        <div className="text-2xl font-semibold">{value}</div>
        {delta != null && (
          <div className="flex items-center gap-1 text-xs">
            {delta === 0 ? (
              <span className="text-muted-foreground">sem mudança {deltaLabel}</span>
            ) : (
              <>
                {delta > 0 ? (
                  <TrendingUp className={`h-3 w-3 ${invert ? 'text-amber-600' : 'text-emerald-600'}`} />
                ) : (
                  <TrendingDown className={`h-3 w-3 ${invert ? 'text-emerald-600' : 'text-amber-600'}`} />
                )}
                <span className="text-muted-foreground">
                  {typeof delta === 'number' && Math.abs(delta) > 1
                    ? `${delta > 0 ? '+' : ''}${delta.toFixed(0)}${title === 'Concluídas' ? '' : '%'}`
                    : ''}
                  {' '}
                  {deltaLabel}
                </span>
              </>
            )}
          </div>
        )}
        {onClickDetail && (
          <Button
            variant="ghost"
            size="sm"
            className="h-7 px-2 text-xs"
            onClick={onClickDetail}
          >
            {detailLabel ?? 'Detalhar'} →
          </Button>
        )}
      </CardContent>
    </Card>
  );
}


function formatRelative(iso: string): string {
  const t = new Date(iso).getTime();
  const diff = Date.now() - t;
  if (diff < 60_000) return 'agora';
  if (diff < 3_600_000) return `há ${Math.floor(diff / 60_000)}min`;
  if (diff < 86_400_000) return `há ${Math.floor(diff / 3_600_000)}h`;
  return `há ${Math.floor(diff / 86_400_000)}d`;
}

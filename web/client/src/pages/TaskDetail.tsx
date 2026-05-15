import { useNavigate, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  ArrowLeft, ExternalLink, Loader2, CheckCircle2, XCircle, Circle,
  AlertCircle,
} from 'lucide-react';

import { useClientId } from '@/lib/use-client-id';
import {
  fetchTaskDetail, type TaskTimelineEvent,
} from '@/lib/api';
import { formatApiError } from '@/lib/utils';
import { Button } from '@/components/ui/button';


interface JiraEvent {
  ts: string;
  kind: string;
  author: string;
  body: string;
}


/**
 * Detalhe de uma task (D-05 — versão S-2).
 *
 * Mostra: identidade + status + timeline derivada de scan_progress + custo.
 * Não inclui ainda (S-7): bloco "Demanda original do Jira", comentários
 * humanos do Jira inline, caixa "Adicionar instrução" sincronizada.
 *
 * Estes itens são TODO documentado pra quando S-7 (integração Jira)
 * for implementado.
 */
export default function TaskDetailPage() {
  const navigate = useNavigate();
  const { taskId } = useParams<{ taskId: string }>();
  const clientId = useClientId();

  const taskQuery = useQuery({
    queryKey: ['task-detail', clientId, taskId],
    queryFn: () => fetchTaskDetail(clientId, taskId!),
    enabled: Boolean(taskId),
    refetchInterval: (q) => {
      const status = q.state.data?.status;
      if (!status) return 5000;
      if (status === 'in_progress' || status === 'pending') return 5000;
      return false;
    },
  });

  if (taskQuery.isLoading) {
    return (
      <div className="mx-auto max-w-3xl py-12 px-6 text-center text-sm text-muted-foreground">
        <Loader2 className="mx-auto h-6 w-6 animate-spin" />
      </div>
    );
  }

  if (taskQuery.isError || !taskQuery.data) {
    return (
      <div className="mx-auto max-w-3xl py-12 px-6">
        <p className="text-sm text-destructive">
          {formatApiError(taskQuery.error, 'Erro carregando task.')}
        </p>
      </div>
    );
  }

  const t = taskQuery.data;

  return (
    <div className="mx-auto max-w-3xl py-12 px-6 space-y-8">
      <Button variant="ghost" size="sm" onClick={() => navigate('/tasks')} className="-ml-2">
        <ArrowLeft className="mr-1 h-3 w-3" />
        Todas as tasks
      </Button>

      <header className="space-y-2">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="font-mono text-xs text-muted-foreground">
              {t.jira_issue_key ?? t.id.slice(0, 8)}
            </p>
            <h1 className="text-xl font-semibold tracking-tight mt-1">
              {t.title}
            </h1>
          </div>
          <TaskStatusBig status={t.status} />
        </div>
        <p className="text-xs text-muted-foreground">
          Squad: {t.squad_slug ?? '—'} ·
          Criada: {new Date(t.created_at).toLocaleString('pt-BR')} ·
          Atualizada: {new Date(t.updated_at).toLocaleString('pt-BR')}
        </p>
        <div className="flex gap-2 pt-2">
          {t.pr_url && (
            <Button variant="outline" size="sm" asChild>
              <a href={t.pr_url} target="_blank" rel="noopener noreferrer">
                Ver PR
                <ExternalLink className="ml-1 h-3 w-3" />
              </a>
            </Button>
          )}
          {t.jira_workspace_url && t.jira_issue_key && (
            <Button variant="outline" size="sm" asChild>
              <a
                href={`${t.jira_workspace_url.replace(/\/$/, '')}/browse/${t.jira_issue_key}`}
                target="_blank"
                rel="noopener noreferrer"
              >
                Ver no Jira
                <ExternalLink className="ml-1 h-3 w-3" />
              </a>
            </Button>
          )}
        </div>
      </header>

      <section className="rounded-md border bg-muted/30 p-4 space-y-1 text-xs">
        <p>
          <span className="text-muted-foreground">Custo total:</span>{' '}
          <strong>US$ {t.cost_usd.toFixed(4)}</strong>
        </p>
        <p>
          <span className="text-muted-foreground">API calls:</span>{' '}
          {t.api_calls_count}
        </p>
        {t.outcome_status && (
          <p>
            <span className="text-muted-foreground">Outcome:</span>{' '}
            {t.outcome_status} ({t.outcome_iterations} iterações)
          </p>
        )}
        {t.anthropic_session_id && (
          <p className="font-mono text-[10px] text-muted-foreground">
            session: {t.anthropic_session_id}
          </p>
        )}
      </section>

      {t.step_label && t.status === 'in_progress' && (
        <section className="rounded-md border border-primary/30 bg-primary/5 p-4">
          <p className="text-sm">
            <strong>Etapa atual:</strong> {t.current_step}
          </p>
          <p className="text-xs text-muted-foreground mt-1">{t.step_label}</p>
        </section>
      )}

      <section className="space-y-3">
        <h2 className="text-sm font-medium">Timeline</h2>
        {t.timeline.length === 0 ? (
          <p className="text-xs text-muted-foreground">
            Sem eventos registrados ainda.
          </p>
        ) : (
          <ol className="space-y-3">
            {t.timeline.map((ev, i) => (
              <TimelineRow key={i} event={ev} />
            ))}
          </ol>
        )}
      </section>

      {/* S-7: eventos vindos do Jira via webhook bidirecional */}
      {(t.scan_progress?.jira_events as JiraEvent[] | undefined)?.length ? (
        <section className="space-y-2">
          <h2 className="text-sm font-medium">Comentários do Jira</h2>
          <ol className="space-y-2">
            {(t.scan_progress!.jira_events as JiraEvent[]).slice().reverse().map((ev, i) => (
              <li key={i} className="rounded-md border bg-muted/10 px-3 py-2 text-sm">
                <p className="text-xs text-muted-foreground">
                  <span className="font-medium text-foreground">{ev.author}</span>
                  {' · '}
                  {ev.kind === 'transition' ? 'mudou status' : 'comentou'}
                  {' · '}
                  {new Date(ev.ts).toLocaleString('pt-BR')}
                </p>
                <p className="mt-1 whitespace-pre-wrap">{ev.body}</p>
              </li>
            ))}
          </ol>
        </section>
      ) : null}

      {t.scan_progress && Object.keys(t.scan_progress).length > 0 && (
        <section className="space-y-2">
          <h2 className="text-sm font-medium">Detalhes da execução</h2>
          <div className="rounded-md border bg-muted/20 p-3 text-xs font-mono whitespace-pre-wrap">
            {JSON.stringify(t.scan_progress, null, 2)}
          </div>
        </section>
      )}
    </div>
  );
}


function TimelineRow({ event }: { event: TaskTimelineEvent }) {
  const icon = event.kind === 'completed'
    ? <CheckCircle2 className="h-4 w-4 text-emerald-600 dark:text-emerald-400" />
    : event.kind === 'failed' || event.kind === 'cancelled'
      ? <XCircle className="h-4 w-4 text-destructive" />
      : event.kind === 'step_current'
        ? <Loader2 className="h-4 w-4 animate-spin text-primary" />
        : <Circle className="h-4 w-4 text-muted-foreground/50" />;

  return (
    <li className="flex gap-3">
      <div className="pt-0.5">{icon}</div>
      <div className="flex-1">
        <p className="text-sm">{event.label}</p>
        <p className="text-xs text-muted-foreground">
          {new Date(event.timestamp).toLocaleString('pt-BR')}
        </p>
        {Object.keys(event.detail).length > 0 && (
          <p className="text-xs text-muted-foreground mt-0.5">
            {Object.entries(event.detail).map(([k, v]) =>
              v ? `${k}=${String(v).slice(0, 40)}` : null,
            ).filter(Boolean).join(' · ')}
          </p>
        )}
      </div>
    </li>
  );
}


function TaskStatusBig({ status }: { status: string }) {
  const config: Record<string, { label: string; cls: string; icon: React.ReactNode }> = {
    in_progress: {
      label: 'Em curso',
      cls: 'bg-blue-500/10 text-blue-700 dark:text-blue-400',
      icon: <Loader2 className="h-3 w-3 animate-spin" />,
    },
    done: {
      label: 'Concluída',
      cls: 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-400',
      icon: <CheckCircle2 className="h-3 w-3" />,
    },
    failed: {
      label: 'Falhou',
      cls: 'bg-destructive/10 text-destructive',
      icon: <AlertCircle className="h-3 w-3" />,
    },
    cancelled: {
      label: 'Cancelada',
      cls: 'bg-muted text-muted-foreground',
      icon: <XCircle className="h-3 w-3" />,
    },
  };
  const c = config[status] ?? { label: status, cls: 'bg-muted', icon: null };
  return (
    <span className={`flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ${c.cls}`}>
      {c.icon}
      {c.label}
    </span>
  );
}

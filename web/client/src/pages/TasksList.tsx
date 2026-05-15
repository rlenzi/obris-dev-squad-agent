import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ChevronLeft, ChevronRight, Loader2, X } from 'lucide-react';

import { useClientId } from '@/lib/use-client-id';
import {
  fetchTasks, fetchSquadsForClient,
  type TaskStatusType, type TasksListFilters,
} from '@/lib/api';
import { formatApiError } from '@/lib/utils';
import { Button } from '@/components/ui/button';

const PAGE_SIZE = 50;
const STATUS_OPTIONS: { value: TaskStatusType; label: string }[] = [
  { value: 'in_progress', label: 'Em curso' },
  { value: 'done', label: 'Concluída' },
  { value: 'failed', label: 'Falhou' },
  { value: 'cancelled', label: 'Cancelada' },
  { value: 'pending', label: 'Pendente' },
  { value: 'blocked', label: 'Bloqueada' },
];


export default function TasksListPage() {
  const navigate = useNavigate();
  const clientId = useClientId();

  const [page, setPage] = useState(0);
  const [filterStatus, setFilterStatus] = useState<TaskStatusType | ''>('');
  const [filterSquad, setFilterSquad] = useState<string>('');

  const squadsQuery = useQuery({
    queryKey: ['squads', clientId],
    queryFn: () => fetchSquadsForClient(clientId),
  });

  const filters: TasksListFilters = {
    offset: page * PAGE_SIZE,
    limit: PAGE_SIZE,
    status: filterStatus || undefined,
    squad_id: filterSquad || undefined,
  };

  const tasksQuery = useQuery({
    queryKey: ['tasks', clientId, filters],
    queryFn: () => fetchTasks(clientId, filters),
  });

  return (
    <div className="mx-auto max-w-5xl py-12 px-6 space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Tasks</h1>
        <p className="text-sm text-muted-foreground">
          Todas as demandas do seu tenant — em curso, concluídas, falhas.
        </p>
      </header>

      <div className="flex flex-wrap items-center gap-2">
        <FilterDropdown
          label="Status"
          value={filterStatus}
          options={STATUS_OPTIONS.map(o => ({ value: o.value, label: o.label }))}
          onChange={(v) => {
            setFilterStatus(v as TaskStatusType | '');
            setPage(0);
          }}
        />
        <FilterDropdown
          label="Squad"
          value={filterSquad}
          options={(squadsQuery.data ?? []).map(s => ({ value: s.id, label: s.name }))}
          onChange={(v) => {
            setFilterSquad(v);
            setPage(0);
          }}
        />
        {(filterStatus || filterSquad) && (
          <Button
            variant="ghost"
            size="sm"
            className="text-xs"
            onClick={() => {
              setFilterStatus('');
              setFilterSquad('');
              setPage(0);
            }}
          >
            <X className="mr-1 h-3 w-3" />
            Limpar filtros
          </Button>
        )}
      </div>

      {tasksQuery.isLoading ? (
        <div className="text-center text-sm text-muted-foreground py-12">
          <Loader2 className="mx-auto h-6 w-6 animate-spin" />
          <p className="mt-3">Carregando…</p>
        </div>
      ) : tasksQuery.isError ? (
        <p className="text-sm text-destructive">
          {formatApiError(tasksQuery.error, 'Erro carregando tasks.')}
        </p>
      ) : tasksQuery.data && tasksQuery.data.items.length === 0 ? (
        <div className="rounded-md border border-dashed p-8 text-center">
          <p className="text-sm text-muted-foreground">
            {filterStatus || filterSquad
              ? 'Nada bate seus filtros · ajuste ou limpe.'
              : 'Nenhuma task ainda. Crie a primeira demanda na sua squad.'}
          </p>
        </div>
      ) : (
        <>
          <div className="rounded-md border overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-muted/30 text-xs text-muted-foreground">
                <tr>
                  <th className="text-left px-3 py-2">Issue</th>
                  <th className="text-left px-3 py-2">Título</th>
                  <th className="text-left px-3 py-2">Squad</th>
                  <th className="text-left px-3 py-2">Status</th>
                  <th className="text-left px-3 py-2">Criada</th>
                  <th className="text-right px-3 py-2">Custo</th>
                </tr>
              </thead>
              <tbody>
                {tasksQuery.data?.items.map(t => (
                  <tr
                    key={t.id}
                    onClick={() => navigate(`/tasks/${t.id}`)}
                    className="border-t cursor-pointer hover:bg-muted/30"
                  >
                    <td className="px-3 py-2 font-mono text-xs">
                      {t.jira_issue_key ?? t.id.slice(0, 8)}
                    </td>
                    <td className="px-3 py-2">{t.title.slice(0, 60)}</td>
                    <td className="px-3 py-2 text-xs text-muted-foreground">
                      {t.squad_slug ?? '—'}
                    </td>
                    <td className="px-3 py-2">
                      <StatusBadge status={t.status} />
                    </td>
                    <td className="px-3 py-2 text-xs text-muted-foreground">
                      {new Date(t.created_at).toLocaleString('pt-BR', {
                        day: '2-digit', month: '2-digit',
                        hour: '2-digit', minute: '2-digit',
                      })}
                    </td>
                    <td className="px-3 py-2 text-right text-xs">
                      US$ {t.cost_usd.toFixed(2)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span>
              Mostrando {tasksQuery.data!.offset + 1}–
              {Math.min(
                tasksQuery.data!.offset + tasksQuery.data!.items.length,
                tasksQuery.data!.total,
              )}
              {' '}de {tasksQuery.data!.total}
            </span>
            <div className="flex gap-1">
              <Button
                variant="outline"
                size="sm"
                disabled={page === 0}
                onClick={() => setPage(p => Math.max(0, p - 1))}
              >
                <ChevronLeft className="h-3 w-3" />
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={
                  (page + 1) * PAGE_SIZE >= (tasksQuery.data?.total ?? 0)
                }
                onClick={() => setPage(p => p + 1)}
              >
                <ChevronRight className="h-3 w-3" />
              </Button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}


function FilterDropdown({
  label, value, options, onChange,
}: {
  label: string;
  value: string;
  options: { value: string; label: string }[];
  onChange: (v: string) => void;
}) {
  return (
    <label className="flex items-center gap-1.5 text-xs">
      <span className="text-muted-foreground">{label}:</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="rounded-md border bg-background px-2 py-1 text-xs"
      >
        <option value="">Todos</option>
        {options.map(o => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
    </label>
  );
}


function StatusBadge({ status }: { status: TaskStatusType }) {
  const config: Record<TaskStatusType, { label: string; cls: string }> = {
    pending: { label: 'Pendente', cls: 'bg-muted text-foreground/70' },
    in_progress: { label: 'Em curso', cls: 'bg-blue-500/10 text-blue-700 dark:text-blue-400' },
    blocked: { label: 'Bloqueada', cls: 'bg-amber-500/10 text-amber-700 dark:text-amber-400' },
    done: { label: 'Concluída', cls: 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-400' },
    cancelled: { label: 'Cancelada', cls: 'bg-muted text-muted-foreground' },
    failed: { label: 'Falhou', cls: 'bg-destructive/10 text-destructive' },
  };
  const c = config[status] ?? config.pending;
  return (
    <span className={`inline-block rounded-full px-2 py-0.5 text-[10px] font-medium ${c.cls}`}>
      {c.label}
    </span>
  );
}

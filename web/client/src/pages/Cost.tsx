import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { DollarSign, Calendar } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/lib/auth';
import {
  fetchClientCost, fetchDailyCostSeries, fetchTopTasksByCost,
  type DailyCostPoint, type TopTaskCost,
} from '@/lib/api';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';

function getPeriodPreset(preset: 'current' | 'last' | 'last30'): {
  start: string;
  end: string;
  label: string;
} {
  const now = new Date();
  if (preset === 'current') {
    const start = new Date(now.getFullYear(), now.getMonth(), 1);
    return {
      start: start.toISOString().slice(0, 10),
      end: now.toISOString().slice(0, 10),
      label: 'Mês corrente',
    };
  }
  if (preset === 'last') {
    const start = new Date(now.getFullYear(), now.getMonth() - 1, 1);
    const end = new Date(now.getFullYear(), now.getMonth(), 0);
    return {
      start: start.toISOString().slice(0, 10),
      end: end.toISOString().slice(0, 10),
      label: 'Mês passado',
    };
  }
  const start = new Date(now);
  start.setDate(start.getDate() - 30);
  return {
    start: start.toISOString().slice(0, 10),
    end: now.toISOString().slice(0, 10),
    label: 'Últimos 30 dias',
  };
}

export default function ClientCostPage() {
  const { me } = useAuth();
  const membership = me?.memberships?.[0];
  const clientId = membership?.client_id;
  const [preset, setPreset] = useState<'current' | 'last' | 'last30'>('current');
  const period = getPeriodPreset(preset);

  const costQuery = useQuery({
    queryKey: ['client-cost', clientId, period.start, period.end],
    queryFn: () =>
      fetchClientCost(clientId!, {
        period_start: period.start,
        period_end: period.end,
      }),
    enabled: Boolean(clientId),
  });

  const breakdown = costQuery.data?.breakdown;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="grid size-14 place-items-center rounded-lg bg-brand-500/10">
            <DollarSign className="size-7 text-brand-500" />
          </div>
          <div>
            <h1 className="text-3xl font-semibold tracking-tight">Custos</h1>
            <p className="text-muted-foreground">
              Consumo de API e cálculo do plano do tenant {membership?.client_name}
            </p>
          </div>
        </div>
        <div className="flex gap-2">
          <Button
            variant={preset === 'current' ? 'default' : 'outline'}
            size="sm"
            onClick={() => setPreset('current')}
          >
            Mês corrente
          </Button>
          <Button
            variant={preset === 'last' ? 'default' : 'outline'}
            size="sm"
            onClick={() => setPreset('last')}
          >
            Mês passado
          </Button>
          <Button
            variant={preset === 'last30' ? 'default' : 'outline'}
            size="sm"
            onClick={() => setPreset('last30')}
          >
            Últimos 30d
          </Button>
        </div>
      </div>

      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <Calendar className="size-3.5" />
        Período: {period.start} → {period.end}
      </div>

      {costQuery.isLoading && (
        <p className="text-sm text-muted-foreground">Carregando…</p>
      )}
      {costQuery.isError && (
        <p className="text-sm text-destructive">
          Erro: {(costQuery.error as Error)?.message}
        </p>
      )}

      {breakdown && (
        <>
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
            <StatCard
              label="Tasks no período"
              value={String(breakdown.num_tasks)}
            />
            <StatCard
              label="Chamadas API"
              value={String(breakdown.num_calls)}
            />
            <StatCard
              label="Tokens (in/out)"
              value={`${fmt(breakdown.total_input_tokens)}/${fmt(breakdown.total_output_tokens)}`}
            />
            <StatCard
              label="USD direto"
              value={fmtUSD(Number(breakdown.direct_cost_usd))}
            />
          </div>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Breakdown do plano</CardTitle>
              <CardDescription>
                Cálculo aplicando a cotação USD/BRL + overhead de infra + custo fixo por task
              </CardDescription>
            </CardHeader>
            <CardContent>
              <table className="w-full text-sm">
                <tbody>
                  <Row label="Direto (USD)" value={fmtUSD(Number(breakdown.direct_cost_usd))} />
                  <Row label="Direto (BRL)" value={fmtBRL(Number(breakdown.direct_cost_brl))} />
                  <Row
                    label="Infra overhead (BRL)"
                    value={fmtBRL(Number(breakdown.infra_overhead_brl))}
                  />
                  <Row
                    label="Fixed por task (BRL)"
                    value={fmtBRL(Number(breakdown.fixed_overhead_brl))}
                  />
                  <Row
                    label="TOTAL real (BRL)"
                    value={fmtBRL(Number(breakdown.full_cost_brl))}
                    emphasis
                  />
                </tbody>
              </table>
              <p className="mt-3 text-xs text-muted-foreground">
                O valor faturável aplica markup adicional conforme seu plano de billing —
                consulte o admin do tenant ou seu contrato.
              </p>
            </CardContent>
          </Card>

          <DailySeriesChart
            clientId={clientId!}
            start={period.start}
            end={period.end}
          />

          <TopTasksTable
            clientId={clientId!}
            start={period.start}
            end={period.end}
          />
        </>
      )}
    </div>
  );
}


function DailySeriesChart({
  clientId, start, end,
}: { clientId: string; start: string; end: string }) {
  const q = useQuery({
    queryKey: ['cost-daily', clientId, start, end],
    queryFn: () => fetchDailyCostSeries(clientId, { period_start: start, period_end: end }),
  });
  const items = q.data?.items ?? [];
  if (items.length === 0) return null;
  const maxCost = Math.max(...items.map(i => i.cost_usd), 0.01);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Custo diário</CardTitle>
        <CardDescription>
          Distribuição do consumo USD direto por dia
        </CardDescription>
      </CardHeader>
      <CardContent>
        <DailyBars items={items} maxCost={maxCost} />
      </CardContent>
    </Card>
  );
}


function DailyBars({ items, maxCost }: { items: DailyCostPoint[]; maxCost: number }) {
  // Bar chart SVG inline (sem chart lib). Cada barra = 1 dia.
  const width = 600;
  const height = 120;
  const barWidth = Math.max(2, Math.floor(width / Math.max(items.length, 1)) - 2);
  return (
    <svg viewBox={`0 0 ${width} ${height + 20}`} className="w-full">
      {items.map((p, i) => {
        const h = (p.cost_usd / maxCost) * height;
        return (
          <g key={p.date}>
            <rect
              x={i * (barWidth + 2)}
              y={height - h}
              width={barWidth}
              height={h}
              fill="currentColor"
              className="text-primary"
              opacity={0.8}
            >
              <title>{p.date}: US$ {p.cost_usd.toFixed(4)}</title>
            </rect>
          </g>
        );
      })}
      <text x={0} y={height + 14} className="text-[10px] fill-muted-foreground">
        {items[0]?.date}
      </text>
      <text
        x={width}
        y={height + 14}
        textAnchor="end"
        className="text-[10px] fill-muted-foreground"
      >
        {items[items.length - 1]?.date}
      </text>
    </svg>
  );
}


function TopTasksTable({
  clientId, start, end,
}: { clientId: string; start: string; end: string }) {
  const navigate = useNavigate();
  const q = useQuery({
    queryKey: ['cost-top-tasks', clientId, start, end],
    queryFn: () => fetchTopTasksByCost(clientId, {
      period_start: start, period_end: end, limit: 20,
    }),
  });
  const items = q.data?.items ?? [];

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Top 20 tasks mais caras</CardTitle>
        <CardDescription>
          Click numa linha pra ver o detalhe
        </CardDescription>
      </CardHeader>
      <CardContent>
        {items.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Nenhuma task no período.
          </p>
        ) : (
          <div className="overflow-hidden rounded-md border">
            <table className="w-full text-sm">
              <thead className="bg-muted/30 text-xs text-muted-foreground">
                <tr>
                  <th className="px-3 py-2 text-left">Issue</th>
                  <th className="px-3 py-2 text-left">Título</th>
                  <th className="px-3 py-2 text-right">API calls</th>
                  <th className="px-3 py-2 text-right">Custo USD</th>
                </tr>
              </thead>
              <tbody>
                {items.map((t: TopTaskCost) => (
                  <tr
                    key={t.task_id}
                    onClick={() => navigate(`/tasks/${t.task_id}`)}
                    className="cursor-pointer border-t hover:bg-muted/30"
                  >
                    <td className="px-3 py-2 font-mono text-xs">
                      {t.jira_issue_key ?? t.task_id.slice(0, 8)}
                    </td>
                    <td className="px-3 py-2">{t.title.slice(0, 60)}</td>
                    <td className="px-3 py-2 text-right text-xs">
                      {t.api_calls_count}
                    </td>
                    <td className="px-3 py-2 text-right font-mono text-xs">
                      ${t.cost_usd.toFixed(4)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <Card>
      <CardContent className="py-4">
        <div className="text-xs text-muted-foreground">{label}</div>
        <div className="mt-1 font-mono text-2xl font-semibold">{value}</div>
      </CardContent>
    </Card>
  );
}

function Row({
  label,
  value,
  emphasis,
}: {
  label: string;
  value: string;
  emphasis?: boolean;
}) {
  return (
    <tr className={emphasis ? 'border-t' : ''}>
      <td className={'py-1.5 pr-3 ' + (emphasis ? 'font-medium' : 'text-muted-foreground')}>
        {label}
      </td>
      <td
        className={
          'py-1.5 text-right font-mono ' +
          (emphasis ? 'font-semibold text-brand-500' : '')
        }
      >
        {value}
      </td>
    </tr>
  );
}

function fmt(n: number): string {
  return n.toLocaleString('pt-BR');
}
function fmtUSD(n: number): string {
  return isNaN(n)
    ? '—'
    : n.toLocaleString('en-US', {
        style: 'currency',
        currency: 'USD',
        minimumFractionDigits: 4,
      });
}
function fmtBRL(n: number): string {
  return isNaN(n)
    ? '—'
    : n.toLocaleString('pt-BR', {
        style: 'currency',
        currency: 'BRL',
        minimumFractionDigits: 2,
      });
}

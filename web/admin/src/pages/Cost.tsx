import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { ArrowRight, DollarSign, TrendingUp } from 'lucide-react';
import {
  fetchClientCost,
  fetchCostByClient,
  type CostBreakdownResponse,
} from '@/lib/api';
import { Badge } from '@/components/ui/badge';
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
  // last30
  const start = new Date(now);
  start.setDate(start.getDate() - 30);
  return {
    start: start.toISOString().slice(0, 10),
    end: now.toISOString().slice(0, 10),
    label: 'Últimos 30 dias',
  };
}

export default function CostPage() {
  const [preset, setPreset] = useState<'current' | 'last' | 'last30'>('current');
  const period = getPeriodPreset(preset);

  const rankingQuery = useQuery({
    queryKey: ['cost-by-client', period.start, period.end],
    queryFn: () =>
      fetchCostByClient({
        period_start: period.start,
        period_end: period.end,
        limit: 50,
      }),
  });

  const items = rankingQuery.data ?? [];
  const totalUsd = items.reduce(
    (acc, i) => acc + Number(i.breakdown.direct_cost_usd),
    0,
  );
  const totalBrl = items.reduce(
    (acc, i) => acc + Number(i.breakdown.full_cost_brl),
    0,
  );

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">Custos</h1>
          <p className="text-muted-foreground">
            Consumo de API + cálculo do plano (USD → BRL + infra + faturável)
          </p>
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

      <div className="text-xs text-muted-foreground">
        Período: {period.start} → {period.end}
      </div>

      {/* Totais agregados */}
      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardContent className="flex items-center gap-3 py-4">
            <div className="grid size-10 place-items-center rounded-md bg-brand-500/10">
              <DollarSign className="size-5 text-brand-500" />
            </div>
            <div>
              <div className="text-xs text-muted-foreground">Total USD direto</div>
              <div className="font-mono text-xl">{fmtUSD(totalUsd)}</div>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="flex items-center gap-3 py-4">
            <div className="grid size-10 place-items-center rounded-md bg-brand-500/10">
              <TrendingUp className="size-5 text-brand-500" />
            </div>
            <div>
              <div className="text-xs text-muted-foreground">Total BRL (custo real)</div>
              <div className="font-mono text-xl">{fmtBRL(totalBrl)}</div>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="flex items-center gap-3 py-4">
            <div className="grid size-10 place-items-center rounded-md bg-brand-500/10">
              <DollarSign className="size-5 text-brand-500" />
            </div>
            <div>
              <div className="text-xs text-muted-foreground">Clientes ativos</div>
              <div className="font-mono text-xl">{items.length}</div>
            </div>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Ranking por cliente</CardTitle>
          <CardDescription>Quem gastou mais no período selecionado</CardDescription>
        </CardHeader>
        <CardContent>
          {rankingQuery.isLoading && (
            <p className="text-sm text-muted-foreground">Carregando…</p>
          )}
          {rankingQuery.isError && (
            <p className="text-sm text-destructive">
              Erro ao carregar: {(rankingQuery.error as Error)?.message}
            </p>
          )}
          {items.length === 0 && !rankingQuery.isLoading && (
            <p className="text-sm italic text-muted-foreground">
              Sem dados de custo no período selecionado.
            </p>
          )}
          {items.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-xs uppercase text-muted-foreground">
                    <th className="py-2 pr-3 font-medium">#</th>
                    <th className="py-2 pr-3 font-medium">Cliente</th>
                    <th className="py-2 pr-3 text-right font-medium">Tasks</th>
                    <th className="py-2 pr-3 text-right font-medium">Chamadas</th>
                    <th className="py-2 pr-3 text-right font-medium">USD direto</th>
                    <th className="py-2 pr-3 text-right font-medium">BRL real</th>
                    <th className="py-2 font-medium" />
                  </tr>
                </thead>
                <tbody>
                  {items.map((it, idx) => (
                    <RankingRow key={it.client_id} item={it} rank={idx + 1} />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      <ClientDetail period={period} items={items} />
    </div>
  );
}

function RankingRow({
  item,
  rank,
}: {
  item: { client_id: string; client_slug: string; client_name: string; breakdown: CostBreakdownResponse };
  rank: number;
}) {
  const b = item.breakdown;
  return (
    <tr className="border-b last:border-b-0 hover:bg-muted/40">
      <td className="py-2 pr-3 font-mono text-xs text-muted-foreground">{rank}</td>
      <td className="py-2 pr-3">
        <Link
          to={`/clients/${item.client_id}`}
          className="text-brand-500 hover:underline"
        >
          {item.client_name}
        </Link>
        <span className="ml-2 text-xs text-muted-foreground">({item.client_slug})</span>
      </td>
      <td className="py-2 pr-3 text-right font-mono text-xs">{b.num_tasks}</td>
      <td className="py-2 pr-3 text-right font-mono text-xs">{b.num_calls}</td>
      <td className="py-2 pr-3 text-right font-mono text-xs">{fmtUSD(Number(b.direct_cost_usd))}</td>
      <td className="py-2 pr-3 text-right font-mono text-xs">{fmtBRL(Number(b.full_cost_brl))}</td>
      <td className="py-2">
        <Link to={`/clients/${item.client_id}`}>
          <ArrowRight className="size-4 text-muted-foreground" />
        </Link>
      </td>
    </tr>
  );
}

function ClientDetail({
  period,
  items,
}: {
  period: { start: string; end: string };
  items: { client_id: string; client_name: string }[];
}) {
  const [selectedClientId, setSelectedClientId] = useState<string | null>(
    items[0]?.client_id ?? null,
  );

  // Re-seleciona se a lista mudou e o selecionado sumiu
  if (
    selectedClientId &&
    items.length > 0 &&
    !items.find((i) => i.client_id === selectedClientId)
  ) {
    setSelectedClientId(items[0].client_id);
  }

  const detailQuery = useQuery({
    queryKey: ['client-cost', selectedClientId, period.start, period.end],
    queryFn: () =>
      fetchClientCost(selectedClientId!, {
        period_start: period.start,
        period_end: period.end,
      }),
    enabled: Boolean(selectedClientId),
  });

  if (items.length === 0) return null;

  const cost = detailQuery.data;
  const b = cost?.breakdown;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Detalhamento por cliente</CardTitle>
        <CardDescription>Breakdown do plano: direto → BRL → infra → faturável</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap gap-2">
          {items.map((c) => (
            <Badge
              key={c.client_id}
              variant={c.client_id === selectedClientId ? 'default' : 'outline'}
              className="cursor-pointer"
              onClick={() => setSelectedClientId(c.client_id)}
            >
              {c.client_name}
            </Badge>
          ))}
        </div>

        {detailQuery.isLoading && (
          <p className="text-sm text-muted-foreground">Carregando…</p>
        )}
        {b && (
          <table className="w-full text-sm">
            <tbody>
              <BreakdownRow label="Direto (USD)" value={fmtUSD(Number(b.direct_cost_usd))} />
              <BreakdownRow label="Direto (BRL)" value={fmtBRL(Number(b.direct_cost_brl))} />
              <BreakdownRow label="Infra overhead (BRL)" value={fmtBRL(Number(b.infra_overhead_brl))} />
              <BreakdownRow label="Fixed/task (BRL)" value={fmtBRL(Number(b.fixed_overhead_brl))} />
              <BreakdownRow label="TOTAL real (BRL)" value={fmtBRL(Number(b.full_cost_brl))} emphasis />
            </tbody>
          </table>
        )}
      </CardContent>
    </Card>
  );
}

function BreakdownRow({
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
      <td className={'py-1.5 text-right font-mono ' + (emphasis ? 'font-semibold text-brand-500' : '')}>
        {value}
      </td>
    </tr>
  );
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

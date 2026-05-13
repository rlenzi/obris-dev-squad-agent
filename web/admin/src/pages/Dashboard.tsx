import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { Building2, Coins, Receipt } from 'lucide-react';
import { fetchClients, fetchCostByClient } from '@/lib/api';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { formatBRL, formatNumber, formatUSD } from '@/lib/utils';

export default function DashboardPage() {
  const navigate = useNavigate();

  const clientsQuery = useQuery({ queryKey: ['clients'], queryFn: fetchClients });
  const costQuery = useQuery({
    queryKey: ['cost-by-client'],
    queryFn: () => fetchCostByClient(),
  });

  const totalDirectUSD = (costQuery.data ?? []).reduce(
    (acc, c) => acc + parseFloat(c.breakdown.direct_cost_usd),
    0,
  );
  const totalFullBRL = (costQuery.data ?? []).reduce(
    (acc, c) => acc + parseFloat(c.breakdown.full_cost_brl),
    0,
  );
  const totalCalls = (costQuery.data ?? []).reduce(
    (acc, c) => acc + c.breakdown.num_calls,
    0,
  );

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight">Dashboard</h1>
        <p className="text-muted-foreground">
          Visão geral de clientes, consumo e custo agregado nos últimos 30 dias.
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Custo total (BRL)</CardTitle>
            <Coins className="size-4 text-brand-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-semibold tabular-nums">{formatBRL(totalFullBRL)}</div>
            <p className="text-xs text-muted-foreground mt-1">
              Direto + overhead infra + fixo
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Custo direto APIs (USD)</CardTitle>
            <Receipt className="size-4 text-brand-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-semibold tabular-nums">{formatUSD(totalDirectUSD)}</div>
            <p className="text-xs text-muted-foreground mt-1">
              Anthropic + Voyage agregado
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Chamadas APIs</CardTitle>
            <Building2 className="size-4 text-brand-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-semibold tabular-nums">{formatNumber(totalCalls)}</div>
            <p className="text-xs text-muted-foreground mt-1">Eventos registrados</p>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Top clientes por custo</CardTitle>
          <CardDescription>Clique pra abrir o cliente.</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="overflow-hidden rounded-md border">
            <table className="w-full text-sm">
              <thead className="bg-muted text-muted-foreground">
                <tr>
                  <th className="text-left font-medium px-3 py-2">Cliente</th>
                  <th className="text-right font-medium px-3 py-2">Direto USD</th>
                  <th className="text-right font-medium px-3 py-2">Total BRL</th>
                  <th className="text-right font-medium px-3 py-2">Chamadas</th>
                </tr>
              </thead>
              <tbody>
                {clientsQuery.isLoading || costQuery.isLoading ? (
                  <tr>
                    <td colSpan={4} className="px-3 py-6 text-center text-muted-foreground">
                      Carregando…
                    </td>
                  </tr>
                ) : (
                  (clientsQuery.data ?? []).map((client) => {
                    const cost = (costQuery.data ?? []).find((c) => c.client_id === client.id);
                    const b = cost?.breakdown;
                    return (
                      <tr
                        key={client.id}
                        className="border-t hover:bg-muted/40 cursor-pointer"
                        onClick={() => navigate(`/clients/${client.id}`)}
                      >
                        <td className="px-3 py-3">
                          <div className="font-medium">{client.name}</div>
                          <div className="text-xs text-muted-foreground font-mono">
                            {client.slug} · {client.status}
                          </div>
                        </td>
                        <td className="px-3 py-3 text-right tabular-nums">
                          {b ? formatUSD(b.direct_cost_usd) : '—'}
                        </td>
                        <td className="px-3 py-3 text-right tabular-nums font-semibold text-brand-500">
                          {b ? formatBRL(b.full_cost_brl) : '—'}
                        </td>
                        <td className="px-3 py-3 text-right tabular-nums text-muted-foreground">
                          {b ? formatNumber(b.num_calls) : 0}
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

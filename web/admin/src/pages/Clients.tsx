import { useQuery } from '@tanstack/react-query';
import { Link, useNavigate } from 'react-router-dom';
import { Building2, Plus } from 'lucide-react';
import { fetchClients, fetchCostByClient } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { formatBRL, formatUSD } from '@/lib/utils';

export default function ClientsPage() {
  const navigate = useNavigate();

  const clientsQuery = useQuery({ queryKey: ['clients'], queryFn: fetchClients });
  const costQuery = useQuery({
    queryKey: ['cost-by-client'],
    queryFn: () => fetchCostByClient(),
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">Clientes</h1>
          <p className="text-muted-foreground">
            Tenants do sistema. Cada um possui squads, agentes e plano próprio.
          </p>
        </div>
        <Button asChild>
          <Link to="/clients/new">
            <Plus className="size-4" /> Novo cliente
          </Link>
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            <Building2 className="inline size-4 mr-1 text-brand-500" /> Lista de
            clientes
          </CardTitle>
          <CardDescription>
            Clique numa linha pra abrir o cliente e ajustar billing.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="overflow-hidden rounded-md border">
            <table className="w-full text-sm">
              <thead className="bg-muted text-muted-foreground">
                <tr>
                  <th className="text-left font-medium px-3 py-2">Cliente</th>
                  <th className="text-left font-medium px-3 py-2">Status</th>
                  <th className="text-left font-medium px-3 py-2">Jira</th>
                  <th className="text-right font-medium px-3 py-2">Custo BRL</th>
                  <th className="text-right font-medium px-3 py-2">Direto USD</th>
                  <th className="text-right font-medium px-3 py-2">Chamadas</th>
                </tr>
              </thead>
              <tbody>
                {clientsQuery.isLoading ? (
                  <tr>
                    <td colSpan={6} className="px-3 py-6 text-center text-muted-foreground">
                      Carregando…
                    </td>
                  </tr>
                ) : (clientsQuery.data ?? []).length === 0 ? (
                  <tr>
                    <td colSpan={6} className="px-3 py-6 text-center text-muted-foreground">
                      Nenhum cliente cadastrado.
                    </td>
                  </tr>
                ) : (
                  (clientsQuery.data ?? []).map((client) => {
                    const cost = (costQuery.data ?? []).find(
                      (c) => c.client_id === client.id,
                    );
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
                            {client.slug}
                          </div>
                        </td>
                        <td className="px-3 py-3">
                          <StatusBadge status={client.status} />
                        </td>
                        <td className="px-3 py-3 text-muted-foreground">
                          {client.jira_workspace_url ? (
                            <span className="font-mono text-xs">
                              {new URL(client.jira_workspace_url).hostname}
                            </span>
                          ) : (
                            '—'
                          )}
                        </td>
                        <td className="px-3 py-3 text-right tabular-nums font-semibold text-brand-500">
                          {b ? formatBRL(b.full_cost_brl) : '—'}
                        </td>
                        <td className="px-3 py-3 text-right tabular-nums">
                          {b ? formatUSD(b.direct_cost_usd) : '—'}
                        </td>
                        <td className="px-3 py-3 text-right tabular-nums text-muted-foreground">
                          {b ? b.num_calls : 0}
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

function StatusBadge({ status }: { status: string }) {
  if (status === 'active') return <Badge variant="success">Ativo</Badge>;
  if (status === 'paused') return <Badge variant="warning">Pausado</Badge>;
  if (status === 'archived') return <Badge variant="muted">Arquivado</Badge>;
  return <Badge variant="outline">{status}</Badge>;
}


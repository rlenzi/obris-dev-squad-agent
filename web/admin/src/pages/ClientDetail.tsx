import { useState, type FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import {
  fetchBillingPlan,
  fetchClient,
  fetchClientCost,
  updateBillingPlan,
  updateClient,
  type BillingPlan,
  type Client,
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
import { formatBRL, formatUSD } from '@/lib/utils';
import CredentialsTab from './Credentials';
import SquadsTab from './Squads';

export default function ClientDetailPage() {
  const { clientId } = useParams<{ clientId: string }>();
  const navigate = useNavigate();

  const clientQuery = useQuery({
    queryKey: ['client', clientId],
    queryFn: () => fetchClient(clientId!),
    enabled: Boolean(clientId),
  });
  const planQuery = useQuery({
    queryKey: ['billing-plan', clientId],
    queryFn: () => fetchBillingPlan(clientId!),
    enabled: Boolean(clientId),
  });
  const costQuery = useQuery({
    queryKey: ['client-cost', clientId],
    queryFn: () => fetchClientCost(clientId!),
    enabled: Boolean(clientId),
  });

  if (clientQuery.isLoading || !clientQuery.data) {
    return <div className="text-muted-foreground">Carregando cliente…</div>;
  }

  const client = clientQuery.data;
  const breakdown = costQuery.data?.breakdown;

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="sm" onClick={() => navigate('/clients')}>
          <ArrowLeft className="size-4" /> Voltar
        </Button>
      </div>

      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">{client.name}</h1>
          <div className="mt-1 flex items-center gap-2 text-muted-foreground">
            <span className="font-mono text-sm">{client.slug}</span>
            <StatusBadge status={client.status} />
          </div>
        </div>
        {breakdown && (
          <div className="rounded-lg border border-border bg-card p-4 text-right">
            <div className="text-xs text-muted-foreground">
              Custo total (últimos 30 dias)
            </div>
            <div className="text-2xl font-semibold tabular-nums text-brand-500">
              {formatBRL(breakdown.full_cost_brl)}
            </div>
            <div className="mt-1 text-xs text-muted-foreground">
              direto {formatUSD(breakdown.direct_cost_usd)} ·{' '}
              {breakdown.num_calls} chamadas
            </div>
          </div>
        )}
      </div>

      <Tabs defaultValue="data" className="w-full">
        <TabsList>
          <TabsTrigger value="data">Dados</TabsTrigger>
          <TabsTrigger value="credentials">Credenciais</TabsTrigger>
          <TabsTrigger value="billing">Billing</TabsTrigger>
          <TabsTrigger value="squads">Squads</TabsTrigger>
        </TabsList>

        <TabsContent value="data">
          <ClientForm client={client} />
        </TabsContent>

        <TabsContent value="credentials">
          <CredentialsTab clientId={client.id} />
        </TabsContent>

        <TabsContent value="billing">
          {planQuery.data && <BillingPlanForm plan={planQuery.data} />}
        </TabsContent>

        <TabsContent value="squads">
          <SquadsTab clientId={client.id} />
        </TabsContent>
      </Tabs>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  if (status === 'active') return <Badge variant="success">Ativo</Badge>;
  if (status === 'paused') return <Badge variant="warning">Pausado</Badge>;
  if (status === 'archived') return <Badge variant="muted">Arquivado</Badge>;
  return <Badge variant="outline">{status}</Badge>;
}

function ClientForm({ client }: { client: Client }) {
  const queryClient = useQueryClient();
  const [name, setName] = useState(client.name);
  const [status, setStatus] = useState(client.status);
  const [jiraUrl, setJiraUrl] = useState(client.jira_workspace_url ?? '');
  const [jiraEmail, setJiraEmail] = useState(client.jira_email ?? '');
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: () =>
      updateClient(client.id, {
        name,
        status,
        jira_workspace_url: jiraUrl || null,
        jira_email: jiraEmail || null,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['client', client.id] });
      queryClient.invalidateQueries({ queryKey: ['clients'] });
      setSaved(true);
      setError(null);
      setTimeout(() => setSaved(false), 2000);
    },
    onError: (err: any) =>
      setError(err?.response?.data?.detail ?? 'Falha ao salvar'),
  });

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    mutation.mutate();
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Identificação</CardTitle>
        <CardDescription>
          Slug é imutável. Jira workspace é endereço da instância Atlassian
          desse cliente (o token vai em <strong>Credenciais</strong>).
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="grid gap-3 md:grid-cols-2">
          <div className="space-y-1.5">
            <Label>Slug</Label>
            <Input value={client.slug} disabled />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="name">Nome</Label>
            <Input id="name" value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="status">Status</Label>
            <select
              id="status"
              value={status}
              onChange={(e) => setStatus(e.target.value)}
              className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <option value="active">Ativo</option>
              <option value="paused">Pausado</option>
              <option value="archived">Arquivado</option>
            </select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="jiraEmail">Jira email</Label>
            <Input
              id="jiraEmail"
              type="email"
              value={jiraEmail}
              onChange={(e) => setJiraEmail(e.target.value)}
            />
          </div>
          <div className="space-y-1.5 md:col-span-2">
            <Label htmlFor="jiraUrl">Jira workspace URL</Label>
            <Input
              id="jiraUrl"
              value={jiraUrl}
              onChange={(e) => setJiraUrl(e.target.value)}
              placeholder="https://acme.atlassian.net"
            />
          </div>
          <div className="md:col-span-2 flex items-center gap-2">
            <Button type="submit" disabled={mutation.isPending}>
              {mutation.isPending ? 'Salvando…' : 'Salvar alterações'}
            </Button>
            {error && <p className="text-sm text-destructive">{error}</p>}
            {saved && <p className="text-sm text-success">Salvo!</p>}
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

function BillingPlanForm({ plan }: { plan: BillingPlan }) {
  const queryClient = useQueryClient();
  const [planKind, setPlanKind] = useState(plan.plan_kind);
  const [baseFee, setBaseFee] = useState(plan.base_fee_monthly_brl);
  const [quotaTokens, setQuotaTokens] = useState(plan.included_quota_tokens.toString());
  const [quotaTasks, setQuotaTasks] = useState(plan.included_quota_tasks.toString());
  const [markup, setMarkup] = useState(plan.overage_markup_pct);
  const [infra, setInfra] = useState(plan.infra_overhead_pct);
  const [fixed, setFixed] = useState(plan.fixed_overhead_brl_per_task);
  const [fx, setFx] = useState(plan.usd_to_brl_rate);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: () =>
      updateBillingPlan(plan.client_id, {
        plan_kind: planKind,
        base_fee_monthly_brl: baseFee,
        included_quota_tokens: Number(quotaTokens),
        included_quota_tasks: Number(quotaTasks),
        overage_markup_pct: markup,
        infra_overhead_pct: infra,
        fixed_overhead_brl_per_task: fixed,
        usd_to_brl_rate: fx,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['billing-plan', plan.client_id] });
      queryClient.invalidateQueries({ queryKey: ['client-cost', plan.client_id] });
      queryClient.invalidateQueries({ queryKey: ['cost-by-client'] });
      setSaved(true);
      setError(null);
      setTimeout(() => setSaved(false), 2000);
    },
    onError: (err: any) =>
      setError(err?.response?.data?.detail ?? 'Falha ao salvar'),
  });

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    mutation.mutate();
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Plano de billing</CardTitle>
        <CardDescription>
          Define quanto cobrar do cliente. Overhead e câmbio entram no cálculo do
          custo total que aparece no dashboard.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="grid grid-cols-2 gap-3">
          <div className="space-y-1.5 col-span-2">
            <Label htmlFor="planKind">Tipo de plano</Label>
            <select
              id="planKind"
              value={planKind}
              onChange={(e) => setPlanKind(e.target.value)}
              className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
            >
              <option value="hybrid">Híbrido (fee + overage)</option>
              <option value="fixed">Fixed price mensal</option>
              <option value="pay_per_use">Pay per use</option>
            </select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="baseFee">Fee mensal (R$)</Label>
            <Input id="baseFee" type="number" step="0.01" value={baseFee} onChange={(e) => setBaseFee(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="fx">Câmbio USD→BRL</Label>
            <Input id="fx" type="number" step="0.0001" value={fx} onChange={(e) => setFx(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="quotaTokens">Quota tokens/mês</Label>
            <Input id="quotaTokens" type="number" value={quotaTokens} onChange={(e) => setQuotaTokens(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="quotaTasks">Quota tasks/mês</Label>
            <Input id="quotaTasks" type="number" value={quotaTasks} onChange={(e) => setQuotaTasks(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="infra">Overhead infra (%)</Label>
            <Input id="infra" type="number" step="0.01" value={infra} onChange={(e) => setInfra(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="fixed">Fixo R$/task</Label>
            <Input id="fixed" type="number" step="0.01" value={fixed} onChange={(e) => setFixed(e.target.value)} />
          </div>
          <div className="space-y-1.5 col-span-2">
            <Label htmlFor="markup">Markup overage (%)</Label>
            <Input id="markup" type="number" step="0.01" value={markup} onChange={(e) => setMarkup(e.target.value)} />
          </div>
          <div className="col-span-2 space-y-2">
            {error && <p className="text-sm text-destructive">{error}</p>}
            {saved && <p className="text-sm text-success">Salvo!</p>}
            <Button type="submit" disabled={mutation.isPending}>
              {mutation.isPending ? 'Salvando…' : 'Salvar plano'}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

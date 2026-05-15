import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import {
  Bell, CreditCard, KeyRound, Settings as SettingsIcon, Users,
} from 'lucide-react';
import { useClientId } from '@/lib/use-client-id';
import {
  fetchBillingPlan,
  fetchClient,
  fetchClientMembers,
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';


export default function SettingsPage() {
  const clientId = useClientId();
  if (!clientId) {
    return <p className="text-muted-foreground">Carregando tenant…</p>;
  }
  return (
    <div className="space-y-6">
      <header className="flex items-center gap-3">
        <SettingsIcon className="size-6 text-brand-500" />
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Configurações</h1>
          <p className="text-sm text-muted-foreground">
            Plano, credenciais, membros e notificações do tenant.
          </p>
        </div>
      </header>

      <Tabs defaultValue="plan" className="w-full">
        <TabsList>
          <TabsTrigger value="plan">Plano</TabsTrigger>
          <TabsTrigger value="credentials">Credenciais</TabsTrigger>
          <TabsTrigger value="members">Membros</TabsTrigger>
          <TabsTrigger value="notifications">Notificações</TabsTrigger>
        </TabsList>

        <TabsContent value="plan" className="mt-6">
          <PlanTab clientId={clientId} />
        </TabsContent>
        <TabsContent value="credentials" className="mt-6">
          <CredentialsTab />
        </TabsContent>
        <TabsContent value="members" className="mt-6">
          <MembersTab clientId={clientId} />
        </TabsContent>
        <TabsContent value="notifications" className="mt-6">
          <NotificationsTab />
        </TabsContent>
      </Tabs>
    </div>
  );
}


function PlanTab({ clientId }: { clientId: string }) {
  const clientQuery = useQuery({
    queryKey: ['client', clientId],
    queryFn: () => fetchClient(clientId),
  });
  const planQuery = useQuery({
    queryKey: ['billing-plan', clientId],
    queryFn: () => fetchBillingPlan(clientId),
    // CLIENT_ADMIN pode nao ter acesso ao endpoint /admin/.
    // Sem retry pra evitar barulho em 403/404.
    retry: false,
  });

  const plan = planQuery.data;
  const client = clientQuery.data;

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <CreditCard className="size-4" />
            Plano atual
          </CardTitle>
          <CardDescription>
            Modelo de cobrança e limites do tenant.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          <p>
            <span className="text-muted-foreground">Tenant:</span>{' '}
            <span className="font-medium">{client?.name ?? '—'}</span>
          </p>
          <p>
            <span className="text-muted-foreground">Status:</span>{' '}
            <Badge variant={client?.status === 'active' ? 'success' : 'muted'}>
              {client?.status ?? '—'}
            </Badge>
          </p>
          {plan ? (
            <>
              <p>
                <span className="text-muted-foreground">Tipo de plano:</span>{' '}
                <Badge variant="outline">{plan.plan_kind}</Badge>
              </p>
              <p>
                <span className="text-muted-foreground">Mensalidade base:</span>{' '}
                R$ {Number(plan.base_fee_monthly_brl ?? 0).toFixed(2)}
              </p>
              <p>
                <span className="text-muted-foreground">Quota inclusa:</span>{' '}
                {plan.included_quota_tasks.toLocaleString('pt-BR')} tasks /{' '}
                {plan.included_quota_tokens.toLocaleString('pt-BR')} tokens
              </p>
              <p>
                <span className="text-muted-foreground">Markup overage:</span>{' '}
                {plan.overage_markup_pct}%
              </p>
            </>
          ) : planQuery.isError ? (
            <p className="text-xs text-muted-foreground">
              Sem permissão pra ver os detalhes do plano direto. Fale com seu
              account manager pra ver fatura/limites.
            </p>
          ) : (
            <p className="text-xs text-muted-foreground">Carregando…</p>
          )}
          <p className="text-xs text-muted-foreground pt-2">
            💡 Mudar plano e ver fatura detalhada chegam em follow-up.
            Por enquanto, contate-nos pra ajustes.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}


function CredentialsTab() {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base flex items-center gap-2">
          <KeyRound className="size-4" />
          Credenciais externas
        </CardTitle>
        <CardDescription>
          GitHub, GitLab, Jira — usados pelos agentes pra operar nos seus
          sistemas.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <Button asChild>
          <Link to="/credentials">Gerenciar credenciais →</Link>
        </Button>
        <p className="mt-3 text-xs text-muted-foreground">
          Painel completo de credenciais vive em <code>/credentials</code>.
          Movido pra cá conforme S-8 evolui.
        </p>
      </CardContent>
    </Card>
  );
}


function MembersTab({ clientId }: { clientId: string }) {
  const membersQuery = useQuery({
    queryKey: ['client-members', clientId],
    queryFn: () => fetchClientMembers(clientId),
  });

  if (membersQuery.isLoading) {
    return <p className="text-sm text-muted-foreground">Carregando…</p>;
  }
  const members = membersQuery.data ?? [];

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Users className="size-4" />
            Membros do tenant ({members.length})
          </CardTitle>
          <CardDescription>
            Quem acessa esse painel. Roles: CLIENT_ADMIN (pode tudo),
            CLIENT_REVIEWER (aprova PRs), CLIENT_VIEWER (read-only).
          </CardDescription>
        </CardHeader>
        <CardContent>
          {members.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              Nenhum membro além de você.
            </p>
          ) : (
            <ul className="divide-y divide-border">
              {members.map(m => (
                <li
                  key={m.id}
                  className="flex items-center justify-between gap-3 py-3"
                >
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium truncate">{m.full_name}</p>
                    <p className="text-xs text-muted-foreground truncate">
                      {m.email}
                    </p>
                  </div>
                  <Badge variant="outline">{m.role}</Badge>
                  {!m.active && <Badge variant="muted">inativo</Badge>}
                </li>
              ))}
            </ul>
          )}
          <p className="mt-4 text-xs text-muted-foreground">
            💡 Convidar / desativar membro inline chega em follow-up. Por
            enquanto, peça via account manager.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}


function NotificationsTab() {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base flex items-center gap-2">
          <Bell className="size-4" />
          Notificações
        </CardTitle>
        <CardDescription>
          Onde você quer receber avisos do sistema.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <div className="rounded-md border bg-muted/20 p-3 text-muted-foreground">
          <p className="font-medium text-foreground">Em construção</p>
          <p className="mt-1 text-xs">
            Eventos planejados: task falhou, PR aberto aguardando review,
            custo passou de threshold, novo membro convidado. Canais:
            email, Slack, webhook custom. Chega em follow-up.
          </p>
        </div>
      </CardContent>
    </Card>
  );
}

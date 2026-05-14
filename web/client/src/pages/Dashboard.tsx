import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { Bot, DollarSign, Users, Activity } from 'lucide-react';
import { useAuth } from '@/lib/auth';
import { fetchSquadsForClient } from '@/lib/api';
import { Badge } from '@/components/ui/badge';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';

export default function ClientDashboardPage() {
  const { me } = useAuth();
  const membership = me?.memberships?.[0];
  const clientId = membership?.client_id;

  const squadsQuery = useQuery({
    queryKey: ['squads', clientId],
    queryFn: () => fetchSquadsForClient(clientId!),
    enabled: Boolean(clientId),
  });

  if (!membership) {
    return (
      <div className="text-muted-foreground">
        Você não está associado a nenhum tenant. Contate o administrador.
      </div>
    );
  }

  const squads = squadsQuery.data ?? [];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight">
          {membership.client_name}
        </h1>
        <p className="text-muted-foreground">
          <code className="font-mono text-sm">{membership.client_slug}</code> ·
          Você está logado como <strong>{membership.role}</strong>
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <StatCard
          icon={<Users className="size-5 text-brand-500" />}
          label="Squads"
          value={String(squads.length)}
        />
        <StatCard
          icon={<Bot className="size-5 text-brand-500" />}
          label="Agentes (estimado)"
          value="—"
          subtitle="entre as squads"
        />
        <StatCard
          icon={<Activity className="size-5 text-brand-500" />}
          label="Runs do mês"
          value="—"
          subtitle="todas as squads"
        />
        <StatCard
          icon={<DollarSign className="size-5 text-brand-500" />}
          label="Custo do mês"
          value="—"
          subtitle="USD direto"
        />
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Suas squads</CardTitle>
          <CardDescription>Equipes ativas no seu tenant</CardDescription>
        </CardHeader>
        <CardContent>
          {squadsQuery.isLoading && (
            <p className="text-sm text-muted-foreground">Carregando…</p>
          )}
          {squadsQuery.isError && (
            <p className="text-sm text-destructive">
              Erro ao carregar squads: {(squadsQuery.error as Error)?.message}
            </p>
          )}
          {squads.length === 0 && !squadsQuery.isLoading && (
            <p className="text-sm italic text-muted-foreground">
              Você ainda não tem nenhuma squad. Crie uma no painel admin ou
              peça ao seu administrador.
            </p>
          )}
          {squads.length > 0 && (
            <ul className="space-y-2">
              {squads.map((squad) => (
                <li key={squad.id}>
                  <Link
                    to={`/squads/${squad.id}`}
                    className="block rounded-md border bg-card p-3 transition-colors hover:border-brand-500"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <div className="font-medium">{squad.name}</div>
                        <div className="font-mono text-xs text-muted-foreground">
                          {squad.slug}
                        </div>
                      </div>
                      <Badge variant={squad.status === 'ACTIVE' ? 'success' : 'outline'}>
                        {squad.status}
                      </Badge>
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
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
  subtitle,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  subtitle?: string;
}) {
  return (
    <Card>
      <CardContent className="flex items-center gap-3 py-4">
        <div className="grid size-10 place-items-center rounded-md bg-muted">
          {icon}
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-xs text-muted-foreground">{label}</div>
          <div className="truncate font-mono text-2xl font-semibold">{value}</div>
          {subtitle && (
            <div className="text-xs text-muted-foreground">{subtitle}</div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

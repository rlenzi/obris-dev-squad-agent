import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { Users } from 'lucide-react';
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

export default function SquadsListPage() {
  const { me } = useAuth();
  const membership = me?.memberships?.[0];
  const clientId = membership?.client_id;

  const squadsQuery = useQuery({
    queryKey: ['squads', clientId],
    queryFn: () => fetchSquadsForClient(clientId!),
    enabled: Boolean(clientId),
  });

  const squads = squadsQuery.data ?? [];

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <div className="grid size-14 place-items-center rounded-lg bg-brand-500/10">
          <Users className="size-7 text-brand-500" />
        </div>
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">Squads</h1>
          <p className="text-muted-foreground">
            Equipes do tenant {membership?.client_name}
          </p>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Squads ativas</CardTitle>
          <CardDescription>
            Clique numa squad pra ver agentes, manifest e histórico
          </CardDescription>
        </CardHeader>
        <CardContent>
          {squadsQuery.isLoading && (
            <p className="text-sm text-muted-foreground">Carregando…</p>
          )}
          {squadsQuery.isError && (
            <p className="text-sm text-destructive">
              Erro: {(squadsQuery.error as Error)?.message}
            </p>
          )}
          {squads.length === 0 && !squadsQuery.isLoading && (
            <p className="text-sm italic text-muted-foreground">
              Sem squads ainda. Crie uma no painel admin.
            </p>
          )}
          {squads.length > 0 && (
            <ul className="space-y-2">
              {squads.map((squad) => (
                <li key={squad.id}>
                  <Link
                    to={`/squads/${squad.id}`}
                    className="block rounded-md border bg-card p-4 transition-colors hover:border-brand-500"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0 flex-1">
                        <div className="font-medium">{squad.name}</div>
                        <div className="font-mono text-xs text-muted-foreground">
                          {squad.slug}
                        </div>
                      </div>
                      <Badge
                        variant={squad.status === 'ACTIVE' ? 'success' : 'outline'}
                      >
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

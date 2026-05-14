import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { Bot, Inbox, Users } from 'lucide-react';
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
        <CardHeader className="flex flex-row items-center justify-between gap-2 space-y-0">
          <div>
            <CardTitle className="text-base">Squads ativas</CardTitle>
            <CardDescription>
              Clique numa squad pra ver agentes, manifest e histórico
            </CardDescription>
          </div>
          {squads.length > 0 && (
            <Badge variant="outline" className="font-mono">
              {squads.length} squad{squads.length === 1 ? '' : 's'}
            </Badge>
          )}
        </CardHeader>
        <CardContent>
          {squadsQuery.isLoading && (
            <ul className="space-y-2">
              {[0, 1, 2].map((i) => (
                <li
                  key={i}
                  className="h-[68px] animate-pulse rounded-md border border-border bg-muted/40"
                />
              ))}
            </ul>
          )}
          {squadsQuery.isError && (
            <div className="rounded-md border border-destructive/40 bg-destructive/5 p-4 text-sm text-destructive">
              Erro ao carregar squads: {(squadsQuery.error as Error)?.message}
            </div>
          )}
          {squads.length === 0 && !squadsQuery.isLoading && !squadsQuery.isError && (
            <div className="flex flex-col items-center gap-2 rounded-md border border-dashed py-10 text-center">
              <div className="grid size-10 place-items-center rounded-full bg-muted">
                <Inbox className="size-5 text-muted-foreground" />
              </div>
              <div className="text-sm font-medium">Nenhuma squad ainda</div>
              <p className="max-w-sm text-xs text-muted-foreground">
                Squads são organizadas pelo time da plataforma. Fale com seu
                administrador para provisionar a primeira.
              </p>
            </div>
          )}
          {squads.length > 0 && (
            <ul className="space-y-2">
              {squads.map((squad) => (
                <li key={squad.id}>
                  <Link
                    to={`/squads/${squad.id}`}
                    className="flex items-start justify-between gap-3 rounded-md border bg-card p-4 transition-colors hover:border-brand-500"
                  >
                    <div className="flex items-start gap-3">
                      <div className="grid size-10 shrink-0 place-items-center rounded-md bg-brand-500/10">
                        <Bot className="size-5 text-brand-500" />
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="font-medium">{squad.name}</div>
                        <div className="font-mono text-xs text-muted-foreground">
                          {squad.slug}
                        </div>
                        {squad.domain && (
                          <div className="text-xs text-muted-foreground">
                            domínio: {squad.domain}
                          </div>
                        )}
                      </div>
                    </div>
                    <Badge
                      variant={squad.status === 'active' ? 'success' : 'outline'}
                    >
                      {squad.status}
                    </Badge>
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

import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { Inbox, Plus } from 'lucide-react';
import {
  fetchClient,
  fetchJiraIntegration,
  fetchTasks,
} from '@/lib/api';
import { useClientId } from '@/lib/use-client-id';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Card, CardContent, CardDescription, CardHeader, CardTitle,
} from '@/components/ui/card';


/**
 * Página /demands — mini-Jira embutido pra cliente que ainda não conectou
 * Jira externo. Estado MVP: lista as tasks locais + ponteia pra criar
 * demanda (TODO: form completo).
 *
 * Quando o cliente tem Jira conectado, mostra banner reforçando que as
 * demandas deveriam vir do Jira mas a página continua acessível pra
 * navegacao.
 */
export default function DemandsPage() {
  const clientId = useClientId();
  const navigate = useNavigate();

  const clientQuery = useQuery({
    queryKey: ['client', clientId],
    queryFn: () => fetchClient(clientId!),
    enabled: Boolean(clientId),
  });
  const integrationQuery = useQuery({
    queryKey: ['jira-integration', clientId],
    queryFn: () => fetchJiraIntegration(clientId!),
    enabled: Boolean(clientId),
  });
  const tasksQuery = useQuery({
    queryKey: ['demands-tasks', clientId],
    queryFn: () => fetchTasks(clientId!, { limit: 50 }),
    enabled: Boolean(clientId),
  });

  const integration = integrationQuery.data;
  const tasks = tasksQuery.data?.items ?? [];

  // Buckets simples por status
  const byStatus = {
    pending: tasks.filter(t => t.status === 'pending'),
    in_progress: tasks.filter(t => t.status === 'in_progress'),
    blocked: tasks.filter(t => t.status === 'blocked'),
    done: tasks.filter(t => t.status === 'done'),
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight">Demandas</h1>
        <p className="mt-1 text-muted-foreground">
          Suas demandas em um único lugar. Cliente sem Jira pode criar
          demandas direto aqui; com Jira, espelhamos automaticamente.
        </p>
      </div>

      {integration?.connected && (
        <Card>
          <CardContent className="p-4 text-sm">
            <p>
              <span className="font-medium">Jira conectado:</span>{' '}
              <code className="text-xs">{clientQuery.data?.jira_workspace_url}</code>
            </p>
            <p className="mt-1 text-xs text-muted-foreground">
              As demandas listadas aqui espelham o Jira. Criar uma demanda
              local cria uma issue lá em seguida.
            </p>
          </CardContent>
        </Card>
      )}

      <div className="flex justify-end">
        <Button onClick={() => navigate('/tasks')} variant="outline" size="sm">
          Ver lista completa de tasks →
        </Button>
        <Button size="sm" className="ml-2" disabled title="Criar demanda chega no follow-up de S-7">
          <Plus className="mr-1 size-3" />
          Nova demanda
        </Button>
      </div>

      {tasks.length === 0 ? (
        <Card>
          <CardContent className="p-8 text-center text-muted-foreground">
            <Inbox className="mx-auto size-8 mb-2" />
            <p>Nenhuma demanda ainda.</p>
            <p className="mt-1 text-xs">
              {integration?.connected
                ? 'Crie uma issue no Jira pra ver aqui.'
                : 'Conecte o Jira em /credentials ou crie uma demanda local.'}
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-4">
          <DemandColumn title="Pendente" tasks={byStatus.pending} variant="muted" />
          <DemandColumn title="Em curso" tasks={byStatus.in_progress} variant="warning" />
          <DemandColumn title="Bloqueada" tasks={byStatus.blocked} variant="destructive" />
          <DemandColumn title="Concluída" tasks={byStatus.done} variant="success" />
        </div>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Como funciona</CardTitle>
          <CardDescription>
            Pipeline de demandas no dev-autonomo
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-2 text-sm text-muted-foreground">
          <p>
            1. <span className="text-foreground">Demanda chega</span> — do Jira
            (via webhook) ou criada direto aqui.
          </p>
          <p>
            2. <span className="text-foreground">BA refina</span> — transforma a
            descrição em spec estruturada.
          </p>
          <p>
            3. <span className="text-foreground">Architect planeja</span> —
            quebra em passos técnicos.
          </p>
          <p>
            4. <span className="text-foreground">Dev executa</span> — abre PR
            no GitHub.
          </p>
          <p>
            5. <span className="text-foreground">Reviewer verifica</span> —
            segunda passada antes da revisão humana.
          </p>
          <p>
            A cada estágio, o painel atualiza em tempo real. Se há Jira
            conectado, comentamos lá também.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}


function DemandColumn({
  title, tasks, variant,
}: {
  title: string;
  tasks: Array<{ id: string; title: string; jira_issue_key: string | null }>;
  variant: 'muted' | 'warning' | 'destructive' | 'success';
}) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm flex items-center justify-between">
          <span>{title}</span>
          <Badge variant={variant as any}>{tasks.length}</Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-1.5">
        {tasks.length === 0 ? (
          <p className="text-xs text-muted-foreground">—</p>
        ) : (
          tasks.slice(0, 8).map(t => (
            <a
              key={t.id}
              href={`/tasks/${t.id}`}
              className="block rounded-md border bg-muted/20 px-2 py-1.5 text-xs hover:bg-muted/40"
            >
              <span className="font-mono">
                {t.jira_issue_key ?? t.id.slice(0, 8)}
              </span>
              {' · '}
              <span className="text-muted-foreground">{t.title.slice(0, 40)}</span>
            </a>
          ))
        )}
        {tasks.length > 8 && (
          <p className="text-xs text-muted-foreground">
            +{tasks.length - 8} mais…
          </p>
        )}
      </CardContent>
    </Card>
  );
}

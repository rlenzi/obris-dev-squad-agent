import { useState, type FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { Plus, Users } from 'lucide-react';
import {
  createSquad,
  fetchSquadsForClient,
  type Squad,
  type SquadCreate,
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
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';

export default function SquadsTab({ clientId }: { clientId: string }) {
  const navigate = useNavigate();
  const [openCreate, setOpenCreate] = useState(false);

  const squadsQuery = useQuery({
    queryKey: ['squads', clientId],
    queryFn: () => fetchSquadsForClient(clientId),
  });

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between">
        <div>
          <CardTitle>Squads</CardTitle>
          <CardDescription>
            Grupos de agentes que atendem áreas/produtos do cliente. Cada squad
            tem manifesto próprio com lista de repos, schemas, eventos e APIs.
          </CardDescription>
        </div>
        <Dialog open={openCreate} onOpenChange={setOpenCreate}>
          <DialogTrigger asChild>
            <Button size="sm">
              <Plus className="size-4" /> Nova squad
            </Button>
          </DialogTrigger>
          {openCreate && <CreateSquadDialog clientId={clientId} onSuccess={() => setOpenCreate(false)} />}
        </Dialog>
      </CardHeader>
      <CardContent>
        {squadsQuery.isLoading ? (
          <p className="text-sm text-muted-foreground">Carregando…</p>
        ) : (squadsQuery.data ?? []).length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Nenhuma squad cadastrada. Crie a primeira pra começar a provisionar
            agentes.
          </p>
        ) : (
          <ul className="space-y-2">
            {(squadsQuery.data ?? []).map((squad) => (
              <SquadRow
                key={squad.id}
                squad={squad}
                onClick={() => navigate(`/clients/${clientId}/squads/${squad.id}`)}
              />
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

function SquadRow({ squad, onClick }: { squad: Squad; onClick: () => void }) {
  return (
    <li
      className="flex cursor-pointer items-center justify-between rounded-md border border-border p-3 hover:bg-muted/40"
      onClick={onClick}
    >
      <div className="flex items-center gap-3">
        <div className="grid size-9 place-items-center rounded-md bg-brand-500/10">
          <Users className="size-4 text-brand-500" />
        </div>
        <div>
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-medium">{squad.name}</span>
            <StatusBadge status={squad.status} />
          </div>
          <div className="text-xs text-muted-foreground font-mono">
            {squad.slug} {squad.domain && `· ${squad.domain}`}
            {squad.current_manifest_id ? ' · manifest ativo' : ' · SEM manifest'}
          </div>
        </div>
      </div>
    </li>
  );
}

function StatusBadge({ status }: { status: Squad['status'] }) {
  const map: Record<string, { variant: any; label: string }> = {
    provisioning: { variant: 'warning', label: 'Provisionando' },
    active: { variant: 'success', label: 'Ativa' },
    paused: { variant: 'warning', label: 'Pausada' },
    archived: { variant: 'muted', label: 'Arquivada' },
  };
  const m = map[status] ?? { variant: 'outline', label: status };
  return <Badge variant={m.variant}>{m.label}</Badge>;
}

function CreateSquadDialog({
  clientId,
  onSuccess,
}: {
  clientId: string;
  onSuccess: () => void;
}) {
  const queryClient = useQueryClient();
  const [slug, setSlug] = useState('');
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [domain, setDomain] = useState('');
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: (payload: SquadCreate) => createSquad(clientId, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['squads', clientId] });
      onSuccess();
    },
    onError: (err: any) =>
      setError(err?.response?.data?.detail ?? 'Falha ao criar squad'),
  });

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    mutation.mutate({
      slug,
      name,
      description: description || undefined,
      domain: domain || undefined,
    });
  }

  return (
    <DialogContent>
      <DialogHeader>
        <DialogTitle>Nova squad</DialogTitle>
        <DialogDescription>
          Squads agrupam agentes que atendem uma área específica. Depois de
          criada, configure o manifesto com os repos que ela opera.
        </DialogDescription>
      </DialogHeader>
      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="space-y-1.5">
          <Label htmlFor="slug">Slug *</Label>
          <Input
            id="slug"
            value={slug}
            onChange={(e) =>
              setSlug(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, '-'))
            }
            placeholder="payments-team"
            required
            pattern="^[a-z0-9][a-z0-9-]*$"
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="name">Nome *</Label>
          <Input
            id="name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Squad Pagamentos"
            required
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="domain">Domínio (opcional)</Label>
          <Input
            id="domain"
            value={domain}
            onChange={(e) => setDomain(e.target.value)}
            placeholder="pagamentos"
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="description">Descrição (opcional)</Label>
          <Input
            id="description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Time autonomo de pagamentos e cobranca"
          />
        </div>
        {error && <p className="text-sm text-destructive">{error}</p>}
        <DialogFooter>
          <Button type="submit" disabled={mutation.isPending}>
            {mutation.isPending ? 'Criando…' : 'Criar squad'}
          </Button>
        </DialogFooter>
      </form>
    </DialogContent>
  );
}

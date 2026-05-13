import { useState, type FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { formatDistanceToNow } from 'date-fns';
import { ptBR } from 'date-fns/locale/pt-BR';
import { KeyRound, Plus, RefreshCw, Trash2 } from 'lucide-react';
import {
  createCredential,
  deleteCredential,
  fetchCredentials,
  rotateCredential,
  type Credential,
  type CredentialKind,
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

const KIND_LABEL: Record<string, string> = {
  github_token: 'GitHub token',
  gitlab_token: 'GitLab token',
  jira_token: 'Jira API token',
  generic: 'Genérico',
};

export default function CredentialsTab({ clientId }: { clientId: string }) {
  const [openCreate, setOpenCreate] = useState(false);

  const credsQuery = useQuery({
    queryKey: ['credentials', clientId],
    queryFn: () => fetchCredentials(clientId),
  });

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between">
        <div>
          <CardTitle>Credenciais</CardTitle>
          <CardDescription>
            Tokens (Jira, GitHub, GitLab) criptografados com Fernet. O valor
            descriptografado nunca volta na API — só metadata.
          </CardDescription>
        </div>
        <Dialog open={openCreate} onOpenChange={setOpenCreate}>
          <DialogTrigger asChild>
            <Button size="sm">
              <Plus className="size-4" /> Nova credencial
            </Button>
          </DialogTrigger>
          {openCreate && <CreateCredentialDialog clientId={clientId} onSuccess={() => setOpenCreate(false)} />}
        </Dialog>
      </CardHeader>
      <CardContent>
        {credsQuery.isLoading ? (
          <p className="text-sm text-muted-foreground">Carregando…</p>
        ) : (credsQuery.data ?? []).length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Nenhuma credencial cadastrada. Adicione tokens GitHub e Jira pra o
            agente poder operar.
          </p>
        ) : (
          <ul className="space-y-2">
            {(credsQuery.data ?? []).map((cred) => (
              <CredentialRow key={cred.id} clientId={clientId} cred={cred} />
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

function CredentialRow({ clientId, cred }: { clientId: string; cred: Credential }) {
  const queryClient = useQueryClient();
  const [openRotate, setOpenRotate] = useState(false);

  const deleteMutation = useMutation({
    mutationFn: () => deleteCredential(clientId, cred.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['credentials', clientId] });
    },
  });

  return (
    <li className="flex items-center justify-between rounded-md border border-border p-3">
      <div className="flex items-center gap-3 min-w-0">
        <div className="grid size-9 place-items-center rounded-md bg-brand-500/10">
          <KeyRound className="size-4 text-brand-500" />
        </div>
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-medium">{cred.name}</span>
            <Badge variant="secondary">{KIND_LABEL[cred.kind] ?? cred.kind}</Badge>
          </div>
          <div className="text-xs text-muted-foreground">
            {cred.last_rotated_at
              ? `rotacionada ${formatDistanceToNow(new Date(cred.last_rotated_at), {
                  locale: ptBR,
                  addSuffix: true,
                })}`
              : 'sem rotação registrada'}
            {' · '}
            {cred.last_used_at
              ? `usada ${formatDistanceToNow(new Date(cred.last_used_at), {
                  locale: ptBR,
                  addSuffix: true,
                })}`
              : 'nunca usada'}
          </div>
        </div>
      </div>
      <div className="flex items-center gap-1">
        <Dialog open={openRotate} onOpenChange={setOpenRotate}>
          <DialogTrigger asChild>
            <Button variant="ghost" size="sm">
              <RefreshCw className="size-3.5" /> Rotacionar
            </Button>
          </DialogTrigger>
          {openRotate && (
            <RotateCredentialDialog
              clientId={clientId}
              cred={cred}
              onSuccess={() => setOpenRotate(false)}
            />
          )}
        </Dialog>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => {
            if (confirm(`Deletar credencial "${cred.name}"?`)) {
              deleteMutation.mutate();
            }
          }}
        >
          <Trash2 className="size-3.5 text-destructive" />
        </Button>
      </div>
    </li>
  );
}

function CreateCredentialDialog({
  clientId,
  onSuccess,
}: {
  clientId: string;
  onSuccess: () => void;
}) {
  const queryClient = useQueryClient();
  const [kind, setKind] = useState<CredentialKind>('github_token');
  const [name, setName] = useState('main');
  const [value, setValue] = useState('');
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: () => createCredential(clientId, { kind, name, value }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['credentials', clientId] });
      onSuccess();
    },
    onError: (err: any) =>
      setError(err?.response?.data?.detail ?? 'Falha ao salvar'),
  });

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    mutation.mutate();
  }

  return (
    <DialogContent>
      <DialogHeader>
        <DialogTitle>Nova credencial</DialogTitle>
        <DialogDescription>
          O valor é criptografado com Fernet antes de salvar. Você nunca vai
          conseguir vê-lo de novo — só rotacionar.
        </DialogDescription>
      </DialogHeader>
      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="space-y-1.5">
          <Label htmlFor="kind">Tipo</Label>
          <select
            id="kind"
            value={kind}
            onChange={(e) => setKind(e.target.value as CredentialKind)}
            className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <option value="github_token">GitHub token</option>
            <option value="gitlab_token">GitLab token</option>
            <option value="jira_token">Jira API token</option>
            <option value="generic">Genérico</option>
          </select>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="name">Nome (apelido)</Label>
          <Input
            id="name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="main"
            required
          />
          <p className="text-xs text-muted-foreground">
            Útil quando você tem mais de uma do mesmo tipo (ex: "read" vs
            "write").
          </p>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="value">Valor (token)</Label>
          <Input
            id="value"
            type="password"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder="github_pat_... ou ATATT..."
            required
            autoComplete="off"
          />
        </div>
        {error && <p className="text-sm text-destructive">{error}</p>}
        <DialogFooter>
          <Button type="submit" disabled={mutation.isPending}>
            {mutation.isPending ? 'Salvando…' : 'Salvar credencial'}
          </Button>
        </DialogFooter>
      </form>
    </DialogContent>
  );
}

function RotateCredentialDialog({
  clientId,
  cred,
  onSuccess,
}: {
  clientId: string;
  cred: Credential;
  onSuccess: () => void;
}) {
  const queryClient = useQueryClient();
  const [value, setValue] = useState('');
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: () => rotateCredential(clientId, cred.id, { value }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['credentials', clientId] });
      setValue('');
      onSuccess();
    },
    onError: (err: any) =>
      setError(err?.response?.data?.detail ?? 'Falha ao rotacionar'),
  });

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    mutation.mutate();
  }

  return (
    <DialogContent>
      <DialogHeader>
        <DialogTitle>Rotacionar {cred.name}</DialogTitle>
        <DialogDescription>
          Substitui o valor atual. Útil quando o token vence ou é comprometido.
        </DialogDescription>
      </DialogHeader>
      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="space-y-1.5">
          <Label htmlFor="newValue">Novo valor</Label>
          <Input
            id="newValue"
            type="password"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            required
            autoComplete="off"
          />
        </div>
        {error && <p className="text-sm text-destructive">{error}</p>}
        <DialogFooter>
          <Button type="submit" disabled={mutation.isPending}>
            {mutation.isPending ? 'Rotacionando…' : 'Rotacionar'}
          </Button>
        </DialogFooter>
      </form>
    </DialogContent>
  );
}

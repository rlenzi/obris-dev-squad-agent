import { useState } from 'react';
import { useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  BookOpen, FileText, Search, Trash2, UploadCloud,
} from 'lucide-react';
import { useClientId } from '@/lib/use-client-id';
import {
  deleteSquadKnowledgeSource,
  ingestSquadFile,
  ingestSquadText,
  listSquadKnowledgeSources,
  searchSquadKnowledge,
  type RagSourceQualityClient,
  type RetrievalHit,
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
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { formatApiError } from '@/lib/utils';

const QUALITY_OPTIONS: { value: RagSourceQualityClient; label: string }[] = [
  { value: 'internal', label: 'Runbook interno / convencao interna' },
  { value: 'official', label: 'Doc oficial (sua copia local)' },
  { value: 'partner', label: 'Partner / 3a parte' },
  { value: 'community', label: 'Comunidade' },
];

export default function SquadKnowledgePage() {
  const { squadId } = useParams<{ squadId: string }>();
  const clientId = useClientId();

  if (!squadId || !clientId) {
    return <p className="p-6 text-muted-foreground">Selecione uma squad.</p>;
  }

  return (
    <div className="space-y-6">
      <header className="flex items-center gap-3">
        <BookOpen className="size-6 text-brand-500" />
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">
            Conhecimento privado da squad
          </h1>
          <p className="text-sm text-muted-foreground">
            Runbooks internos, convenções da casa, decisões arquiteturais. Visível
            apenas aos agentes desta squad.
          </p>
        </div>
      </header>

      <Tabs defaultValue="overview" className="w-full">
        <TabsList>
          <TabsTrigger value="overview">Visão geral</TabsTrigger>
          <TabsTrigger value="add">Adicionar</TabsTrigger>
          <TabsTrigger value="search">Buscar</TabsTrigger>
          <TabsTrigger value="cleanup">Limpar</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="mt-6">
          <OverviewTab clientId={clientId} squadId={squadId} />
        </TabsContent>
        <TabsContent value="add" className="mt-6">
          <AddTab clientId={clientId} squadId={squadId} />
        </TabsContent>
        <TabsContent value="search" className="mt-6">
          <SearchTab clientId={clientId} squadId={squadId} />
        </TabsContent>
        <TabsContent value="cleanup" className="mt-6">
          <CleanupTab clientId={clientId} squadId={squadId} />
        </TabsContent>
      </Tabs>
    </div>
  );
}


// ---- Visão geral ----

function OverviewTab({ clientId, squadId }: { clientId: string; squadId: string }) {
  const { data, isLoading } = useQuery({
    queryKey: ['squad-knowledge', squadId],
    queryFn: () => listSquadKnowledgeSources(clientId, squadId),
  });

  if (isLoading) {
    return <p className="text-sm text-muted-foreground">Carregando…</p>;
  }
  const sources = data ?? [];
  const totalChunks = sources.reduce((acc, s) => acc + (s.indexed_chunks ?? 0), 0);
  const byQuality: Record<string, number> = {};
  for (const s of sources) {
    byQuality[s.source_quality] = (byQuality[s.source_quality] ?? 0) + 1;
  }

  return (
    <div className="space-y-4">
      <div className="grid gap-4 md:grid-cols-3">
        <KpiCard label="Fontes indexadas" value={String(sources.length)} />
        <KpiCard label="Chunks totais" value={String(totalChunks)} />
        <KpiCard
          label="Falhas"
          value={String(sources.filter(s => s.status === 'failed').length)}
        />
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Distribuição por qualidade</CardTitle>
        </CardHeader>
        <CardContent>
          {Object.keys(byQuality).length === 0 ? (
            <p className="text-sm text-muted-foreground">
              Nenhuma fonte ainda. Use a aba "Adicionar".
            </p>
          ) : (
            <ul className="space-y-1.5">
              {Object.entries(byQuality).map(([q, n]) => (
                <li key={q} className="flex items-center gap-3 text-sm">
                  <Badge variant="outline">{q}</Badge>
                  <span className="text-muted-foreground">{n} fonte(s)</span>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}


function KpiCard({ label, value }: { label: string; value: string }) {
  return (
    <Card>
      <CardContent className="p-4">
        <p className="text-xs text-muted-foreground">{label}</p>
        <p className="mt-2 text-2xl font-semibold">{value}</p>
      </CardContent>
    </Card>
  );
}


// ---- Adicionar (ex-IngestPanel) ----

function AddTab({ clientId, squadId }: { clientId: string; squadId: string }) {
  const queryClient = useQueryClient();
  const [mode, setMode] = useState<'text' | 'file'>('text');
  const [text, setText] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [quality, setQuality] = useState<RagSourceQualityClient>('internal');
  const [stackVersion, setStackVersion] = useState('');
  const [tags, setTags] = useState('');

  const ingestMutation = useMutation({
    mutationFn: async () => {
      const common = {
        source_quality: quality,
        stack_version: stackVersion || undefined,
        tags,
      };
      if (mode === 'text') return ingestSquadText(clientId, squadId, { ...common, text });
      if (!file) throw new Error('selecione um arquivo');
      return ingestSquadFile(clientId, squadId, { ...common, file });
    },
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ['squad-knowledge', squadId] });
      setText('');
      setFile(null);
      alert(
        res.deduplicated
          ? `Já existia (dedup). ID: ${res.rag_source_id}`
          : `Indexado: ${res.indexed_chunks} chunks · status=${res.status}`,
      );
    },
  });

  const disabled =
    ingestMutation.isPending ||
    (mode === 'text' && text.length < 50) ||
    (mode === 'file' && !file);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base flex items-center gap-2">
          <UploadCloud className="size-5 text-brand-500" />
          Adicionar fonte
        </CardTitle>
        <CardDescription>
          Apenas os agentes desta squad terão acesso. Conteúdo nunca é
          compartilhado cross-tenant.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex gap-2">
          <Button
            size="sm"
            variant={mode === 'text' ? 'default' : 'outline'}
            onClick={() => setMode('text')}
          >
            Texto
          </Button>
          <Button
            size="sm"
            variant={mode === 'file' ? 'default' : 'outline'}
            onClick={() => setMode('file')}
          >
            Arquivo
          </Button>
        </div>

        {mode === 'text' ? (
          <div>
            <Label>Conteúdo (mín. 50 chars)</Label>
            <textarea
              rows={6}
              value={text}
              onChange={(e) => setText(e.target.value)}
              className="mt-1 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
              placeholder="Cole conteúdo aqui (runbook, decisão arquitetural, convenção...)"
            />
          </div>
        ) : (
          <div>
            <Label>Arquivo (PDF, DOCX, MD, TXT — máx 50MB)</Label>
            <Input
              type="file"
              accept=".pdf,.docx,.doc,.md,.markdown,.txt"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
          </div>
        )}

        <div className="grid gap-3 sm:grid-cols-2">
          <div>
            <Label>Qualidade</Label>
            <select
              className="mt-1 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
              value={quality}
              onChange={(e) => setQuality(e.target.value as RagSourceQualityClient)}
            >
              {QUALITY_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <Label>Versão da stack (opcional)</Label>
            <Input
              value={stackVersion}
              onChange={(e) => setStackVersion(e.target.value)}
              placeholder="hybris-2305, salesforce-spring-25..."
            />
          </div>
          <div className="sm:col-span-2">
            <Label>Tags (CSV, opcional)</Label>
            <Input
              value={tags}
              onChange={(e) => setTags(e.target.value)}
              placeholder="onboarding, deploys, runbook"
            />
          </div>
        </div>

        {ingestMutation.error && (
          <p className="text-sm text-destructive">
            {formatApiError(ingestMutation.error)}
          </p>
        )}

        <Button onClick={() => ingestMutation.mutate()} disabled={disabled}>
          {ingestMutation.isPending ? 'Processando…' : 'Indexar'}
        </Button>
      </CardContent>
    </Card>
  );
}


// ---- Buscar (S-8 — usa /retrieval/search) ----

function SearchTab({ clientId, squadId }: { clientId: string; squadId: string }) {
  const [query, setQuery] = useState('');
  const [submittedQuery, setSubmittedQuery] = useState('');

  const searchMutation = useMutation({
    mutationFn: () => searchSquadKnowledge(clientId, squadId, submittedQuery, 10),
  });

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Search className="size-4" />
            Busca semântica
          </CardTitle>
          <CardDescription>
            Veja o que o agente vai receber pra uma query — chunks com score
            rerank-aware. Útil pra debugar relevância.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (query.trim().length < 3) return;
              setSubmittedQuery(query.trim());
              searchMutation.mutate();
            }}
            className="flex gap-2"
          >
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Como o pipeline de deploy funciona?"
              minLength={3}
            />
            <Button type="submit" disabled={searchMutation.isPending || query.trim().length < 3}>
              {searchMutation.isPending ? 'Buscando…' : 'Buscar'}
            </Button>
          </form>
          {searchMutation.error && (
            <p className="mt-2 text-xs text-destructive">
              {formatApiError(searchMutation.error)}
            </p>
          )}
        </CardContent>
      </Card>

      {searchMutation.data && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">
              {searchMutation.data.hits.length} hits
              <span className="ml-2 text-xs font-normal text-muted-foreground">
                de {searchMutation.data.total} candidates
              </span>
            </CardTitle>
          </CardHeader>
          <CardContent>
            {searchMutation.data.hits.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                Nenhum chunk relevante. Adicione mais fontes ou refraseie.
              </p>
            ) : (
              <ol className="space-y-3">
                {searchMutation.data.hits.map((hit, i) => (
                  <HitRow key={i} hit={hit} rank={i + 1} />
                ))}
              </ol>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}


function HitRow({ hit, rank }: { hit: RetrievalHit; rank: number }) {
  return (
    <li className="rounded-md border bg-muted/10 px-3 py-2">
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <span className="font-mono">#{rank}</span>
        <Badge variant="outline">{hit.scope}</Badge>
        <Badge variant="muted">{hit.source_quality}</Badge>
        <span>score: {hit.score.toFixed(3)}</span>
        {hit.source_uri && (
          <span className="truncate">· {hit.source_uri}</span>
        )}
      </div>
      <p className="mt-1.5 text-sm whitespace-pre-wrap line-clamp-4">
        {hit.content}
      </p>
    </li>
  );
}


// ---- Limpar (bulk delete com confirmação dupla) ----

function CleanupTab({ clientId, squadId }: { clientId: string; squadId: string }) {
  const queryClient = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ['squad-knowledge', squadId],
    queryFn: () => listSquadKnowledgeSources(clientId, squadId),
  });
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [confirmText, setConfirmText] = useState('');

  const deleteMutation = useMutation({
    mutationFn: async (ids: string[]) => {
      // sequencial pra ter feedback de erro por item; volume baixo (<50 fontes)
      for (const id of ids) {
        await deleteSquadKnowledgeSource(clientId, squadId, id);
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['squad-knowledge', squadId] });
      setSelected(new Set());
      setConfirmText('');
    },
  });

  if (isLoading) {
    return <p className="text-sm text-muted-foreground">Carregando…</p>;
  }
  const sources = data ?? [];
  const allSelected = selected.size === sources.length && sources.length > 0;
  const confirmMatched = confirmText.trim().toLowerCase() === 'remover';

  function toggle(id: string) {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setSelected(next);
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Trash2 className="size-4 text-destructive" />
            Remover fontes
          </CardTitle>
          <CardDescription>
            Marca as fontes pra remover. Ação irreversível: chunks
            desaparecem do Qdrant e o registro vai pra delete. Confirme
            digitando <code>remover</code>.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {sources.length === 0 ? (
            <p className="text-sm italic text-muted-foreground">
              Nenhuma fonte indexada. Nada pra remover.
            </p>
          ) : (
            <>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={allSelected}
                  onChange={() => {
                    if (allSelected) setSelected(new Set());
                    else setSelected(new Set(sources.map(s => s.id)));
                  }}
                />
                Selecionar todas ({sources.length})
              </label>

              <ul className="divide-y divide-border max-h-96 overflow-y-auto">
                {sources.map(src => (
                  <li key={src.id} className="flex items-center gap-3 py-2">
                    <input
                      type="checkbox"
                      checked={selected.has(src.id)}
                      onChange={() => toggle(src.id)}
                    />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium truncate">
                        <FileText className="inline size-3 text-muted-foreground mr-1" />
                        {src.source_uri || src.source_hash.slice(0, 10)}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {src.source_quality} · {src.indexed_chunks} chunks
                      </p>
                    </div>
                  </li>
                ))}
              </ul>

              {selected.size > 0 && (
                <div className="space-y-2 pt-3 border-t">
                  <p className="text-sm">
                    <span className="font-medium text-destructive">
                      {selected.size} fonte(s) selecionada(s)
                    </span>
                    {' '}— digite <code>remover</code> pra confirmar:
                  </p>
                  <Input
                    value={confirmText}
                    onChange={(e) => setConfirmText(e.target.value)}
                    placeholder="remover"
                  />
                  <Button
                    variant="destructive"
                    onClick={() => deleteMutation.mutate(Array.from(selected))}
                    disabled={!confirmMatched || deleteMutation.isPending}
                  >
                    {deleteMutation.isPending
                      ? `Removendo ${selected.size}…`
                      : `Remover ${selected.size} fonte(s)`}
                  </Button>
                  {deleteMutation.error && (
                    <p className="text-xs text-destructive">
                      {formatApiError(deleteMutation.error)}
                    </p>
                  )}
                </div>
              )}
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

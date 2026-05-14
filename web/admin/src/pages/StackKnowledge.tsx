import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ChevronLeft, FileText, Globe, Library, Trash2, UploadCloud } from 'lucide-react';
import {
  deleteStackSource,
  ingestStackFile,
  ingestStackText,
  ingestStackUrl,
  listStackCollections,
  listStackSources,
  type RagSourceLicense,
  type RagSourceQuality,
  type StackCollectionSummary,
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
import { Textarea } from '@/components/ui/textarea';
import { formatApiError } from '@/lib/utils';

const QUALITY_OPTIONS: { value: RagSourceQuality; label: string }[] = [
  { value: 'official', label: 'Doc oficial do fornecedor' },
  { value: 'orbis_curated', label: 'Conhecimento Orbis (experiência da casa)' },
  { value: 'partner', label: 'Parceiro / 3ª parte confiável' },
  { value: 'community', label: 'Comunidade (blog, SO)' },
];

const LICENSE_OPTIONS: { value: RagSourceLicense; label: string }[] = [
  { value: 'redistributable', label: 'Redistribuível (público ou parceria)' },
  { value: 'partner_only', label: 'Parceiro/NDA (NÃO redistribuir)' },
  { value: 'unknown', label: 'Desconhecida' },
];

export default function StackKnowledgePage() {
  const [selectedStack, setSelectedStack] = useState<StackCollectionSummary | null>(null);

  if (selectedStack) {
    return (
      <StackDetailView
        stack={selectedStack}
        onBack={() => setSelectedStack(null)}
      />
    );
  }
  return <StackListView onSelect={setSelectedStack} />;
}

function StackListView({ onSelect }: { onSelect: (s: StackCollectionSummary) => void }) {
  const { data, isLoading, error } = useQuery({
    queryKey: ['stack-collections'],
    queryFn: listStackCollections,
  });

  return (
    <div className="space-y-6">
      <header className="flex items-center gap-3">
        <Library className="size-6 text-brand-500" />
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Stack Knowledge</h1>
          <p className="text-sm text-muted-foreground">
            Curadoria cross-tenant de conhecimento por stack. Material público + experiência Orbis.
          </p>
        </div>
      </header>

      {isLoading && <p className="text-muted-foreground">Carregando…</p>}
      {error && <p className="text-destructive">{formatApiError(error)}</p>}
      {data && (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {data.map((s) => (
            <button
              key={s.stack_slug}
              type="button"
              onClick={() => onSelect(s)}
              className="rounded-lg border border-border bg-card p-4 text-left transition-colors hover:bg-muted"
            >
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-sm font-medium">{s.stack_name}</div>
                  <div className="font-mono text-xs text-muted-foreground">{s.stack_slug}</div>
                </div>
                <div className="text-right">
                  <div className="text-2xl font-semibold">{s.total_chunks}</div>
                  <div className="text-[10px] uppercase tracking-wide text-muted-foreground">chunks</div>
                </div>
              </div>
              <div className="mt-3 flex flex-wrap gap-1">
                <Badge variant="outline" className="text-[10px]">
                  {s.total_sources} fontes
                </Badge>
                {Object.entries(s.sources_by_quality).map(([q, n]) => (
                  <Badge key={q} variant="secondary" className="text-[10px]">
                    {q}: {n}
                  </Badge>
                ))}
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function StackDetailView({
  stack,
  onBack,
}: {
  stack: StackCollectionSummary;
  onBack: () => void;
}) {
  const queryClient = useQueryClient();
  const { data: sources, refetch } = useQuery({
    queryKey: ['stack-sources', stack.stack_slug],
    queryFn: () => listStackSources(stack.stack_slug),
  });

  const deleteMutation = useMutation({
    mutationFn: (sourceId: string) => deleteStackSource(stack.stack_slug, sourceId),
    onSuccess: () => {
      refetch();
      queryClient.invalidateQueries({ queryKey: ['stack-collections'] });
    },
  });

  return (
    <div className="space-y-6">
      <header>
        <Button variant="ghost" size="sm" onClick={onBack}>
          <ChevronLeft className="mr-1 size-4" /> Voltar
        </Button>
        <div className="mt-2 flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">{stack.stack_name}</h1>
            <p className="font-mono text-xs text-muted-foreground">
              stack_patterns:{stack.stack_slug}
            </p>
          </div>
          <Badge variant="default">{stack.total_chunks} chunks · {stack.total_sources} fontes</Badge>
        </div>
      </header>

      <IngestForm stackSlug={stack.stack_slug} onIngested={() => { refetch(); queryClient.invalidateQueries({ queryKey: ['stack-collections'] }); }} />

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Fontes indexadas</CardTitle>
          <CardDescription>
            Remover apaga os chunks correspondentes no Qdrant.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {!sources || sources.length === 0 ? (
            <p className="text-sm italic text-muted-foreground">
              Nenhuma fonte ainda. Use o formulário acima pra adicionar.
            </p>
          ) : (
            <ul className="divide-y divide-border">
              {sources.map((src) => (
                <li key={src.id} className="flex items-center justify-between gap-3 py-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <KindIcon kind={src.kind} />
                      <span className="truncate text-sm font-medium">
                        {src.source_uri || src.source_hash.slice(0, 10)}
                      </span>
                    </div>
                    <div className="mt-1 flex flex-wrap gap-1 text-xs">
                      <Badge variant="outline">{src.source_quality}</Badge>
                      <Badge variant="outline">{src.license}</Badge>
                      {src.stack_version && (
                        <Badge variant="outline">v: {src.stack_version}</Badge>
                      )}
                      <Badge variant="secondary">{src.indexed_chunks} chunks</Badge>
                      {src.status === 'failed' && (
                        <Badge variant="danger">{src.error_message?.slice(0, 60)}</Badge>
                      )}
                    </div>
                  </div>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => {
                      if (confirm('Remover esta fonte e seus chunks?')) {
                        deleteMutation.mutate(src.id);
                      }
                    }}
                    disabled={deleteMutation.isPending}
                  >
                    <Trash2 className="size-4 text-destructive" />
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function IngestForm({
  stackSlug,
  onIngested,
}: {
  stackSlug: string;
  onIngested: () => void;
}) {
  const [mode, setMode] = useState<'text' | 'url' | 'file'>('text');
  const [text, setText] = useState('');
  const [url, setUrl] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [license, setLicense] = useState<RagSourceLicense>('redistributable');
  const [quality, setQuality] = useState<RagSourceQuality>('official');
  const [stackVersion, setStackVersion] = useState('');
  const [tags, setTags] = useState('');
  const [hasRights, setHasRights] = useState(false);

  const requiresRights = useMemo(() => license === 'redistributable', [license]);

  const ingestMutation = useMutation({
    mutationFn: async () => {
      const common = {
        license,
        source_quality: quality,
        stack_version: stackVersion || undefined,
        tags,
        has_redistribution_right: hasRights,
      };
      if (mode === 'text') return ingestStackText(stackSlug, { ...common, text });
      if (mode === 'url') return ingestStackUrl(stackSlug, { ...common, url });
      if (!file) throw new Error('selecione um arquivo');
      return ingestStackFile(stackSlug, { ...common, file });
    },
    onSuccess: (res) => {
      onIngested();
      setText('');
      setUrl('');
      setFile(null);
      alert(
        res.deduplicated
          ? `Fonte já existia (dedup por hash). ID: ${res.rag_source_id}`
          : `Indexado: ${res.indexed_chunks} chunks · status=${res.status}`,
      );
    },
  });

  const disabled =
    ingestMutation.isPending ||
    (mode === 'text' && text.length < 50) ||
    (mode === 'url' && url.length < 10) ||
    (mode === 'file' && !file) ||
    (requiresRights && !hasRights);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base flex items-center gap-2">
          <UploadCloud className="size-5 text-brand-500" />
          Adicionar fonte
        </CardTitle>
        <CardDescription>
          Material indexado em <code className="font-mono">stack_patterns:{stackSlug}</code> fica
          disponível pra todos os clientes que usem essa stack.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex gap-2">
          {(['text', 'url', 'file'] as const).map((m) => (
            <Button
              key={m}
              size="sm"
              variant={mode === m ? 'default' : 'outline'}
              onClick={() => setMode(m)}
            >
              {m === 'text' ? 'Texto' : m === 'url' ? 'URL' : 'Arquivo'}
            </Button>
          ))}
        </div>

        {mode === 'text' && (
          <div>
            <Label>Conteúdo (mín. 50 chars)</Label>
            <Textarea
              rows={6}
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="Cole aqui o conteúdo (notas, transcript, doc oficial...)"
            />
          </div>
        )}
        {mode === 'url' && (
          <div>
            <Label>URL</Label>
            <Input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://..." />
          </div>
        )}
        {mode === 'file' && (
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
            <Label>Qualidade da fonte</Label>
            <select
              className="mt-1 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
              value={quality}
              onChange={(e) => setQuality(e.target.value as RagSourceQuality)}
            >
              {QUALITY_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <Label>Licença</Label>
            <select
              className="mt-1 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
              value={license}
              onChange={(e) => setLicense(e.target.value as RagSourceLicense)}
            >
              {LICENSE_OPTIONS.map((o) => (
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
          <div>
            <Label>Tags (CSV, opcional)</Label>
            <Input
              value={tags}
              onChange={(e) => setTags(e.target.value)}
              placeholder="checkout, b2b, oms"
            />
          </div>
        </div>

        {requiresRights && (
          <label className="flex items-start gap-2 rounded-md border border-warning/40 bg-warning/5 p-3 text-sm">
            <input
              type="checkbox"
              checked={hasRights}
              onChange={(e) => setHasRights(e.target.checked)}
              className="mt-1"
            />
            <span>
              <strong>Confirmo que tenho direito de redistribuir</strong> este conteúdo cross-tenant.
              Esse aviso fica logado e te identifica como responsável legal pelo upload.
            </span>
          </label>
        )}

        {ingestMutation.error && (
          <p className="text-sm text-destructive">{formatApiError(ingestMutation.error)}</p>
        )}

        <Button onClick={() => ingestMutation.mutate()} disabled={disabled}>
          {ingestMutation.isPending ? 'Processando…' : 'Indexar'}
        </Button>
      </CardContent>
    </Card>
  );
}

function KindIcon({ kind }: { kind: string }) {
  if (kind === 'url_fetch') return <Globe className="size-4 text-muted-foreground" />;
  if (kind === 'file_upload') return <FileText className="size-4 text-muted-foreground" />;
  return <FileText className="size-4 text-muted-foreground" />;
}

import { useState } from 'react';
import { useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { BookOpen, FileText, Trash2, UploadCloud } from 'lucide-react';
import { useClientId } from '@/lib/use-client-id';
import {
  deleteSquadKnowledgeSource,
  ingestSquadFile,
  ingestSquadText,
  listSquadKnowledgeSources,
  type RagSourceQualityClient,
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
  const queryClient = useQueryClient();

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
            Runbooks internos, convenções da casa, decisões arquiteturais. Visível apenas
            aos agentes desta squad.
          </p>
        </div>
      </header>

      <IngestPanel
        clientId={clientId}
        squadId={squadId}
        onIngested={() => queryClient.invalidateQueries({ queryKey: ['squad-knowledge', squadId] })}
      />

      <SourcesList clientId={clientId} squadId={squadId} />
    </div>
  );
}

function IngestPanel({
  clientId,
  squadId,
  onIngested,
}: {
  clientId: string;
  squadId: string;
  onIngested: () => void;
}) {
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
      onIngested();
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
          Apenas os agentes desta squad terão acesso. Conteúdo nunca é compartilhado cross-tenant.
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

function SourcesList({ clientId, squadId }: { clientId: string; squadId: string }) {
  const queryClient = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ['squad-knowledge', squadId],
    queryFn: () => listSquadKnowledgeSources(clientId, squadId),
  });

  const deleteMutation = useMutation({
    mutationFn: (sourceId: string) =>
      deleteSquadKnowledgeSource(clientId, squadId, sourceId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['squad-knowledge', squadId] }),
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Fontes indexadas</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading && <p className="text-sm text-muted-foreground">Carregando…</p>}
        {data && data.length === 0 && (
          <p className="text-sm italic text-muted-foreground">
            Nenhuma fonte ainda. Use o formulário acima.
          </p>
        )}
        {data && data.length > 0 && (
          <ul className="divide-y divide-border">
            {data.map((src) => (
              <li key={src.id} className="flex items-center justify-between gap-3 py-3">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <FileText className="size-4 text-muted-foreground" />
                    <span className="truncate text-sm font-medium">
                      {src.source_uri || src.source_hash.slice(0, 10)}
                    </span>
                  </div>
                  <div className="mt-1 flex flex-wrap gap-1 text-xs">
                    <Badge variant="outline">{src.source_quality}</Badge>
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
                    if (confirm('Remover esta fonte?')) {
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
  );
}

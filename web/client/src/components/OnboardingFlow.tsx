/**
 * Componente que orquestra: tela de loading (polling do OA) → recomendação
 * de agentes (consome manifest + propose-skills) → onConfirm com o payload
 * final pra parent chamar finalize-setup.
 *
 * Bloco E do roadmap stack-knowledge.
 */
import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { CheckCircle2, Edit3, Loader2, X } from 'lucide-react';
import {
  getOnboardingManifest,
  getOnboardingStatus,
  proposeSkills,
  runOnboardingAnalysis,
  type FinalizeSkillEntry,
  type OnboardingStatusResponse,
  type SkillTemplateDraft,
} from '@/lib/api';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Card, CardContent, CardDescription, CardHeader, CardTitle,
} from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { formatApiError } from '@/lib/utils';

interface Props {
  clientId: string;
  squadId: string;
  repoUrls: string[];
  /** Catalog default templates (BA/Architect/Reviewer — não geram drafts). */
  catalogSkillSlugs: { ba: string; architect: string; reviewer: string };
  onConfirm: (entries: FinalizeSkillEntry[]) => void;
  onBack: () => void;
}

export default function OnboardingFlow({
  clientId, squadId, repoUrls, catalogSkillSlugs, onConfirm, onBack,
}: Props) {
  // Dispara analysis na montagem (idempotente — backend não duplica).
  const startMutation = useMutation({
    mutationFn: () => runOnboardingAnalysis(clientId, squadId, repoUrls),
  });

  useEffect(() => {
    startMutation.mutate();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Polling do status
  const statusQuery = useQuery({
    queryKey: ['onboarding-status', squadId],
    queryFn: () => getOnboardingStatus(clientId, squadId),
    refetchInterval: (query) => {
      const s = query.state.data?.status;
      return s === 'completed' || s === 'failed' ? false : 5000;
    },
  });

  const status = statusQuery.data;

  if (!status || status.status === 'pending' || status.status === 'not_started' ||
      status.status === 'extracting' || status.status === 'analyzing' ||
      status.status === 'proposing') {
    return (
      <ProgressView
        status={status}
        onBack={onBack}
        onRefresh={() => statusQuery.refetch()}
      />
    );
  }

  if (status.status === 'failed') {
    return (
      <FailureView
        message={status.error_message ?? 'OA falhou sem mensagem.'}
        onBack={onBack}
      />
    );
  }

  // status === 'completed' → mostra recomendação
  return (
    <RecommendationView
      clientId={clientId}
      squadId={squadId}
      catalogSkillSlugs={catalogSkillSlugs}
      onBack={onBack}
      onConfirm={onConfirm}
    />
  );
}

function ProgressView({
  status,
  onBack,
  onRefresh,
}: {
  status: OnboardingStatusResponse | undefined;
  onBack: () => void;
  onRefresh: () => void;
}) {
  const steps = [
    { key: 'extracting', label: 'Lendo repositórios' },
    { key: 'analyzing', label: 'Detectando frameworks' },
    { key: 'proposing', label: 'Gerando manifesto' },
    { key: 'completed', label: 'Propondo agentes' },
  ];
  const currentIdx = status ? steps.findIndex((s) => s.key === status.status) : 0;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Loader2 className="size-5 animate-spin text-brand-500" />
          Analisando seu código…
        </CardTitle>
        <CardDescription>
          Nosso Onboarding Analyst está escaneando os repositórios pra entender sua
          stack e propor agentes direcionados. Leva entre 2 e 5 minutos.
          Você pode fechar essa página e voltar — retomamos onde estiver.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-2">
          {steps.map((step, idx) => {
            const done = idx < currentIdx;
            const active = idx === currentIdx;
            return (
              <div key={step.key} className="flex items-center gap-3 text-sm">
                {done ? (
                  <CheckCircle2 className="size-5 text-success" />
                ) : active ? (
                  <Loader2 className="size-5 animate-spin text-brand-500" />
                ) : (
                  <div className="size-5 rounded-full border-2 border-muted" />
                )}
                <span className={done ? 'text-muted-foreground' : active ? 'font-medium' : 'text-muted-foreground'}>
                  {step.label}
                </span>
                {active && status?.current_step && (
                  <span className="text-xs italic text-muted-foreground">
                    — {status.current_step}
                  </span>
                )}
              </div>
            );
          })}
        </div>

        {status && (
          <div className="rounded-md border border-border bg-muted/30 p-3 text-xs">
            <div>Progresso: {status.progress_pct}%</div>
            <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-muted">
              <div
                className="h-full bg-brand-500 transition-all"
                style={{ width: `${status.progress_pct}%` }}
              />
            </div>
          </div>
        )}

        <div className="flex gap-2">
          <Button variant="outline" onClick={onBack}>Voltar pro Dashboard</Button>
          <Button variant="ghost" onClick={onRefresh}>Atualizar agora</Button>
        </div>
      </CardContent>
    </Card>
  );
}

function FailureView({ message, onBack }: { message: string; onBack: () => void }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-destructive">
          <X className="size-5" /> Onboarding falhou
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-sm text-muted-foreground">{message}</p>
        <Button variant="outline" onClick={onBack}>Voltar</Button>
      </CardContent>
    </Card>
  );
}

function RecommendationView({
  clientId,
  squadId,
  catalogSkillSlugs,
  onBack,
  onConfirm,
}: {
  clientId: string;
  squadId: string;
  catalogSkillSlugs: { ba: string; architect: string; reviewer: string };
  onBack: () => void;
  onConfirm: (entries: FinalizeSkillEntry[]) => void;
}) {
  const manifestQuery = useQuery({
    queryKey: ['onboarding-manifest', squadId],
    queryFn: () => getOnboardingManifest(clientId, squadId),
  });

  const stackSlugs = useMemo(() => {
    if (!manifestQuery.data?.recommended_agents) return [];
    return Array.from(
      new Set(
        manifestQuery.data.recommended_agents
          .filter((a) => a.skill_template_slug?.startsWith('dev-'))
          .map((a) => {
            // recommend_agents.skill_template_slug ex: "dev-backend-python-fastapi-v1" → stack "python-fastapi"
            const slug = a.skill_template_slug.replace(/^dev-(?:backend-|frontend-)?/, '').replace(/-v\d+$/, '');
            return slug;
          }),
      ),
    );
  }, [manifestQuery.data]);

  const proposeMutation = useMutation({
    mutationFn: () =>
      proposeSkills(clientId, squadId, manifestQuery.data!, stackSlugs),
    onSuccess: (data) => {
      // Pre-marca todos por default
      const initial = new Set(data.drafts.map((_, i) => `draft-${i}`));
      initial.add('catalog-ba');
      initial.add('catalog-architect');
      // Reviewer desmarcado por default (decisão UX).
      setSelected(initial);
    },
  });

  useEffect(() => {
    if (manifestQuery.data && stackSlugs.length > 0) {
      proposeMutation.mutate();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [manifestQuery.data]);

  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [editingDraft, setEditingDraft] = useState<{ idx: number; draft: SkillTemplateDraft } | null>(null);
  const [draftEdits, setDraftEdits] = useState<Map<string, SkillTemplateDraft>>(new Map());

  if (manifestQuery.isLoading) return <p>Carregando manifesto…</p>;
  if (manifestQuery.error) return <p className="text-destructive">{formatApiError(manifestQuery.error)}</p>;

  const drafts = proposeMutation.data?.drafts ?? [];
  const detectedRepo = manifestQuery.data?.repos?.[0];

  const buildEntries = (): FinalizeSkillEntry[] => {
    const entries: FinalizeSkillEntry[] = [];
    drafts.forEach((draft, idx) => {
      const key = `draft-${idx}`;
      if (selected.has(key)) {
        const finalDraft = draftEdits.get(key) ?? draft;
        entries.push({
          draft_to_materialize: finalDraft,
          instance_name: finalDraft.name,
        });
      }
    });
    if (selected.has('catalog-ba')) {
      entries.push({ catalog_skill_slug: catalogSkillSlugs.ba, instance_name: 'BA Plataforma' });
    }
    if (selected.has('catalog-architect')) {
      entries.push({ catalog_skill_slug: catalogSkillSlugs.architect, instance_name: 'Architect Plataforma' });
    }
    if (selected.has('catalog-reviewer')) {
      entries.push({ catalog_skill_slug: catalogSkillSlugs.reviewer, instance_name: 'Reviewer Plataforma' });
    }
    return entries;
  };

  const toggleSelected = (key: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Agentes recomendados pra sua squad</CardTitle>
        <CardDescription>
          {detectedRepo
            ? `Detectamos: ${detectedRepo.framework} (linguagem: ${detectedRepo.primary_language})`
            : 'Detectamos sua stack e preparamos sugestões.'}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {proposeMutation.isPending && (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" /> Gerando propostas (Claude)…
          </div>
        )}
        {proposeMutation.error && (
          <p className="text-sm text-destructive">{formatApiError(proposeMutation.error)}</p>
        )}

        {/* Drafts (skills geradas) */}
        {drafts.map((draft, idx) => {
          const key = `draft-${idx}`;
          const edited = draftEdits.get(key);
          const current = edited ?? draft;
          return (
            <AgentRow
              key={key}
              selected={selected.has(key)}
              onToggle={() => toggleSelected(key)}
              variant="new"
              title={current.name}
              subtitle={`Skill gerada com base na sua stack · Modelo: ${current.model_alias}`}
              onEdit={() => setEditingDraft({ idx, draft: current })}
            />
          );
        })}

        {/* Catalog */}
        <AgentRow
          selected={selected.has('catalog-ba')}
          onToggle={() => toggleSelected('catalog-ba')}
          variant="catalog"
          title="BA Plataforma"
          subtitle="Refina demandas em ACs claros · Modelo: claude-sonnet-4-6"
        />
        <AgentRow
          selected={selected.has('catalog-architect')}
          onToggle={() => toggleSelected('catalog-architect')}
          variant="catalog"
          title="Architect Plataforma"
          subtitle="Decompõe demandas e delega aos Devs · Modelo: claude-opus-4-7 (coordinator)"
        />
        <AgentRow
          selected={selected.has('catalog-reviewer')}
          onToggle={() => toggleSelected('catalog-reviewer')}
          variant="catalog"
          title="Reviewer Plataforma"
          subtitle="Revisa PRs antes do humano (opcional)"
        />

        {proposeMutation.data && (
          <p className="text-xs italic text-muted-foreground">
            Total estimado de criação: US$ {Number(proposeMutation.data.api_call_cost_usd).toFixed(2)} (
            {drafts.length} skill(s) gerada(s) com Claude)
          </p>
        )}

        <div className="flex justify-between pt-3">
          <Button variant="outline" onClick={onBack}>◀ Voltar</Button>
          <Button onClick={() => onConfirm(buildEntries())} disabled={selected.size === 0}>
            Próximo ▶
          </Button>
        </div>
      </CardContent>

      {/* Modal de edição */}
      {editingDraft && (
        <SkillDraftEditor
          draft={editingDraft.draft}
          onCancel={() => setEditingDraft(null)}
          onSave={(updated) => {
            setDraftEdits((prev) => {
              const next = new Map(prev);
              next.set(`draft-${editingDraft.idx}`, updated);
              return next;
            });
            setEditingDraft(null);
          }}
          onRestore={() => {
            setDraftEdits((prev) => {
              const next = new Map(prev);
              next.delete(`draft-${editingDraft.idx}`);
              return next;
            });
            setEditingDraft(null);
          }}
        />
      )}
    </Card>
  );
}

function AgentRow({
  selected, onToggle, variant, title, subtitle, onEdit,
}: {
  selected: boolean;
  onToggle: () => void;
  variant: 'new' | 'catalog';
  title: string;
  subtitle: string;
  onEdit?: () => void;
}) {
  return (
    <div className="flex items-start justify-between gap-3 rounded-md border border-border p-3">
      <label className="flex flex-1 cursor-pointer items-start gap-3">
        <input
          type="checkbox"
          checked={selected}
          onChange={onToggle}
          className="mt-1"
        />
        <div className="flex-1">
          <div className="flex items-center gap-2">
            <span className="font-medium">{title}</span>
            <Badge variant={variant === 'new' ? 'warning' : 'secondary'} className="text-[10px]">
              {variant === 'new' ? '🔧 NOVO' : '✓ CATÁLOGO'}
            </Badge>
          </div>
          <p className="text-xs text-muted-foreground">{subtitle}</p>
        </div>
      </label>
      {onEdit && (
        <Button variant="ghost" size="sm" onClick={onEdit}>
          <Edit3 className="mr-1 size-3" /> Ver/editar
        </Button>
      )}
    </div>
  );
}

function SkillDraftEditor({
  draft, onCancel, onSave, onRestore,
}: {
  draft: SkillTemplateDraft;
  onCancel: () => void;
  onSave: (updated: SkillTemplateDraft) => void;
  onRestore: () => void;
}) {
  const [name, setName] = useState(draft.name);
  const [model, setModel] = useState(draft.model_alias);
  const [prompt, setPrompt] = useState(draft.system_prompt);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="flex max-h-[90vh] w-full max-w-3xl flex-col rounded-lg border border-border bg-card shadow-xl">
        <div className="flex items-center justify-between border-b border-border p-4">
          <h2 className="font-semibold">{draft.name}</h2>
          <Button variant="ghost" size="sm" onClick={onCancel}>
            <X className="size-4" />
          </Button>
        </div>
        <div className="flex-1 space-y-3 overflow-y-auto p-4">
          <div>
            <Label>Nome do agente</Label>
            <Input value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div>
            <Label>Modelo Claude</Label>
            <select
              className="mt-1 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
              value={model}
              onChange={(e) => setModel(e.target.value)}
            >
              <option value="claude-sonnet-4-6">claude-sonnet-4-6 (default)</option>
              <option value="claude-opus-4-7">claude-opus-4-7 (premium)</option>
              <option value="claude-haiku-4-5">claude-haiku-4-5 (economico)</option>
            </select>
          </div>
          <div>
            <Label>System Prompt (gerado, editável)</Label>
            <textarea
              rows={16}
              className="mt-1 w-full rounded-md border border-input bg-background px-3 py-2 font-mono text-xs"
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
            />
            <p className="mt-1 text-xs italic text-muted-foreground">
              💡 Esse prompt foi gerado pela Orbis com base na sua stack. Você pode editar tudo.
              Quando clicar "Salvar", o agente será provisionado com essa versão.
            </p>
          </div>
        </div>
        <div className="flex items-center justify-between gap-2 border-t border-border p-4">
          <Button variant="ghost" onClick={onRestore}>Restaurar original</Button>
          <div className="flex gap-2">
            <Button variant="outline" onClick={onCancel}>Cancelar</Button>
            <Button
              onClick={() => onSave({ ...draft, name, model_alias: model, system_prompt: prompt })}
            >
              Salvar
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}

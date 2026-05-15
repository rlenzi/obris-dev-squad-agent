import { useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useMutation, useQuery } from '@tanstack/react-query';
import {
  AlertCircle, AlertTriangle, ArrowLeft, ArrowRight,
  Brain, CheckCircle2, ChevronDown, ChevronUp, Code2,
  Layers, Loader2, Pencil, Shield, X,
} from 'lucide-react';

import { useClientId } from '@/lib/use-client-id';
import {
  createCredential, finalizeSetup, getOnboardingResult,
  type AnalysisAgentRec, type AnalysisAntiPattern, type AnalysisStack,
  type CredentialKind,
} from '@/lib/api';
import { formatApiError } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

/**
 * Tela 3 — Resultado e proposta de agentes (PR-7 do redesign).
 *
 * Renderiza o manifest produzido pelo OA scan v2 (PR-3):
 *   - Relatório em prosa (summary)
 *   - Stacks detectadas (com paths e conventions expansíveis)
 *   - Agentes recomendados como cards
 *     * Architect + Dev: marcados ESSENCIAIS (botão remover desabilitado)
 *     * BA + Reviewer: removíveis com modal de aviso inline
 *   - Diagrama do fluxo da pipeline (atualiza dinamicamente com remoções)
 *   - Anti-patterns como seção "Pontos de atenção"
 *   - Jira inline (se detectado em commits) com input de URL workspace +
 *     API token + projetos pré-marcados
 *   - Botão "Ativar minha squad" dispara finalizeSetup
 *
 * Escopo intencional (NÃO no PR-7, fica como TODO pós-implementação):
 *   - Modal "Editar prompt" do agente
 *   - Modal "Adicionar agente" com escolha de stack
 *
 * O cliente confirma os agentes recomendados como vêm. Edição de prompt
 * vai num PR futuro do roadmap.
 */

const JIRA_HOWTO_URL =
  'https://id.atlassian.com/manage-profile/security/api-tokens';

const AGENT_TIER_META: Record<
  AnalysisAgentRec['tier'],
  { icon: React.ReactNode; label: string; description: string }
> = {
  ba: {
    icon: <Brain className="h-5 w-5" />,
    label: 'Business Analyst',
    description: 'Refina demandas em ACs claras antes do Architect planejar',
  },
  architect: {
    icon: <Layers className="h-5 w-5" />,
    label: 'Architect',
    description: 'Decompõe demandas e delega aos Devs',
  },
  dev: {
    icon: <Code2 className="h-5 w-5" />,
    label: 'Dev',
    description: 'Especialista na stack — implementa o código',
  },
  reviewer: {
    icon: <Shield className="h-5 w-5" />,
    label: 'Reviewer',
    description: 'Revisa PRs antes do humano (opcional)',
  },
};


export default function SetupResultPage() {
  const { squadId } = useParams<{ squadId: string }>();
  const navigate = useNavigate();
  const clientId = useClientId();

  const manifestQuery = useQuery({
    queryKey: ['onboarding-result', clientId, squadId],
    queryFn: () => getOnboardingResult(clientId, squadId!),
    enabled: Boolean(squadId),
  });

  // Estado local — agentes selecionados (cliente pode remover BA/Reviewer)
  const [removedAgents, setRemovedAgents] = useState<Set<string>>(new Set());
  // Jira
  const [jiraUrl, setJiraUrl] = useState('');
  const [jiraToken, setJiraToken] = useState('');
  const [jiraProjects, setJiraProjects] = useState<string[]>([]);
  const [jiraHowtoOpen, setJiraHowtoOpen] = useState(false);
  // Confirmações de remoção
  const [confirmRemove, setConfirmRemove] = useState<string | null>(null);
  // Erros
  const [activateError, setActivateError] = useState<string | null>(null);

  // Pré-popula jira_projects quando manifest chega
  useMemo(() => {
    if (manifestQuery.data && jiraProjects.length === 0) {
      setJiraProjects([...manifestQuery.data.jira_projects]);
    }
  }, [manifestQuery.data, jiraProjects.length]);

  const activateMutation = useMutation({
    mutationFn: async () => {
      if (!manifestQuery.data || !squadId) {
        throw new Error('Manifest ainda não carregado.');
      }

      // 1. Conectar Jira (se cliente preencheu)
      if (jiraToken.trim()) {
        try {
          await createCredential(clientId, {
            kind: 'jira_token' as CredentialKind,
            name: 'main',
            value: jiraToken.trim(),
          });
        } catch (err: unknown) {
          // 409 → token já existe, segue
          const msg = formatApiError(err, '');
          if (!msg.toLowerCase().includes('ja existe')) {
            throw err;
          }
        }
      }

      // 2. Provisiona agents via finalize-setup.
      // Estratégia: pra cada recommended_agent NÃO removido,
      // mapeia pra entrada do FinalizeSetupRequest. Pra BA/Architect/
      // Reviewer (tiers com catálogo), usa slug do catálogo. Pra Dev
      // (paramétrico), o backend legado infere via skill_template_slug
      // do manifest — fluxo simplificado: usa slug literal.
      const accepted = manifestQuery.data.recommended_agents.filter(
        (a) => !removedAgents.has(agentKey(a)),
      );
      const entries = accepted.map((a) => ({
        catalog_skill_slug: catalogSlugFor(a),
        instance_name: `${AGENT_TIER_META[a.tier].label}${a.stack_slug ? ` (${a.stack_slug})` : ''}`,
        domain_business: 'general',
      }));
      await finalizeSetup(clientId, squadId, entries);

      return { squadId };
    },
    onSuccess: ({ squadId }) => {
      navigate(`/setup/ready/${squadId}`);
    },
    onError: (err) => {
      setActivateError(formatApiError(err, 'Falha ao ativar a squad.'));
    },
  });

  if (manifestQuery.isLoading) {
    return (
      <div className="mx-auto max-w-2xl py-12 px-6 text-center text-sm text-muted-foreground">
        <Loader2 className="mx-auto h-6 w-6 animate-spin" />
        <p className="mt-3">Carregando o que encontrei…</p>
      </div>
    );
  }

  if (manifestQuery.isError || !manifestQuery.data) {
    return (
      <div className="mx-auto max-w-2xl py-12 px-6">
        <p className="text-sm text-destructive">
          {formatApiError(manifestQuery.error, 'Não consegui carregar o resultado da análise.')}
        </p>
        <Button
          variant="outline"
          className="mt-4"
          onClick={() => navigate(`/setup/analyzing/${squadId}`)}
        >
          <ArrowLeft className="mr-1 h-3 w-3" />
          Voltar pra tela de análise
        </Button>
      </div>
    );
  }

  const manifest = manifestQuery.data;
  const acceptedAgents = manifest.recommended_agents.filter(
    (a) => !removedAgents.has(agentKey(a)),
  );

  return (
    <div className="mx-auto max-w-3xl py-12 px-6">
      <header className="mb-8 space-y-2">
        <div className="flex items-center gap-2">
          <CheckCircle2 className="h-6 w-6 text-emerald-600 dark:text-emerald-400" />
          <h1 className="text-2xl font-semibold tracking-tight">
            Análise concluída
          </h1>
        </div>
      </header>

      <section className="mb-10 space-y-3">
        <h2 className="text-lg font-medium">Olha o que encontrei no seu projeto:</h2>
        <div className="rounded-md border bg-muted/30 p-4 text-sm leading-relaxed">
          {manifest.summary}
        </div>
      </section>

      {manifest.stacks.length > 0 && (
        <section className="mb-10 space-y-3">
          <h2 className="text-lg font-medium">Stacks detectadas</h2>
          <div className="grid gap-3">
            {manifest.stacks.map((stack) => (
              <StackCard key={stack.slug} stack={stack} />
            ))}
          </div>
        </section>
      )}

      <section className="mb-10 space-y-3">
        <h2 className="text-lg font-medium">
          Pra esse projeto, sugiro estes agentes:
        </h2>
        <div className="grid gap-3">
          {manifest.recommended_agents.map((agent) => {
            const key = agentKey(agent);
            const isRemoved = removedAgents.has(key);
            const essential = agent.tier === 'architect' || agent.tier === 'dev';
            return (
              <AgentCard
                key={key}
                agent={agent}
                isRemoved={isRemoved}
                essential={essential}
                onRemoveRequested={() => setConfirmRemove(key)}
                onUndoRemove={() =>
                  setRemovedAgents((s) => {
                    const next = new Set(s);
                    next.delete(key);
                    return next;
                  })
                }
              />
            );
          })}
        </div>
        <p className="mt-3 text-center text-xs text-muted-foreground">
          Editar prompt do agente e adicionar agentes ao catálogo serão habilitados em
          um próximo PR. Pra essa versão, o catálogo recomendado vai como está.
        </p>
      </section>

      {confirmRemove !== null && (
        <RemovalConfirmation
          agentKey={confirmRemove}
          agents={manifest.recommended_agents}
          onCancel={() => setConfirmRemove(null)}
          onConfirm={() => {
            setRemovedAgents((s) => new Set(s).add(confirmRemove));
            setConfirmRemove(null);
          }}
        />
      )}

      <section className="mb-10 space-y-3">
        <h2 className="text-lg font-medium">Como sua squad vai trabalhar</h2>
        <PipelineDiagram agents={acceptedAgents} />
      </section>

      {manifest.anti_patterns_detected.length > 0 && (
        <section className="mb-10 space-y-3">
          <h2 className="text-lg font-medium">Pontos de atenção que notei</h2>
          <p className="text-xs text-muted-foreground">
            Não são bloqueadores. Os agentes vão ser instruídos a evitar
            replicar esses padrões — você pode revisar com calma depois.
          </p>
          <div className="grid gap-3">
            {manifest.anti_patterns_detected.map((ap, i) => (
              <AntiPatternCard key={i} ap={ap} />
            ))}
          </div>
        </section>
      )}

      <section className="mb-10 space-y-3">
        <h2 className="text-lg font-medium">Conectar seu Jira</h2>
        {manifest.jira_projects.length > 0 ? (
          <p className="text-xs text-muted-foreground">
            Vi referências aos projetos{' '}
            <code className="rounded bg-muted px-1">
              {manifest.jira_projects.join(', ')}
            </code>{' '}
            nos seus commits. Se você conectar agora, os agentes vão receber
            demandas direto dali. Pode pular e conectar depois.
          </p>
        ) : (
          <p className="text-xs text-muted-foreground">
            Não encontrei referências Jira no histórico do repo. Se você usa
            Jira mesmo assim, conecte agora — senão pule.
          </p>
        )}

        <div className="space-y-3 rounded-md border p-4">
          <div className="space-y-1.5">
            <Label htmlFor="jira-url">URL do workspace Jira</Label>
            <Input
              id="jira-url"
              type="url"
              placeholder="https://sua-empresa.atlassian.net"
              value={jiraUrl}
              onChange={(e) => setJiraUrl(e.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="jira-token">API token</Label>
            <Input
              id="jira-token"
              type="password"
              placeholder="ATATT..."
              value={jiraToken}
              onChange={(e) => setJiraToken(e.target.value)}
            />
            <button
              type="button"
              onClick={() => setJiraHowtoOpen((v) => !v)}
              className="mt-1 flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
            >
              {jiraHowtoOpen ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
              Como gerar um API token (1 min)
            </button>
            {jiraHowtoOpen && (
              <div className="mt-2 space-y-2 rounded-md border bg-background p-3 text-xs">
                <p>
                  1. Vá em{' '}
                  <a
                    href={JIRA_HOWTO_URL}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-primary hover:underline"
                  >
                    id.atlassian.com → Manage profile → Security → API tokens
                  </a>.
                </p>
                <p>2. Click <strong>Create API token</strong>.</p>
                <p>3. Dê um nome (ex: <code>dev-autonomo</code>) e crie.</p>
                <p>4. Copie e cole aqui.</p>
              </div>
            )}
          </div>
          {manifest.jira_projects.length > 0 && (
            <div className="space-y-2">
              <Label>Projetos cobertos</Label>
              <div className="flex flex-wrap gap-2">
                {manifest.jira_projects.map((p) => (
                  <label
                    key={p}
                    className="flex items-center gap-1.5 rounded-md border bg-muted/40 px-2 py-1 text-xs"
                  >
                    <input
                      type="checkbox"
                      checked={jiraProjects.includes(p)}
                      onChange={(e) => {
                        setJiraProjects((cur) =>
                          e.target.checked
                            ? [...cur, p]
                            : cur.filter((x) => x !== p),
                        );
                      }}
                    />
                    <code>{p}</code>
                  </label>
                ))}
              </div>
            </div>
          )}
          <p className="text-xs text-muted-foreground">
            🔒 Token cifrado com a chave da sua tenant. Pode revogar a
            qualquer momento.
          </p>
        </div>
      </section>

      {activateError && (
        <div className="mb-4 flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive">
          <AlertCircle className="mt-0.5 h-4 w-4 flex-shrink-0" />
          <span>{activateError}</span>
        </div>
      )}

      <div className="flex justify-end gap-2">
        <Button variant="outline" onClick={() => navigate('/setup/start')}>
          <ArrowLeft className="mr-1 h-4 w-4" />
          Voltar
        </Button>
        <Button
          onClick={() => {
            setActivateError(null);
            activateMutation.mutate();
          }}
          disabled={
            activateMutation.isPending ||
            acceptedAgents.length === 0
          }
        >
          {activateMutation.isPending ? (
            <>
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              Ativando squad…
            </>
          ) : (
            <>
              Ativar minha squad
              <ArrowRight className="ml-2 h-4 w-4" />
            </>
          )}
        </Button>
      </div>
    </div>
  );
}


// ---------------------------------------------------------------------------
// Helpers + sub-componentes
// ---------------------------------------------------------------------------


function agentKey(a: AnalysisAgentRec): string {
  return `${a.tier}:${a.stack_slug ?? '_'}`;
}


function catalogSlugFor(a: AnalysisAgentRec): string {
  // Mapeamento simples: cada tier do recommended_agent vira slug do catálogo.
  // Devs (paramétricos) usam um catalog slug genérico por enquanto — o
  // backend legacy finalize-setup espera catalog_skill_slug. Edição
  // de skill paramétrico vira melhoria futura.
  if (a.tier === 'ba') return 'ba-generic-v1';
  if (a.tier === 'architect') return 'architect-generic-v1';
  if (a.tier === 'reviewer') return 'reviewer-generic-v1';
  // Dev — usa stack_slug pra inferir skill. Se backend não tiver, vai dar 404.
  return `dev-${a.stack_slug ?? 'generic'}-v1`;
}


function StackCard({ stack }: { stack: AnalysisStack }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="rounded-md border p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1">
          <h3 className="text-sm font-medium">{stack.name}</h3>
          <p className="mt-1 text-xs text-muted-foreground">
            <code>{stack.paths.join(' · ')}</code>
            {stack.framework && (
              <>
                {' · '}
                {stack.framework}
                {stack.framework_version && ` ${stack.framework_version}`}
              </>
            )}
          </p>
        </div>
        <button
          type="button"
          className="text-xs text-muted-foreground hover:text-foreground"
          onClick={() => setOpen((v) => !v)}
        >
          {open ? (
            <>
              <ChevronUp className="inline h-3 w-3" /> Ocultar convenções
            </>
          ) : (
            <>
              <ChevronDown className="inline h-3 w-3" /> Ver convenções
            </>
          )}
        </button>
      </div>
      {open && (
        <div className="mt-3 grid gap-3 border-t pt-3 md:grid-cols-2">
          <ConventionsBlock
            title="Observado no código"
            data={stack.conventions.observed_patterns}
          />
          <ConventionsBlock
            title="Recomendado pros agentes"
            data={stack.conventions.recommended_for_agents}
            prescriptive
          />
        </div>
      )}
    </div>
  );
}


function ConventionsBlock({
  title, data, prescriptive = false,
}: {
  title: string;
  data: Record<string, string>;
  prescriptive?: boolean;
}) {
  return (
    <div className="space-y-2">
      <h4 className={`text-xs font-medium ${prescriptive ? 'text-primary' : ''}`}>
        {title}
      </h4>
      <dl className="space-y-1.5 text-xs">
        {Object.entries(data).map(([key, value]) => (
          <div key={key}>
            <dt className="font-medium capitalize text-foreground/70">
              {key.replace(/_/g, ' ')}
            </dt>
            <dd className="text-muted-foreground">{value}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}


function AgentCard({
  agent, isRemoved, essential, onRemoveRequested, onUndoRemove,
}: {
  agent: AnalysisAgentRec;
  isRemoved: boolean;
  essential: boolean;
  onRemoveRequested: () => void;
  onUndoRemove: () => void;
}) {
  const meta = AGENT_TIER_META[agent.tier];
  return (
    <div
      className={`rounded-md border p-4 transition ${
        isRemoved ? 'border-dashed bg-muted/20 opacity-50' : ''
      }`}
    >
      <div className="flex items-start gap-3">
        <div className="rounded-md bg-muted p-2 text-foreground/70">
          {meta.icon}
        </div>
        <div className="flex-1">
          <div className="flex items-center justify-between gap-2">
            <h3 className="text-sm font-semibold">
              {meta.label}
              {agent.stack_slug && (
                <span className="ml-2 text-xs font-normal text-muted-foreground">
                  · {agent.stack_slug}
                </span>
              )}
            </h3>
            <div className="flex items-center gap-2">
              {essential && (
                <span className="rounded-full bg-primary/10 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider text-primary">
                  Essencial
                </span>
              )}
            </div>
          </div>
          <p className="mt-1 text-xs text-muted-foreground">
            {meta.description}
          </p>
          {agent.rationale && (
            <p className="mt-2 text-xs text-foreground/70">
              <em>{agent.rationale}</em>
            </p>
          )}
          <div className="mt-3 flex gap-2">
            <Button
              size="sm"
              variant="ghost"
              className="h-7 px-2 text-xs text-muted-foreground"
              disabled
              title="Edição de prompt habilitada em um próximo PR"
            >
              <Pencil className="mr-1 h-3 w-3" />
              Editar (em breve)
            </Button>
            {!isRemoved && !essential && (
              <Button
                size="sm"
                variant="ghost"
                className="h-7 px-2 text-xs text-muted-foreground hover:text-destructive"
                onClick={onRemoveRequested}
              >
                <X className="mr-1 h-3 w-3" />
                Remover
              </Button>
            )}
            {!isRemoved && essential && (
              <span className="text-[10px] text-muted-foreground">
                Não removível — pipeline depende dele
              </span>
            )}
            {isRemoved && (
              <Button
                size="sm"
                variant="ghost"
                className="h-7 px-2 text-xs"
                onClick={onUndoRemove}
              >
                Desfazer remoção
              </Button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}


function RemovalConfirmation({
  agentKey, agents, onCancel, onConfirm,
}: {
  agentKey: string;
  agents: AnalysisAgentRec[];
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const agent = agents.find((a) => `${a.tier}:${a.stack_slug ?? '_'}` === agentKey);
  if (!agent) return null;

  const consequence =
    agent.tier === 'ba'
      ? 'Sem BA, demandas do Jira vão direto pro Architect sem refinement prévio. Você vai precisar refinar manualmente cada issue antes, ou o Architect vai planejar com a descrição original (geralmente menos preciso).'
      : 'Sem Reviewer, PRs vão direto pro humano sem auditoria prévia automatizada. Você ganha controle total mas perde um quality gate barato (Reviewer custa ~25× menos que Dev).';

  return (
    <div className="mb-6 rounded-md border border-destructive/40 bg-destructive/5 p-4">
      <div className="flex items-start gap-2">
        <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0 text-destructive" />
        <div className="space-y-2 text-sm">
          <p className="font-medium">
            Remover {AGENT_TIER_META[agent.tier].label}?
          </p>
          <p className="text-xs text-muted-foreground">{consequence}</p>
          <div className="flex gap-2 pt-1">
            <Button size="sm" variant="destructive" onClick={onConfirm}>
              Remover assim mesmo
            </Button>
            <Button size="sm" variant="ghost" onClick={onCancel}>
              Voltar
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}


function PipelineDiagram({ agents }: { agents: AnalysisAgentRec[] }) {
  const hasBA = agents.some((a) => a.tier === 'ba');
  const hasReviewer = agents.some((a) => a.tier === 'reviewer');
  const devs = agents.filter((a) => a.tier === 'dev');

  return (
    <div className="rounded-md border bg-muted/20 p-4">
      <div className="space-y-2 font-mono text-xs text-foreground/80">
        <div>📋 Issue chega (Jira ou painel)</div>
        <div className="pl-4 text-muted-foreground">↓</div>
        {hasBA ? (
          <>
            <div>🧠 BA refina em ACs claras</div>
            <div className="pl-4 text-muted-foreground">↓</div>
          </>
        ) : (
          <div className="text-amber-600 dark:text-amber-400">
            (sem BA — demanda vai direto pro Architect sem refinement)
          </div>
        )}
        <div>🏗 Architect planeja e delega</div>
        <div className="pl-4 text-muted-foreground">↓</div>
        {devs.length > 0 ? (
          <div>
            {devs.length > 1 ? `${devs.length} Devs trabalham em paralelo: ` : '💻 Dev trabalha: '}
            {devs.map((d, i) => (
              <span key={d.stack_slug ?? i}>
                <code className="rounded bg-muted px-1">{d.stack_slug ?? 'generic'}</code>
                {i < devs.length - 1 ? ', ' : ''}
              </span>
            ))}
          </div>
        ) : (
          <div className="text-destructive">(sem Dev — pipeline incompleta)</div>
        )}
        <div className="pl-4 text-muted-foreground">↓</div>
        <div>📥 PR aberto</div>
        <div className="pl-4 text-muted-foreground">↓</div>
        {hasReviewer ? (
          <>
            <div>🔍 Reviewer audita o PR</div>
            <div className="pl-4 text-muted-foreground">↓</div>
          </>
        ) : (
          <div className="text-amber-600 dark:text-amber-400">
            (sem Reviewer — PR vai direto pro humano sem auditoria automatizada)
          </div>
        )}
        <div>👤 Você aprova ou ajusta</div>
      </div>
    </div>
  );
}


function AntiPatternCard({ ap }: { ap: AnalysisAntiPattern }) {
  const severityColor =
    ap.severity === 'high'
      ? 'border-destructive/40 bg-destructive/5'
      : ap.severity === 'medium'
        ? 'border-amber-500/40 bg-amber-500/5'
        : 'border-muted bg-muted/20';
  return (
    <div className={`rounded-md border p-4 ${severityColor}`}>
      <div className="flex items-start gap-2">
        <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0" />
        <div className="flex-1 space-y-2">
          <p className="text-sm font-medium">{ap.issue}</p>
          <p className="text-xs">
            <span className="font-medium">Severidade:</span> {ap.severity}
          </p>
          <div className="text-xs">
            <span className="font-medium">Locais:</span>{' '}
            {ap.occurrences.slice(0, 5).map((o, i) => (
              <code key={i} className="ml-1 rounded bg-background/60 px-1">
                {o}
              </code>
            ))}
            {ap.occurrences.length > 5 && (
              <span className="ml-1 text-muted-foreground">
                e mais {ap.occurrences.length - 5}
              </span>
            )}
          </div>
          <p className="text-xs text-muted-foreground">
            <span className="font-medium text-foreground/80">Recomendação:</span>{' '}
            {ap.recommendation}
          </p>
        </div>
      </div>
    </div>
  );
}

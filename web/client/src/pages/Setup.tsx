import { useState, type FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import {
  Bot,
  Check,
  ChevronLeft,
  ChevronRight,
  Flame,
  GitBranch,
  KeyRound,
  Sparkles,
} from 'lucide-react';
import { useClientId } from '@/lib/use-client-id';
import { useAuth } from '@/lib/auth';
import {
  createAgent,
  createCredential,
  createSquad,
  fetchSkillTemplates,
  updateManifest,
  type AgentInstanceCreate,
  type CredentialKind,
  type ManifestContent,
  type SkillTemplate,
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
import { cn, formatApiError } from '@/lib/utils';

interface CredsForm {
  github_token: string;
  jira_token: string;
}

interface SquadForm {
  slug: string;
  name: string;
  domain: string;
  description: string;
}

interface ManifestForm {
  repos: string;
  jira_projects: string;
}

interface AgentDraft {
  templateId: string;
  name: string;
}

const STEPS = ['Boas-vindas', 'Credenciais', 'Squad', 'Manifesto', 'Agentes', 'Revisão'] as const;

export default function SetupPage() {
  const clientId = useClientId();
  const { me } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [step, setStep] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const [creds, setCreds] = useState<CredsForm>({
    github_token: '',
    jira_token: '',
  });

  const [squad, setSquad] = useState<SquadForm>({
    slug: '',
    name: '',
    domain: '',
    description: '',
  });

  const [manifest, setManifest] = useState<ManifestForm>({
    repos: '',
    jira_projects: '',
  });

  const [agents, setAgents] = useState<AgentDraft[]>([]);

  const tplQuery = useQuery({
    queryKey: ['skill-templates'],
    queryFn: fetchSkillTemplates,
  });

  const setupMutation = useMutation({
    mutationFn: async () => {
      // 1. Credenciais (opcional, mas o esperado)
      if (creds.github_token.trim()) {
        await createCredential(clientId, {
          kind: 'github_token' as CredentialKind,
          name: 'main',
          value: creds.github_token.trim(),
        });
      }
      if (creds.jira_token.trim()) {
        await createCredential(clientId, {
          kind: 'jira_token' as CredentialKind,
          name: 'main',
          value: creds.jira_token.trim(),
        });
      }

      // 2. Squad
      const payloadSquad: SquadCreate = {
        slug: squad.slug,
        name: squad.name,
        domain: squad.domain || undefined,
        description: squad.description || undefined,
      };
      const created = await createSquad(clientId, payloadSquad);

      // 3. Manifesto
      const content: ManifestContent = {
        owns: {
          repos: manifest.repos.split(/\s*[\n,]\s*/).map((s) => s.trim()).filter(Boolean),
          jira_projects: manifest.jira_projects
            .split(/\s*[\n,]\s*/)
            .map((s) => s.trim())
            .filter(Boolean),
        },
      };
      await updateManifest(clientId, created.id, content);

      // 4. Agentes
      for (const draft of agents) {
        if (!draft.templateId || !draft.name.trim()) continue;
        const payload: AgentInstanceCreate = {
          skill_template_id: draft.templateId,
          name: draft.name.trim(),
        };
        await createAgent(clientId, created.id, payload);
      }

      return created;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['squads', clientId] });
      navigate('/dashboard');
    },
    onError: (err: unknown) => {
      setError(formatApiError(err, 'Falha na configuração inicial'));
    },
  });

  function canAdvance(): boolean {
    if (step === 0) return true;
    if (step === 1) {
      // Credenciais técnicas opcional, mas avisamos no review se vazio
      return true;
    }
    if (step === 2) {
      return Boolean(squad.slug && squad.name);
    }
    if (step === 3) {
      // Manifesto pode ser vazio pra primeira squad — agente é restrito pelo enforcement
      return true;
    }
    if (step === 4) {
      return agents.every((d) => d.templateId && d.name.trim());
    }
    return true;
  }

  function handleNext(event: FormEvent) {
    event.preventDefault();
    setError(null);
    if (step < STEPS.length - 1) {
      setStep(step + 1);
    } else {
      setupMutation.mutate();
    }
  }

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div className="flex items-center gap-3">
        <div className="grid size-14 place-items-center rounded-lg bg-brand-500/10">
          <Flame className="size-7 text-brand-500" />
        </div>
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">
            Configuração inicial
          </h1>
          <p className="text-muted-foreground">
            Bem-vindo, {me?.user.full_name?.split(' ')[0]}. Em poucos passos seu
            tenant {me?.memberships?.[0]?.client_name} fica pronto pra rodar
            agentes.
          </p>
        </div>
      </div>

      <StepBar current={step} />

      <Card>
        <CardContent className="pt-6">
          <form onSubmit={handleNext} className="space-y-4">
            {step === 0 && <StepWelcome />}
            {step === 1 && <StepCreds form={creds} setForm={setCreds} />}
            {step === 2 && <StepSquad form={squad} setForm={setSquad} />}
            {step === 3 && <StepManifest form={manifest} setForm={setManifest} />}
            {step === 4 && (
              <StepAgents
                drafts={agents}
                setDrafts={setAgents}
                templates={tplQuery.data ?? []}
                isLoading={tplQuery.isLoading}
              />
            )}
            {step === 5 && (
              <StepReview
                creds={creds}
                squad={squad}
                manifest={manifest}
                agents={agents}
                templates={tplQuery.data ?? []}
              />
            )}

            {error && <p className="text-sm text-destructive">{error}</p>}

            <div className="flex items-center justify-between border-t pt-4">
              <Button
                type="button"
                variant="ghost"
                size="sm"
                disabled={step === 0 || setupMutation.isPending}
                onClick={() => {
                  setError(null);
                  setStep(Math.max(0, step - 1));
                }}
              >
                <ChevronLeft className="size-4" /> Voltar
              </Button>
              <Button
                type="submit"
                disabled={!canAdvance() || setupMutation.isPending}
              >
                {step < STEPS.length - 1 ? (
                  <>
                    Próximo <ChevronRight className="size-4" />
                  </>
                ) : setupMutation.isPending ? (
                  'Configurando…'
                ) : (
                  <>
                    <Check className="size-4" /> Concluir
                  </>
                )}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}

function StepBar({ current }: { current: number }) {
  return (
    <ol className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs">
      {STEPS.map((label, idx) => {
        const state =
          idx < current ? 'done' : idx === current ? 'active' : 'pending';
        return (
          <li key={label} className="flex items-center gap-2">
            <span
              className={cn(
                'grid size-6 place-items-center rounded-full font-mono',
                state === 'done' && 'bg-brand-500 text-white',
                state === 'active' &&
                  'bg-brand-500/15 text-brand-500 ring-1 ring-brand-500',
                state === 'pending' && 'bg-muted text-muted-foreground',
              )}
            >
              {state === 'done' ? <Check className="size-3.5" /> : idx + 1}
            </span>
            <span
              className={cn(
                state === 'active' && 'font-medium text-foreground',
                state !== 'active' && 'text-muted-foreground',
              )}
            >
              {label}
            </span>
            {idx < STEPS.length - 1 && (
              <span className="mx-1 text-muted-foreground">·</span>
            )}
          </li>
        );
      })}
    </ol>
  );
}

function StepWelcome() {
  return (
    <div className="space-y-3">
      <h2 className="text-xl font-semibold">Bem-vindo à plataforma</h2>
      <p className="text-sm text-muted-foreground">
        Esse assistente vai te ajudar a configurar seu tenant em cinco passos
        rápidos:
      </p>
      <ol className="list-decimal space-y-1 pl-6 text-sm">
        <li>
          <strong>Credenciais</strong> — tokens do GitHub e Jira (sem isso os
          agentes não funcionam).
        </li>
        <li>
          <strong>Squad</strong> — primeiro time (backend, frontend, etc).
        </li>
        <li>
          <strong>Manifesto</strong> — quais repos e projetos Jira essa squad
          tem permissão de tocar.
        </li>
        <li>
          <strong>Agentes</strong> — quem vai trabalhar nessa squad (BA,
          Architect, Dev, Reviewer, Onboarding Analyst).
        </li>
        <li>
          <strong>Revisão</strong> — confere tudo e cria.
        </li>
      </ol>
      <p className="text-sm text-muted-foreground">
        Tudo isso pode ser ajustado depois nas telas do painel.
      </p>
    </div>
  );
}

function StepCreds({
  form,
  setForm,
}: {
  form: CredsForm;
  setForm: (f: CredsForm) => void;
}) {
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <KeyRound className="size-5 text-brand-500" />
        <h2 className="text-lg font-semibold">Credenciais técnicas</h2>
      </div>
      <p className="text-sm text-muted-foreground">
        Os tokens são guardados criptografados no vault. Você pode editar ou
        rotacionar depois na aba <strong>Credenciais</strong>.
      </p>

      <div className="space-y-1.5">
        <Label htmlFor="gh-token">GitHub token</Label>
        <Input
          id="gh-token"
          type="password"
          value={form.github_token}
          onChange={(e) => setForm({ ...form, github_token: e.target.value })}
          placeholder="ghp_… ou github_pat_…"
        />
        <p className="text-xs text-muted-foreground">
          Personal Access Token com escopo <code>repo</code>,{' '}
          <code>workflow</code>, <code>pull_request</code>.
        </p>
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="jira-token">Jira API token</Label>
        <Input
          id="jira-token"
          type="password"
          value={form.jira_token}
          onChange={(e) => setForm({ ...form, jira_token: e.target.value })}
          placeholder="ATATT…"
        />
        <p className="text-xs text-muted-foreground">
          Gere em id.atlassian.com → Manage API tokens. A URL do workspace e
          email são preenchidos no perfil do cliente.
        </p>
      </div>
    </div>
  );
}

function StepSquad({
  form,
  setForm,
}: {
  form: SquadForm;
  setForm: (f: SquadForm) => void;
}) {
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <GitBranch className="size-5 text-brand-500" />
        <h2 className="text-lg font-semibold">Primeira squad</h2>
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="sq-slug">Slug *</Label>
        <Input
          id="sq-slug"
          value={form.slug}
          onChange={(e) =>
            setForm({
              ...form,
              slug: e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, '-'),
            })
          }
          placeholder="plataforma"
          required
          pattern="^[a-z0-9][a-z0-9-]*$"
        />
        <p className="text-xs text-muted-foreground">
          Identificador único da squad (a-z, 0-9, hífen).
        </p>
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="sq-name">Nome *</Label>
        <Input
          id="sq-name"
          value={form.name}
          onChange={(e) => setForm({ ...form, name: e.target.value })}
          placeholder="Squad Plataforma"
          required
        />
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="sq-domain">Domínio</Label>
        <Input
          id="sq-domain"
          value={form.domain}
          onChange={(e) => setForm({ ...form, domain: e.target.value })}
          placeholder="backend, frontend, mobile, fullstack…"
        />
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="sq-desc">Descrição</Label>
        <Input
          id="sq-desc"
          value={form.description}
          onChange={(e) => setForm({ ...form, description: e.target.value })}
          placeholder="Time responsável por…"
        />
      </div>
    </div>
  );
}

function StepManifest({
  form,
  setForm,
}: {
  form: ManifestForm;
  setForm: (f: ManifestForm) => void;
}) {
  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold">Manifesto da squad</h2>
      <p className="text-sm text-muted-foreground">
        Define o que essa squad é dona — qualquer agente dela só pode operar
        nesses recursos. Pode editar depois na tela da squad.
      </p>

      <div className="space-y-1.5">
        <Label htmlFor="m-repos">Repositórios (um por linha ou vírgula)</Label>
        <textarea
          id="m-repos"
          value={form.repos}
          onChange={(e) => setForm({ ...form, repos: e.target.value })}
          placeholder="https://github.com/acme/web-app&#10;https://github.com/acme/api"
          className="min-h-[80px] w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-sm placeholder:text-muted-foreground"
        />
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="m-jira">Projetos Jira (chaves, separadas por vírgula)</Label>
        <Input
          id="m-jira"
          value={form.jira_projects}
          onChange={(e) => setForm({ ...form, jira_projects: e.target.value })}
          placeholder="LEO, ACME, ADM"
        />
      </div>
    </div>
  );
}

function StepAgents({
  drafts,
  setDrafts,
  templates,
  isLoading,
}: {
  drafts: AgentDraft[];
  setDrafts: (d: AgentDraft[]) => void;
  templates: SkillTemplate[];
  isLoading: boolean;
}) {
  function addDraft() {
    setDrafts([...drafts, { templateId: '', name: '' }]);
  }

  function updateDraft(idx: number, patch: Partial<AgentDraft>) {
    const copy = [...drafts];
    copy[idx] = { ...copy[idx], ...patch };
    setDrafts(copy);
  }

  function removeDraft(idx: number) {
    setDrafts(drafts.filter((_, i) => i !== idx));
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <Sparkles className="size-5 text-brand-500" />
        <h2 className="text-lg font-semibold">Primeiros agentes</h2>
      </div>
      <p className="text-sm text-muted-foreground">
        Escolha quem vai trabalhar nessa squad. Você pode adicionar/remover
        depois.
      </p>

      {isLoading && (
        <p className="text-sm text-muted-foreground">Carregando skills…</p>
      )}

      {drafts.length === 0 && !isLoading && (
        <div className="rounded-md border border-dashed py-6 text-center text-sm text-muted-foreground">
          Nenhum agente — adicione pelo menos um.
        </div>
      )}

      <div className="space-y-2">
        {drafts.map((d, idx) => (
          <div
            key={idx}
            className="grid grid-cols-1 gap-2 rounded-md border bg-muted/30 p-3 sm:grid-cols-[1fr_1fr_auto]"
          >
            <select
              value={d.templateId}
              onChange={(e) => updateDraft(idx, { templateId: e.target.value })}
              className="rounded-md border bg-background px-2 py-1.5 text-sm"
              required
            >
              <option value="">— escolha skill —</option>
              {templates.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.tier.toUpperCase()} · {t.name}
                </option>
              ))}
            </select>
            <Input
              value={d.name}
              onChange={(e) => updateDraft(idx, { name: e.target.value })}
              placeholder="Nome (ex: Dev Backend Plataforma)"
              required
            />
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => removeDraft(idx)}
            >
              Remover
            </Button>
          </div>
        ))}
      </div>

      <Button type="button" variant="outline" size="sm" onClick={addDraft}>
        <Bot className="size-4" /> Adicionar agente
      </Button>
    </div>
  );
}

function StepReview({
  creds,
  squad,
  manifest,
  agents,
  templates,
}: {
  creds: CredsForm;
  squad: SquadForm;
  manifest: ManifestForm;
  agents: AgentDraft[];
  templates: SkillTemplate[];
}) {
  const tplById = new Map(templates.map((t) => [t.id, t]));
  return (
    <div className="space-y-3 text-sm">
      <Card>
        <CardHeader className="py-3">
          <CardTitle className="text-base">Credenciais</CardTitle>
        </CardHeader>
        <CardContent className="space-y-1 py-3">
          <Row
            label="GitHub token"
            value={creds.github_token ? '••• preenchido' : 'vazio'}
          />
          <Row
            label="Jira token"
            value={creds.jira_token ? '••• preenchido' : 'vazio'}
          />
          {(!creds.github_token || !creds.jira_token) && (
            <CardDescription className="mt-2">
              Você pode preencher depois em Credenciais. Sem GitHub, agente Dev
              não consegue abrir PR; sem Jira, BA/Architect não leem issues.
            </CardDescription>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="py-3">
          <CardTitle className="text-base">Squad</CardTitle>
        </CardHeader>
        <CardContent className="space-y-1 py-3">
          <Row label="Slug" value={squad.slug} mono />
          <Row label="Nome" value={squad.name} />
          {squad.domain && <Row label="Domínio" value={squad.domain} />}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="py-3">
          <CardTitle className="text-base">Manifesto</CardTitle>
        </CardHeader>
        <CardContent className="space-y-1 py-3">
          <Row
            label="Repositórios"
            value={
              manifest.repos
                .split(/\s*[\n,]\s*/)
                .filter((s) => s.trim())
                .length + ' repos'
            }
          />
          <Row
            label="Projetos Jira"
            value={
              manifest.jira_projects
                .split(/\s*[\n,]\s*/)
                .filter((s) => s.trim())
                .join(', ') || '(nenhum)'
            }
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="py-3">
          <CardTitle className="text-base">Agentes a provisionar</CardTitle>
        </CardHeader>
        <CardContent className="space-y-1 py-3">
          {agents.length === 0 && (
            <p className="text-xs italic text-muted-foreground">
              Nenhum agente — você pode adicionar pelo painel da squad depois.
            </p>
          )}
          {agents.map((a, i) => {
            const tpl = tplById.get(a.templateId);
            return (
              <div key={i} className="flex items-center justify-between gap-2">
                <span>{a.name || '(sem nome)'}</span>
                {tpl && (
                  <Badge variant="outline" className="text-[10px]">
                    {tpl.tier.toUpperCase()}
                  </Badge>
                )}
              </div>
            );
          })}
        </CardContent>
      </Card>
    </div>
  );
}

function Row({
  label,
  value,
  mono,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="flex justify-between gap-3">
      <span className="text-muted-foreground">{label}</span>
      <span className={cn('truncate text-right', mono && 'font-mono')}>
        {value}
      </span>
    </div>
  );
}

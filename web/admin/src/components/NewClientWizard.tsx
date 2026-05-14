import { useState, type FormEvent } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { Check, ChevronLeft, ChevronRight } from 'lucide-react';
import {
  createClient,
  createSquad,
  updateBillingPlan,
  type ClientCreate,
  type SquadCreate,
} from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { cn } from '@/lib/utils';

interface ClientForm {
  slug: string;
  name: string;
  jiraUrl: string;
  jiraEmail: string;
}

interface BillingForm {
  planKind: 'starter' | 'growth' | 'scale';
  baseFeeBrl: string;
  includedTokens: string;
  includedTasks: string;
  overageMarkupPct: string;
  infraOverheadPct: string;
  fixedOverheadBrlPerTask: string;
  usdToBrlRate: string;
}

interface SquadForm {
  enabled: boolean;
  slug: string;
  name: string;
  description: string;
  domain: string;
}

const PLAN_DEFAULTS: Record<BillingForm['planKind'], Omit<BillingForm, 'planKind'>> = {
  starter: {
    baseFeeBrl: '0',
    includedTokens: '500000',
    includedTasks: '20',
    overageMarkupPct: '50',
    infraOverheadPct: '20',
    fixedOverheadBrlPerTask: '0.50',
    usdToBrlRate: '5.00',
  },
  growth: {
    baseFeeBrl: '1500',
    includedTokens: '5000000',
    includedTasks: '200',
    overageMarkupPct: '30',
    infraOverheadPct: '20',
    fixedOverheadBrlPerTask: '0.50',
    usdToBrlRate: '5.00',
  },
  scale: {
    baseFeeBrl: '5000',
    includedTokens: '25000000',
    includedTasks: '1000',
    overageMarkupPct: '20',
    infraOverheadPct: '15',
    fixedOverheadBrlPerTask: '0.30',
    usdToBrlRate: '5.00',
  },
};

const STEPS = ['Cliente', 'Plano', 'Primeira squad', 'Revisão'] as const;

export default function NewClientWizard({ onSuccess }: { onSuccess: () => void }) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  const [step, setStep] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const [client, setClient] = useState<ClientForm>({
    slug: '',
    name: '',
    jiraUrl: '',
    jiraEmail: '',
  });

  const [billing, setBilling] = useState<BillingForm>({
    planKind: 'starter',
    ...PLAN_DEFAULTS.starter,
  });

  const [squad, setSquad] = useState<SquadForm>({
    enabled: true,
    slug: '',
    name: '',
    description: '',
    domain: '',
  });

  const fullMutation = useMutation({
    mutationFn: async () => {
      const payload: ClientCreate = {
        slug: client.slug,
        name: client.name,
        jira_workspace_url: client.jiraUrl || undefined,
        jira_email: client.jiraEmail || undefined,
      };
      const created = await createClient(payload);

      await updateBillingPlan(created.id, {
        plan_kind: billing.planKind,
        base_fee_monthly_brl: billing.baseFeeBrl,
        included_quota_tokens: Number(billing.includedTokens),
        included_quota_tasks: Number(billing.includedTasks),
        overage_markup_pct: billing.overageMarkupPct,
        infra_overhead_pct: billing.infraOverheadPct,
        fixed_overhead_brl_per_task: billing.fixedOverheadBrlPerTask,
        usd_to_brl_rate: billing.usdToBrlRate,
      });

      if (squad.enabled && squad.slug && squad.name) {
        const payloadSquad: SquadCreate = {
          slug: squad.slug,
          name: squad.name,
          description: squad.description || undefined,
          domain: squad.domain || undefined,
        };
        await createSquad(created.id, payloadSquad);
      }

      return created;
    },
    onSuccess: (created) => {
      queryClient.invalidateQueries({ queryKey: ['clients'] });
      queryClient.invalidateQueries({ queryKey: ['cost-by-client'] });
      onSuccess();
      navigate(`/clients/${created.id}`);
    },
    onError: (err: unknown) => {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(detail ?? 'Falha ao criar cliente');
    },
  });

  function canAdvance(): boolean {
    if (step === 0) return Boolean(client.slug && client.name);
    if (step === 1) {
      return (
        billing.includedTokens !== '' &&
        billing.includedTasks !== '' &&
        billing.usdToBrlRate !== ''
      );
    }
    if (step === 2) {
      if (!squad.enabled) return true;
      return Boolean(squad.slug && squad.name);
    }
    return true;
  }

  function handleNext(event: FormEvent) {
    event.preventDefault();
    setError(null);
    if (step < STEPS.length - 1) {
      setStep(step + 1);
    } else {
      fullMutation.mutate();
    }
  }

  return (
    <DialogContent className="sm:max-w-xl">
      <DialogHeader>
        <DialogTitle>Novo cliente</DialogTitle>
        <DialogDescription>
          Wizard em {STEPS.length} passos: dados, plano de billing, primeira squad e revisão.
        </DialogDescription>
      </DialogHeader>

      <StepBar current={step} />

      <form onSubmit={handleNext} className="space-y-4">
        {step === 0 && <StepClient form={client} setForm={setClient} />}
        {step === 1 && <StepBilling form={billing} setForm={setBilling} />}
        {step === 2 && <StepSquad form={squad} setForm={setSquad} clientSlug={client.slug} />}
        {step === 3 && <StepReview client={client} billing={billing} squad={squad} />}

        {error && <p className="text-sm text-destructive">{error}</p>}

        <DialogFooter className="flex items-center justify-between gap-2 sm:justify-between">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            disabled={step === 0 || fullMutation.isPending}
            onClick={() => {
              setError(null);
              setStep(Math.max(0, step - 1));
            }}
          >
            <ChevronLeft className="size-4" /> Voltar
          </Button>
          <Button type="submit" disabled={!canAdvance() || fullMutation.isPending}>
            {step < STEPS.length - 1 ? (
              <>
                Próximo <ChevronRight className="size-4" />
              </>
            ) : fullMutation.isPending ? (
              'Criando…'
            ) : (
              <>
                <Check className="size-4" /> Criar cliente
              </>
            )}
          </Button>
        </DialogFooter>
      </form>
    </DialogContent>
  );
}

function StepBar({ current }: { current: number }) {
  return (
    <ol className="flex items-center gap-2 text-xs">
      {STEPS.map((label, idx) => {
        const state = idx < current ? 'done' : idx === current ? 'active' : 'pending';
        return (
          <li key={label} className="flex items-center gap-2">
            <span
              className={cn(
                'grid size-6 place-items-center rounded-full font-mono',
                state === 'done' && 'bg-brand-500 text-white',
                state === 'active' && 'bg-brand-500/15 text-brand-500 ring-1 ring-brand-500',
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
            {idx < STEPS.length - 1 && <span className="mx-1 text-muted-foreground">·</span>}
          </li>
        );
      })}
    </ol>
  );
}

function StepClient({
  form,
  setForm,
}: {
  form: ClientForm;
  setForm: (f: ClientForm) => void;
}) {
  return (
    <div className="space-y-3">
      <div className="space-y-1.5">
        <Label htmlFor="slug">Slug *</Label>
        <Input
          id="slug"
          value={form.slug}
          onChange={(e) =>
            setForm({
              ...form,
              slug: e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, '-'),
            })
          }
          placeholder="acme-corp"
          required
          pattern="^[a-z0-9][a-z0-9-]*$"
        />
        <p className="text-xs text-muted-foreground">
          Identificador único (a-z, 0-9, hífen). Não muda depois.
        </p>
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="name">Nome *</Label>
        <Input
          id="name"
          value={form.name}
          onChange={(e) => setForm({ ...form, name: e.target.value })}
          placeholder="ACME Corporation"
          required
        />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="jiraUrl">Jira workspace URL</Label>
        <Input
          id="jiraUrl"
          value={form.jiraUrl}
          onChange={(e) => setForm({ ...form, jiraUrl: e.target.value })}
          placeholder="https://acme.atlassian.net"
        />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="jiraEmail">Jira email</Label>
        <Input
          id="jiraEmail"
          type="email"
          value={form.jiraEmail}
          onChange={(e) => setForm({ ...form, jiraEmail: e.target.value })}
          placeholder="admin@acme.com"
        />
      </div>
    </div>
  );
}

function StepBilling({
  form,
  setForm,
}: {
  form: BillingForm;
  setForm: (f: BillingForm) => void;
}) {
  const choosePlan = (kind: BillingForm['planKind']) => {
    setForm({ planKind: kind, ...PLAN_DEFAULTS[kind] });
  };

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-3 gap-2">
        {(['starter', 'growth', 'scale'] as const).map((kind) => (
          <button
            key={kind}
            type="button"
            onClick={() => choosePlan(kind)}
            className={cn(
              'rounded-md border p-3 text-left text-sm transition-colors',
              form.planKind === kind
                ? 'border-brand-500 bg-brand-500/5'
                : 'border-border hover:border-brand-500/50',
            )}
          >
            <div className="font-medium capitalize">{kind}</div>
            <div className="text-xs text-muted-foreground">
              Base R$ {PLAN_DEFAULTS[kind].baseFeeBrl}/mês ·{' '}
              {Number(PLAN_DEFAULTS[kind].includedTokens).toLocaleString('pt-BR')} tokens
            </div>
          </button>
        ))}
      </div>

      <div className="grid grid-cols-2 gap-3">
        <Field
          label="Base fee mensal (BRL)"
          value={form.baseFeeBrl}
          onChange={(v) => setForm({ ...form, baseFeeBrl: v })}
        />
        <Field
          label="Câmbio USD→BRL"
          value={form.usdToBrlRate}
          onChange={(v) => setForm({ ...form, usdToBrlRate: v })}
        />
        <Field
          label="Quota tokens"
          value={form.includedTokens}
          onChange={(v) => setForm({ ...form, includedTokens: v })}
        />
        <Field
          label="Quota tasks"
          value={form.includedTasks}
          onChange={(v) => setForm({ ...form, includedTasks: v })}
        />
        <Field
          label="Markup overage (%)"
          value={form.overageMarkupPct}
          onChange={(v) => setForm({ ...form, overageMarkupPct: v })}
        />
        <Field
          label="Infra overhead (%)"
          value={form.infraOverheadPct}
          onChange={(v) => setForm({ ...form, infraOverheadPct: v })}
        />
        <Field
          label="Fixed por task (BRL)"
          value={form.fixedOverheadBrlPerTask}
          onChange={(v) => setForm({ ...form, fixedOverheadBrlPerTask: v })}
        />
      </div>
      <p className="text-xs text-muted-foreground">
        Preset preenche valores típicos, ajuste cada campo se necessário.
      </p>
    </div>
  );
}

function StepSquad({
  form,
  setForm,
  clientSlug,
}: {
  form: SquadForm;
  setForm: (f: SquadForm) => void;
  clientSlug: string;
}) {
  return (
    <div className="space-y-3">
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={form.enabled}
          onChange={(e) => setForm({ ...form, enabled: e.target.checked })}
          className="size-4"
        />
        Criar primeira squad agora
        <span className="text-xs text-muted-foreground">(você pode adicionar mais depois)</span>
      </label>

      {form.enabled && (
        <div className="space-y-3 rounded-md border bg-muted/30 p-3">
          <div className="space-y-1.5">
            <Label htmlFor="squad-slug">Slug *</Label>
            <Input
              id="squad-slug"
              value={form.slug}
              onChange={(e) =>
                setForm({
                  ...form,
                  slug: e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, '-'),
                })
              }
              placeholder="plataforma"
              pattern="^[a-z0-9][a-z0-9-]*$"
            />
            <p className="text-xs text-muted-foreground">
              Ex: <code>plataforma</code>, <code>mobile</code>, <code>backend</code>.
              Combina com cliente {clientSlug && <code>{clientSlug}</code>}.
            </p>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="squad-name">Nome *</Label>
            <Input
              id="squad-name"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              placeholder="Squad Plataforma"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="squad-domain">Domínio</Label>
            <Input
              id="squad-domain"
              value={form.domain}
              onChange={(e) => setForm({ ...form, domain: e.target.value })}
              placeholder="backend, frontend, mobile…"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="squad-desc">Descrição</Label>
            <Input
              id="squad-desc"
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
              placeholder="Time responsável por…"
            />
          </div>
        </div>
      )}
    </div>
  );
}

function StepReview({
  client,
  billing,
  squad,
}: {
  client: ClientForm;
  billing: BillingForm;
  squad: SquadForm;
}) {
  return (
    <div className="space-y-3 text-sm">
      <Section title="Cliente">
        <ReviewRow label="Slug" value={client.slug} />
        <ReviewRow label="Nome" value={client.name} />
        {client.jiraUrl && <ReviewRow label="Jira" value={client.jiraUrl} />}
        {client.jiraEmail && <ReviewRow label="Jira email" value={client.jiraEmail} />}
      </Section>

      <Section title="Plano">
        <ReviewRow label="Tipo" value={billing.planKind} mono />
        <ReviewRow label="Base mensal (BRL)" value={billing.baseFeeBrl} />
        <ReviewRow label="Quota tokens" value={billing.includedTokens} />
        <ReviewRow label="Quota tasks" value={billing.includedTasks} />
        <ReviewRow label="Markup overage (%)" value={billing.overageMarkupPct} />
        <ReviewRow label="Câmbio USD→BRL" value={billing.usdToBrlRate} />
      </Section>

      <Section title="Squad">
        {squad.enabled && squad.slug ? (
          <>
            <ReviewRow label="Slug" value={squad.slug} />
            <ReviewRow label="Nome" value={squad.name} />
            {squad.domain && <ReviewRow label="Domínio" value={squad.domain} />}
            {squad.description && <ReviewRow label="Descrição" value={squad.description} />}
          </>
        ) : (
          <p className="text-xs italic text-muted-foreground">
            Nenhuma squad inicial — você cria depois pelo painel.
          </p>
        )}
      </Section>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-md border bg-muted/30 p-3">
      <div className="mb-2 text-xs font-medium uppercase text-muted-foreground">{title}</div>
      <div className="space-y-1">{children}</div>
    </div>
  );
}

function ReviewRow({
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
      <span className={cn('truncate text-right', mono && 'font-mono')}>{value}</span>
    </div>
  );
}

function Field({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <div className="space-y-1.5">
      <Label className="text-xs">{label}</Label>
      <Input value={value} onChange={(e) => onChange(e.target.value)} />
    </div>
  );
}

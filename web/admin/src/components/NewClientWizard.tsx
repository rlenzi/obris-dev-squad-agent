import { useState, type FormEvent } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, Check, ChevronLeft, ChevronRight, RefreshCw } from 'lucide-react';
import {
  createClient,
  createUserForClient,
  updateBillingPlan,
  type ClientCreate,
} from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardContent } from '@/components/ui/card';
import { cn } from '@/lib/utils';

interface ClientForm {
  slug: string;
  name: string;
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

interface UserForm {
  fullName: string;
  email: string;
  password: string;
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

const STEPS = ['Cliente', 'Plano', 'Usuário', 'Revisão'] as const;

const PASSWORD_ALPHABET =
  'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789!@#$%&*-_+=';

function randomPassword(length: number = 16): string {
  const chars = new Array(length);
  const cryptoObj = window.crypto;
  const array = new Uint32Array(length);
  cryptoObj.getRandomValues(array);
  for (let i = 0; i < length; i++) {
    chars[i] = PASSWORD_ALPHABET[array[i] % PASSWORD_ALPHABET.length];
  }
  return chars.join('');
}

export default function NewClientWizard() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  const [step, setStep] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const [client, setClient] = useState<ClientForm>({
    slug: '',
    name: '',
  });

  const [billing, setBilling] = useState<BillingForm>({
    planKind: 'starter',
    ...PLAN_DEFAULTS.starter,
  });

  const [user, setUser] = useState<UserForm>({
    fullName: '',
    email: '',
    password: '',
  });

  const fullMutation = useMutation({
    mutationFn: async () => {
      const payload: ClientCreate = {
        slug: client.slug,
        name: client.name,
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

      await createUserForClient(created.id, {
        email: user.email,
        full_name: user.fullName,
        password: user.password,
        role: 'client_admin',
      });

      return created;
    },
    onSuccess: (created) => {
      queryClient.invalidateQueries({ queryKey: ['clients'] });
      queryClient.invalidateQueries({ queryKey: ['cost-by-client'] });
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
      return Boolean(
        user.fullName.trim() &&
          user.email.includes('@') &&
          user.password.length >= 8,
      );
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
    <div className="mx-auto max-w-2xl space-y-6">
      <Button
        variant="ghost"
        size="sm"
        onClick={() => navigate('/clients')}
      >
        <ArrowLeft className="size-4" /> Voltar para clientes
      </Button>

      <div>
        <h1 className="text-3xl font-semibold tracking-tight">Novo cliente</h1>
        <p className="text-muted-foreground">
          Cria o tenant, define billing e o usuário administrador inicial. O
          cliente recebe email + senha pra entrar no painel dele e configurar
          squad/credenciais/agentes por conta própria.
        </p>
      </div>

      <StepBar current={step} />

      <Card>
        <CardContent className="pt-6">
          <form onSubmit={handleNext} className="space-y-4">
            {step === 0 && <StepClient form={client} setForm={setClient} />}
            {step === 1 && <StepBilling form={billing} setForm={setBilling} />}
            {step === 2 && <StepUser form={user} setForm={setUser} />}
            {step === 3 && (
              <StepReview client={client} billing={billing} user={user} />
            )}

            {error && <p className="text-sm text-destructive">{error}</p>}

            <div className="flex items-center justify-between border-t pt-4">
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
              <Button
                type="submit"
                disabled={!canAdvance() || fullMutation.isPending}
              >
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
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
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
      <p className="text-xs text-muted-foreground">
        Jira, GitHub e demais credenciais são configurados pelo próprio cliente
        no primeiro acesso ao painel dele.
      </p>
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

function StepUser({
  form,
  setForm,
}: {
  form: UserForm;
  setForm: (f: UserForm) => void;
}) {
  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">
        Esse usuário será o <strong>administrador inicial</strong> do tenant.
        Anote a senha e passe pra ele por canal seguro — não há email
        automático.
      </p>
      <div className="space-y-1.5">
        <Label htmlFor="user-name">Nome completo *</Label>
        <Input
          id="user-name"
          value={form.fullName}
          onChange={(e) => setForm({ ...form, fullName: e.target.value })}
          placeholder="João Silva"
          required
        />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="user-email">Email *</Label>
        <Input
          id="user-email"
          type="email"
          value={form.email}
          onChange={(e) => setForm({ ...form, email: e.target.value })}
          placeholder="admin@acme.com"
          required
        />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="user-password">Senha *</Label>
        <div className="flex gap-2">
          <Input
            id="user-password"
            type="text"
            value={form.password}
            onChange={(e) => setForm({ ...form, password: e.target.value })}
            placeholder="mínimo 8 caracteres"
            minLength={8}
            required
          />
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => setForm({ ...form, password: randomPassword(16) })}
            title="Gera senha aleatória de 16 caracteres"
          >
            <RefreshCw className="size-4" /> Gerar
          </Button>
        </div>
        <p className="text-xs text-muted-foreground">
          Visível como texto pra você copiar — feche o wizard só depois de salvar.
        </p>
      </div>
    </div>
  );
}

function StepReview({
  client,
  billing,
  user,
}: {
  client: ClientForm;
  billing: BillingForm;
  user: UserForm;
}) {
  return (
    <div className="space-y-3 text-sm">
      <Section title="Cliente">
        <ReviewRow label="Slug" value={client.slug} mono />
        <ReviewRow label="Nome" value={client.name} />
      </Section>

      <Section title="Plano">
        <ReviewRow label="Tipo" value={billing.planKind} mono />
        <ReviewRow label="Base mensal (BRL)" value={billing.baseFeeBrl} />
        <ReviewRow label="Quota tokens" value={billing.includedTokens} />
        <ReviewRow label="Quota tasks" value={billing.includedTasks} />
        <ReviewRow label="Markup overage (%)" value={billing.overageMarkupPct} />
        <ReviewRow label="Câmbio USD→BRL" value={billing.usdToBrlRate} />
      </Section>

      <Section title="Usuário admin inicial">
        <ReviewRow label="Nome" value={user.fullName} />
        <ReviewRow label="Email" value={user.email} mono />
        <ReviewRow label="Senha" value={user.password} mono />
        <p className="mt-1 text-xs italic text-muted-foreground">
          Copie a senha agora — ela não fica salva em lugar nenhum em texto
          plano depois.
        </p>
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

import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useMutation, useQuery } from '@tanstack/react-query';
import {
  AlertCircle, ArrowLeft, CheckCircle2, Circle, Loader2,
  XCircle,
} from 'lucide-react';

import { useClientId } from '@/lib/use-client-id';
import {
  cancelOnboardingAnalysis, getOnboardingStatus,
  type OnboardingScanProgress, type OnboardingStatusResponse,
  type OnboardingStep,
} from '@/lib/api';
import { formatApiError } from '@/lib/utils';
import { Button } from '@/components/ui/button';

/**
 * Tela 2 — Análise viva (PR-6 do redesign).
 *
 * Polling a cada 2s no /onboarding-status. Mostra as 6 etapas da state
 * machine do backend (analyzer v2):
 *   1. cloning      — Clonando repositório
 *   2. scanning     — Escaneando arquivos
 *   3. oa_scanning  — Analisando código com IA (OA scan profundo)
 *   4. indexing     — Indexando conhecimento na RAG
 *   5. finalizing   — Finalizando
 *   6. grading      — Verificando qualidade (grader independente)
 *
 * Princípios:
 *   - Mensagem em prosa primeira pessoa só na etapa ATIVA (vem do
 *     backend via step_label). Concluídas mostram ✓ + resultado seco;
 *     pendentes mostram ○ + título.
 *   - Sem ETA — barra de progresso só quando há contadores mensuráveis
 *     (chunks_indexed / chunks_total). Etapas opacas só têm spinner.
 *   - Cancelar disponível em qualquer momento (com confirm inline).
 *   - Cliente pode fechar a aba — estado fica persistido no backend.
 *   - Erro em etapa → ícone vermelho na etapa + mensagem + retry.
 */

interface StepDefinition {
  key: OnboardingStep;
  title: string;
}

const STEPS_REPO: StepDefinition[] = [
  { key: 'cloning', title: 'Clonando repositório' },
  { key: 'scanning', title: 'Escaneando arquivos' },
  { key: 'oa_scanning', title: 'Analisando código com IA' },
  { key: 'indexing', title: 'Indexando conhecimento na RAG da squad' },
  { key: 'finalizing', title: 'Finalizando' },
  { key: 'grading', title: 'Verificando qualidade da análise' },
];

const STEPS_GREENFIELD: StepDefinition[] = [
  { key: 'indexing_materials' as OnboardingStep, title: 'Indexando materiais que você subiu' },
  { key: 'proposing_stack' as OnboardingStep, title: 'Pensando na stack ideal pro que você descreveu' },
  { key: 'defining_agents' as OnboardingStep, title: 'Definindo agentes' },
];

const POLL_INTERVAL_MS = 2000;


export default function SetupAnalyzingPage() {
  const { squadId } = useParams<{ squadId: string }>();
  const navigate = useNavigate();
  const clientId = useClientId();

  const [askedCancel, setAskedCancel] = useState(false);
  const [cancelError, setCancelError] = useState<string | null>(null);

  const statusQuery = useQuery({
    queryKey: ['onboarding-status', clientId, squadId],
    queryFn: () => getOnboardingStatus(clientId, squadId!),
    enabled: Boolean(squadId),
    refetchInterval: (query) => {
      const data = query.state.data;
      if (!data) return POLL_INTERVAL_MS;
      // Para de poll quando estado é terminal
      if (data.status === 'completed' || data.status === 'failed' ||
          data.status === 'cancelled') {
        return false;
      }
      return POLL_INTERVAL_MS;
    },
  });

  const cancelMutation = useMutation({
    mutationFn: () => cancelOnboardingAnalysis(clientId, squadId!),
    onSuccess: () => {
      // Re-fetch imediato pra refletir status=cancelled
      statusQuery.refetch();
      setAskedCancel(false);
    },
    onError: (err: unknown) => {
      setCancelError(formatApiError(err, 'Falha ao cancelar.'));
    },
  });

  // Quando completed, navega pra Tela 3 (placeholder do PR-7).
  useEffect(() => {
    if (statusQuery.data?.status === 'completed' && squadId) {
      const t = setTimeout(() => {
        navigate(`/setup/result/${squadId}`);
      }, 800); // pequeno delay pra cliente ver "concluído"
      return () => clearTimeout(t);
    }
  }, [statusQuery.data?.status, navigate, squadId]);

  if (!squadId) {
    return (
      <div className="mx-auto max-w-2xl py-12 px-6">
        <p className="text-sm text-destructive">squadId ausente na URL.</p>
      </div>
    );
  }

  if (statusQuery.isLoading) {
    return (
      <div className="mx-auto max-w-2xl py-12 px-6 text-center text-sm text-muted-foreground">
        <Loader2 className="mx-auto h-6 w-6 animate-spin" />
        <p className="mt-3">Carregando estado da análise…</p>
      </div>
    );
  }

  if (statusQuery.isError || !statusQuery.data) {
    return (
      <div className="mx-auto max-w-2xl py-12 px-6">
        <p className="text-sm text-destructive">
          {formatApiError(statusQuery.error, 'Erro carregando status.')}
        </p>
      </div>
    );
  }

  const data = statusQuery.data;
  // Detecta modo (greenfield vs repo) pelo scan_progress.mode
  const isGreenfield = data.scan_progress?.mode === 'greenfield';
  const STEPS = isGreenfield ? STEPS_GREENFIELD : STEPS_REPO;

  const currentIndex = stepIndexOf(STEPS, data.current_step);
  const terminal =
    data.status === 'completed' ||
    data.status === 'failed' ||
    data.status === 'cancelled';

  const titleByStatus =
    data.status === 'completed'
      ? 'Análise concluída ✓'
      : data.status === 'failed'
        ? 'Análise falhou'
        : data.status === 'cancelled'
          ? 'Análise cancelada'
          : isGreenfield
            ? 'Pensando no seu projeto'
            : 'Analisando seu código';

  return (
    <div className="mx-auto max-w-2xl py-12 px-6">
      <header className="mb-8 space-y-2">
        <h1 className="text-2xl font-semibold tracking-tight">
          {titleByStatus}
        </h1>
        {!terminal && (
          <p className="text-sm text-muted-foreground">
            Pode fechar essa aba e voltar — quando voltar a análise
            continua do mesmo ponto.
          </p>
        )}
      </header>

      <ol className="space-y-6">
        {STEPS.map((step, idx) => (
          <StepRow
            key={step.key}
            step={step}
            state={resolveStepState({
              stepIndex: idx,
              currentIndex,
              backendStatus: data.status,
            })}
            isActive={data.current_step === step.key && !terminal}
            stepLabel={data.step_label}
            scanProgress={data.scan_progress}
            errorMessage={data.error_message}
          />
        ))}
      </ol>

      {data.status === 'in_progress' && !askedCancel && (
        <div className="mt-10 flex justify-end">
          <button
            type="button"
            onClick={() => setAskedCancel(true)}
            className="text-xs text-muted-foreground hover:text-destructive"
          >
            ✕ Cancelar análise
          </button>
        </div>
      )}

      {askedCancel && (
        <div className="mt-10 rounded-md border border-destructive/40 bg-destructive/5 p-4">
          <p className="text-sm">
            Tem certeza que quer cancelar? A análise vai parar e você
            terá que recomeçar do zero numa próxima tentativa.
          </p>
          {cancelError && (
            <p className="mt-2 text-xs text-destructive">{cancelError}</p>
          )}
          <div className="mt-3 flex gap-2">
            <Button
              variant="destructive"
              size="sm"
              onClick={() => cancelMutation.mutate()}
              disabled={cancelMutation.isPending}
            >
              {cancelMutation.isPending ? 'Cancelando…' : 'Sim, cancelar'}
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setAskedCancel(false)}
            >
              Continuar a análise
            </Button>
          </div>
        </div>
      )}

      {data.status === 'failed' && (
        <div className="mt-10 space-y-3 rounded-md border border-destructive/40 bg-destructive/5 p-4">
          <div className="flex items-start gap-2">
            <AlertCircle className="mt-0.5 h-4 w-4 flex-shrink-0 text-destructive" />
            <div className="text-sm">
              <p className="font-medium">A análise não terminou.</p>
              {data.error_message && (
                <p className="mt-1 text-xs text-muted-foreground">
                  {data.error_message}
                </p>
              )}
            </div>
          </div>
          <div className="flex gap-2">
            <Button
              size="sm"
              variant="outline"
              onClick={() => navigate('/setup/start')}
            >
              <ArrowLeft className="mr-1 h-3 w-3" />
              Recomeçar
            </Button>
          </div>
        </div>
      )}

      {data.status === 'cancelled' && (
        <div className="mt-10 flex justify-end">
          <Button
            size="sm"
            variant="outline"
            onClick={() => navigate('/setup/start')}
          >
            <ArrowLeft className="mr-1 h-3 w-3" />
            Recomeçar
          </Button>
        </div>
      )}

      {data.status === 'completed' && (
        <p className="mt-10 text-center text-xs text-muted-foreground">
          Redirecionando pra revisão…
        </p>
      )}
    </div>
  );
}


// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------


type StepState = 'done' | 'active' | 'pending' | 'failed';


function stepIndexOf(
  steps: StepDefinition[],
  currentStep: string | null | undefined,
): number {
  if (!currentStep) return -1;
  return steps.findIndex((s) => s.key === currentStep);
}


function resolveStepState({
  stepIndex, currentIndex, backendStatus,
}: {
  stepIndex: number;
  currentIndex: number;
  backendStatus: OnboardingStatusResponse['status'];
}): StepState {
  if (backendStatus === 'completed') return 'done';
  if (backendStatus === 'failed') {
    // step que estava ativo vira failed; anteriores done; posteriores pending
    if (stepIndex === currentIndex) return 'failed';
    if (stepIndex < currentIndex) return 'done';
    return 'pending';
  }
  if (backendStatus === 'cancelled') {
    if (stepIndex < currentIndex) return 'done';
    return 'pending';
  }
  if (currentIndex === -1) return 'pending';
  if (stepIndex < currentIndex) return 'done';
  if (stepIndex === currentIndex) return 'active';
  return 'pending';
}


interface StepRowProps {
  step: StepDefinition;
  state: StepState;
  isActive: boolean;
  stepLabel: string | null;
  scanProgress: OnboardingScanProgress;
  errorMessage: string | null;
}


function StepRow({
  step, state, isActive, stepLabel, scanProgress, errorMessage,
}: StepRowProps) {
  const icon = state === 'done'
    ? <CheckCircle2 className="h-5 w-5 text-emerald-600 dark:text-emerald-400" />
    : state === 'failed'
      ? <XCircle className="h-5 w-5 text-destructive" />
      : state === 'active'
        ? <Loader2 className="h-5 w-5 animate-spin text-primary" />
        : <Circle className="h-5 w-5 text-muted-foreground/40" />;

  const titleColorClass =
    state === 'done' ? 'text-foreground'
    : state === 'failed' ? 'text-destructive'
    : state === 'active' ? 'text-foreground font-medium'
    : 'text-muted-foreground';

  const summaryLine = state === 'done'
    ? doneSummaryFor(step.key, scanProgress)
    : null;

  return (
    <li className="flex gap-3">
      <div className="flex flex-col items-center pt-0.5">
        {icon}
      </div>
      <div className="flex-1 pb-1">
        <p className={`text-sm ${titleColorClass}`}>{step.title}</p>
        {summaryLine && (
          <p className="mt-0.5 text-xs text-muted-foreground">{summaryLine}</p>
        )}
        {isActive && stepLabel && (
          <div className="mt-2 rounded-md border bg-muted/40 p-3 text-xs leading-relaxed text-foreground/80">
            {stepLabel}
          </div>
        )}
        {isActive && step.key === 'indexing' && hasIndexingProgress(scanProgress) && (
          <IndexingProgressBar progress={scanProgress} />
        )}
        {state === 'failed' && errorMessage && (
          <p className="mt-2 text-xs text-destructive">{errorMessage}</p>
        )}
      </div>
    </li>
  );
}


function doneSummaryFor(
  key: OnboardingStep, progress: OnboardingScanProgress,
): string | null {
  if (key === 'cloning' && progress.clone_size_bytes != null) {
    const mb = (progress.clone_size_bytes / (1024 * 1024)).toFixed(1);
    return `clonado, ${mb} MB`;
  }
  if (key === 'scanning' && progress.total_files != null) {
    const excluded = progress.files_excluded ?? 0;
    return `${progress.total_files} arquivos elegíveis · ${excluded} excluídos`;
  }
  if (key === 'oa_scanning' && progress.oa_iterations != null) {
    return progress.oa_iterations > 1
      ? `${progress.oa_iterations} iterações com o grader`
      : 'concluído na primeira iteração';
  }
  if (key === 'indexing' && progress.chunks_indexed != null) {
    const cost = progress.embedding_cost_usd
      ? ` · US$ ${progress.embedding_cost_usd}`
      : '';
    return `${progress.chunks_indexed} chunks indexados${cost}`;
  }
  if (key === 'finalizing' && progress.stacks_detected != null) {
    return `${progress.stacks_detected} stacks detectadas`;
  }
  return null;
}


function hasIndexingProgress(progress: OnboardingScanProgress): boolean {
  return (
    typeof progress.chunks_indexed === 'number' &&
    typeof progress.chunks_total === 'number' &&
    progress.chunks_total > 0
  );
}


function IndexingProgressBar({ progress }: { progress: OnboardingScanProgress }) {
  const indexed = progress.chunks_indexed ?? 0;
  const total = progress.chunks_total ?? 0;
  const pct = total > 0 ? Math.min(100, (indexed / total) * 100) : 0;
  return (
    <div className="mt-3 space-y-1">
      <div className="text-xs text-muted-foreground">
        {indexed.toLocaleString('pt-BR')} de {total.toLocaleString('pt-BR')} chunks indexados
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
        <div
          className="h-full rounded-full bg-primary transition-all"
          style={{ width: `${pct}%` }}
        />
      </div>
      <div className="text-right text-xs text-muted-foreground">
        {pct.toFixed(0)}%
      </div>
    </div>
  );
}

import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMutation } from '@tanstack/react-query';
import {
  ArrowLeft, AlertCircle, CheckCircle2, ChevronDown, ChevronUp,
  ExternalLink, KeyRound, Loader2, Lock,
} from 'lucide-react';

import { useClientId } from '@/lib/use-client-id';
import {
  createCredential, createSquad, getGithubRepoStatus,
  runOnboardingAnalysis, updateManifest,
  type CredentialKind, type ManifestContent, type RepoStatusResponse,
  type SquadCreate,
} from '@/lib/api';
import { formatApiError } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

/**
 * Tela 1 — Conectar repositório (PR-5 do redesign).
 *
 * Cliente cola URL do repo. Sistema detecta privado/publico via
 * /client/github/repo-status (debounce 500ms). Se privado, mostra
 * input de token GitHub just-in-time, com bloco expansivel "Como
 * criar um token" colapsado por default.
 *
 * Botao "Conectar e começar analise":
 *   1. Cria credencial GITHUB_TOKEN se preenchida (409 se ja existe — ignora)
 *   2. Cria squad com slug derivado do nome do repo
 *   3. Salva manifest derivado (repos = [URL])
 *   4. Dispara POST /run-onboarding-analysis
 *   5. Navega pra /setup/analyzing/<squad_id>/<task_id> (placeholder ate PR-6)
 *
 * Atual: suporta 1 repo. Botao "+ adicionar outro" e' placeholder visual
 * pro fluxo multi-repo do desenho — backend v2 atual indexa o primeiro
 * apenas; expansao multi-repo fica como melhoria futura documentada
 * no doc do redesign.
 */

const TOKEN_HOWTO_GITHUB_URL =
  'https://github.com/settings/tokens/new?scopes=repo&description=dev-autonomo';


type Detection =
  | { kind: 'idle' }
  | { kind: 'loading' }
  | { kind: 'invalid'; message: string }
  | { kind: 'public'; data: RepoStatusResponse }
  | { kind: 'private_needs_token'; data: RepoStatusResponse; message: string }
  | { kind: 'token_invalid'; data: RepoStatusResponse; message: string }
  | { kind: 'accessible_with_token'; data: RepoStatusResponse }
  | { kind: 'network_error'; message: string };


function useDebouncedValue<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(t);
  }, [value, delay]);
  return debounced;
}


export default function SetupRepositoryPage() {
  const navigate = useNavigate();
  const clientId = useClientId();

  const [repoUrl, setRepoUrl] = useState('');
  const [token, setToken] = useState('');
  const [howtoOpen, setHowtoOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const debouncedUrl = useDebouncedValue(repoUrl.trim(), 500);
  const debouncedToken = useDebouncedValue(token.trim(), 500);

  const [detection, setDetection] = useState<Detection>({ kind: 'idle' });

  // Re-checa quando URL ou token mudam (com debounce)
  useEffect(() => {
    if (!debouncedUrl) {
      setDetection({ kind: 'idle' });
      return;
    }
    let cancelled = false;
    setDetection({ kind: 'loading' });
    getGithubRepoStatus(clientId, debouncedUrl, debouncedToken || undefined)
      .then((data) => {
        if (cancelled) return;
        if (!data.valid) {
          setDetection({
            kind: 'invalid',
            message: data.error ?? 'URL não reconhecida como repositório GitHub.',
          });
          return;
        }
        if (data.accessible && data.is_public) {
          setDetection({ kind: 'public', data });
        } else if (data.accessible && !data.is_public) {
          setDetection({ kind: 'accessible_with_token', data });
        } else if (debouncedToken) {
          // Tinha token mas falhou
          setDetection({
            kind: 'token_invalid',
            data,
            message: data.error ?? 'Token recusado pelo GitHub.',
          });
        } else {
          setDetection({
            kind: 'private_needs_token',
            data,
            message:
              data.error ??
              'Repositório privado ou inexistente. Preciso de um token GitHub.',
          });
        }
      })
      .catch((err) => {
        if (cancelled) return;
        setDetection({
          kind: 'network_error',
          message: formatApiError(err, 'Erro consultando GitHub.'),
        });
      });
    return () => {
      cancelled = true;
    };
  }, [clientId, debouncedUrl, debouncedToken]);

  const showTokenInput =
    detection.kind === 'private_needs_token' ||
    detection.kind === 'token_invalid' ||
    detection.kind === 'accessible_with_token';

  const canSubmit =
    detection.kind === 'public' || detection.kind === 'accessible_with_token';

  const submitMutation = useMutation({
    mutationFn: async () => {
      if (detection.kind !== 'public' && detection.kind !== 'accessible_with_token') {
        throw new Error('Aguarde a verificação do repositório terminar.');
      }
      const status = detection.data;
      const slug = status.suggested_slug ?? `squad-${Date.now()}`;
      const repoName = status.repo ?? slug;
      const canonical = status.url;

      // 1. Token (se preenchido). 409 = já existe → ignoramos pra nao
      //    bloquear o cliente. Cliente vai usar a credencial existente.
      if (token.trim()) {
        try {
          await createCredential(clientId, {
            kind: 'github_token' as CredentialKind,
            name: 'main',
            value: token.trim(),
          });
        } catch (err: unknown) {
          // Se for 409 (já existe), seguimos. Qualquer outro erro propaga.
          const message = formatApiError(err, '');
          if (!message.toLowerCase().includes('ja existe')) {
            throw err;
          }
        }
      }

      // 2. Squad
      const payloadSquad: SquadCreate = {
        slug,
        name: `Squad ${repoName}`,
      };
      const squad = await createSquad(clientId, payloadSquad);

      // 3. Manifest derivado (sem jira_projects — OA vai descobrir)
      const content: ManifestContent = {
        owns: {
          repos: [canonical],
          jira_projects: [],
        },
      };
      await updateManifest(clientId, squad.id, content);

      // 4. Dispara analise
      const result = await runOnboardingAnalysis(clientId, squad.id, [canonical]);

      return { squad_id: squad.id, task_id: result.task_id };
    },
    onSuccess: ({ squad_id, task_id }) => {
      // PR-6 implementa a tela viva. Por enquanto, vai pra placeholder
      // que mostra que análise iniciou.
      navigate(`/setup/analyzing/${squad_id}?task=${task_id}`);
    },
    onError: (err: unknown) => {
      setError(formatApiError(err, 'Falha ao iniciar a análise.'));
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    submitMutation.mutate();
  };

  return (
    <div className="mx-auto max-w-2xl py-12 px-6">
      <Button
        variant="ghost"
        className="mb-6 -ml-3"
        onClick={() => navigate('/setup/start')}
      >
        <ArrowLeft className="mr-1 h-4 w-4" />
        Voltar
      </Button>

      <header className="mb-8 space-y-2">
        <h1 className="text-2xl font-semibold tracking-tight">
          Conecta seu repositório
        </h1>
        <p className="text-sm text-muted-foreground">
          Cola a URL do seu repositório principal. Você pode adicionar
          outros depois sem refazer setup.
        </p>
      </header>

      <form onSubmit={handleSubmit} className="space-y-6">
        <div className="space-y-1.5">
          <Label htmlFor="repo-url">Repositório GitHub</Label>
          <Input
            id="repo-url"
            type="url"
            placeholder="https://github.com/seu-usuario/seu-repositorio"
            value={repoUrl}
            onChange={(e) => setRepoUrl(e.target.value)}
            autoFocus
            required
          />
          <DetectionFeedback detection={detection} />
        </div>

        {showTokenInput && (
          <div className="space-y-3 rounded-md border bg-muted/30 p-4">
            <div className="flex items-center gap-2 text-sm font-medium">
              <Lock className="h-4 w-4" />
              Esse repo é privado — preciso de um token do GitHub
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="gh-token">Personal Access Token</Label>
              <Input
                id="gh-token"
                type="password"
                placeholder="ghp_…"
                value={token}
                onChange={(e) => setToken(e.target.value)}
              />
              <button
                type="button"
                onClick={() => setHowtoOpen((v) => !v)}
                className="mt-2 flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
              >
                {howtoOpen
                  ? <ChevronUp className="h-3 w-3" />
                  : <ChevronDown className="h-3 w-3" />}
                Como criar um token (1 min)
              </button>
              {howtoOpen && <TokenHowto />}
            </div>
          </div>
        )}

        {error && (
          <div className="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive">
            <AlertCircle className="mt-0.5 h-4 w-4 flex-shrink-0" />
            <span>{error}</span>
          </div>
        )}

        <Button
          type="submit"
          className="w-full"
          disabled={!canSubmit || submitMutation.isPending}
        >
          {submitMutation.isPending ? (
            <>
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              Conectando e iniciando análise…
            </>
          ) : (
            'Conectar e começar análise →'
          )}
        </Button>
      </form>

      <MultiRepoNote />
    </div>
  );
}


function DetectionFeedback({ detection }: { detection: Detection }) {
  if (detection.kind === 'idle') return null;
  if (detection.kind === 'loading') {
    return (
      <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
        <Loader2 className="h-3 w-3 animate-spin" />
        Verificando…
      </p>
    );
  }
  if (detection.kind === 'invalid') {
    return (
      <p className="flex items-start gap-1.5 text-xs text-destructive">
        <AlertCircle className="mt-0.5 h-3 w-3 flex-shrink-0" />
        {detection.message}
      </p>
    );
  }
  if (detection.kind === 'public') {
    return (
      <p className="flex items-center gap-1.5 text-xs text-emerald-700 dark:text-emerald-400">
        <CheckCircle2 className="h-3 w-3" />
        Repositório público encontrado ({detection.data.owner}/{detection.data.repo}, branch <code className="font-mono">{detection.data.default_branch}</code>).
      </p>
    );
  }
  if (detection.kind === 'accessible_with_token') {
    return (
      <p className="flex items-center gap-1.5 text-xs text-emerald-700 dark:text-emerald-400">
        <CheckCircle2 className="h-3 w-3" />
        Token validado ({detection.data.owner}/{detection.data.repo}, branch <code className="font-mono">{detection.data.default_branch}</code>).
      </p>
    );
  }
  if (detection.kind === 'private_needs_token') {
    return (
      <p className="flex items-start gap-1.5 text-xs text-amber-700 dark:text-amber-400">
        <Lock className="mt-0.5 h-3 w-3 flex-shrink-0" />
        {detection.message}
      </p>
    );
  }
  if (detection.kind === 'token_invalid') {
    return (
      <p className="flex items-start gap-1.5 text-xs text-destructive">
        <KeyRound className="mt-0.5 h-3 w-3 flex-shrink-0" />
        {detection.message}
      </p>
    );
  }
  if (detection.kind === 'network_error') {
    return (
      <p className="flex items-start gap-1.5 text-xs text-destructive">
        <AlertCircle className="mt-0.5 h-3 w-3 flex-shrink-0" />
        {detection.message}
      </p>
    );
  }
  return null;
}


function TokenHowto() {
  return (
    <div className="mt-2 space-y-3 rounded-md border bg-background p-4 text-xs">
      <ol className="space-y-2 text-foreground/80">
        <li>
          1. No GitHub, vá em <strong>Settings → Developer settings →
          Personal access tokens → Tokens (classic) → Generate new
          token</strong>.
        </li>
        <li>2. Dê um nome descritivo (ex: <code>dev-autonomo</code>).</li>
        <li>3. Expira em <strong>90 dias</strong> (recomendado).</li>
        <li>
          4. Marque <strong>APENAS</strong> o escopo:{' '}
          <code className="rounded bg-muted px-1">repo</code> (Full
          control of private repos). Nada mais.
        </li>
        <li>5. <strong>Generate</strong> → copia (começa com <code>ghp_</code>).</li>
      </ol>
      <a
        href={TOKEN_HOWTO_GITHUB_URL}
        target="_blank"
        rel="noopener noreferrer"
        className="inline-flex items-center gap-1 text-primary hover:underline"
      >
        <ExternalLink className="h-3 w-3" />
        Abrir GitHub direto na página de criação (escopo <code>repo</code> pré-marcado)
      </a>
      <p className="text-muted-foreground">
        🔒 O token é cifrado com a chave da sua tenant e fica guardado só
        aqui. Pode revogar a qualquer momento no GitHub ou em
        "Credenciais" no seu painel.
      </p>
    </div>
  );
}


function MultiRepoNote() {
  // Placeholder honesto: multi-repo no setup inicial é melhoria futura.
  // No PR-3 atual o backend indexa o primeiro repo apenas. Botao visivel
  // explicaria isso ao cliente em vez de fingir suporte que nao existe.
  return (
    <p className="mt-8 text-center text-xs text-muted-foreground">
      Multi-repo no setup inicial chega numa próxima versão. Por enquanto,
      adicione 1 repo agora — você pode adicionar mais depois pela tela da squad.
    </p>
  );
}

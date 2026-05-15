import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMutation } from '@tanstack/react-query';
import { ArrowLeft, Loader2, AlertCircle, Sparkles } from 'lucide-react';

import { useClientId } from '@/lib/use-client-id';
import { api, createSquad, type SquadCreate } from '@/lib/api';
import { formatApiError } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';

/**
 * Tela B1 — "Conta sobre seu projeto" (cenário B do redesign).
 *
 * Cliente clicou em "Estou começando do zero" na Tela 0. Descreve o
 * projeto em texto livre. Submit cria squad + dispara análise greenfield.
 *
 * Limites: mín 50 chars (evita "teste"), máx 5000 (custo Claude).
 * Upload de materiais opcional (B2) e scaffold opt-in vêm em PR adicional
 * dentro do S-1.
 */

const MIN_CHARS = 50;
const MAX_CHARS = 5000;
const NEAR_LIMIT_WARNING = 4500;

const PLACEHOLDER = `Ex: Vou fazer um SaaS de gestão pra psicólogos. Quero agenda, prontuário criptografado, cobrança recorrente. Pensei em Python no backend (já conheço) e React/Vite no frontend, mas não tenho certeza. Público é consultório de 1 a 5 profissionais.`;


export default function SetupGreenfieldDescribePage() {
  const navigate = useNavigate();
  const clientId = useClientId();
  const [text, setText] = useState('');
  const [error, setError] = useState<string | null>(null);

  const chars = text.length;
  const canSubmit = chars >= MIN_CHARS && chars <= MAX_CHARS;
  const nearLimit = chars >= NEAR_LIMIT_WARNING;

  const submitMutation = useMutation({
    mutationFn: async () => {
      // 1. Cria squad (slug derivado de timestamp ou similar)
      const slug = `squad-${Date.now()}`;
      const payloadSquad: SquadCreate = {
        slug,
        name: `Squad ${new Date().toLocaleDateString('pt-BR')}`,
      };
      const squad = await createSquad(clientId, payloadSquad);

      // 2. Dispara análise greenfield
      const { data } = await api.post(
        `/client/squads/${squad.id}/run-greenfield-analysis`,
        { description: text.trim() },
        { headers: { 'X-Client-Id': clientId } },
      );

      return { squad_id: squad.id, task_id: data.task_id };
    },
    onSuccess: ({ squad_id, task_id }) => {
      navigate(`/setup/analyzing/${squad_id}?task=${task_id}&mode=greenfield`);
    },
    onError: (err: unknown) => {
      setError(formatApiError(err, 'Falha ao iniciar a análise.'));
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!canSubmit) return;
    submitMutation.mutate();
  };

  return (
    <div className="mx-auto max-w-2xl py-12 px-6">
      <Button
        variant="ghost"
        className="mb-6 -ml-3"
        onClick={() => navigate('/setup')}
      >
        <ArrowLeft className="mr-1 h-4 w-4" />
        Voltar
      </Button>

      <header className="mb-8 space-y-2">
        <div className="flex items-center gap-2">
          <Sparkles className="h-6 w-6 text-primary" />
          <h1 className="text-2xl font-semibold tracking-tight">
            Conta sobre seu projeto
          </h1>
        </div>
        <p className="text-sm text-muted-foreground">
          Quanto mais detalhe, melhor a proposta de stack e agentes que eu vou
          conseguir fazer. Pode escrever como se falasse com um colega.
        </p>
      </header>

      <form onSubmit={handleSubmit} className="space-y-6">
        <div className="space-y-1.5">
          <Label htmlFor="description">Descrição do projeto</Label>
          <textarea
            id="description"
            value={text}
            onChange={(e) => setText(e.target.value.slice(0, MAX_CHARS))}
            placeholder={PLACEHOLDER}
            rows={10}
            autoFocus
            className="min-h-[240px] w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm leading-relaxed shadow-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary"
          />
          <div className="flex items-center justify-between text-xs">
            <span
              className={
                chars < MIN_CHARS
                  ? 'text-muted-foreground'
                  : 'text-emerald-700 dark:text-emerald-400'
              }
            >
              {chars} / {MAX_CHARS} caracteres
              {chars < MIN_CHARS && chars > 0 && (
                <span className="ml-2 text-muted-foreground">
                  · escreva pelo menos {MIN_CHARS} pra eu ter contexto
                </span>
              )}
            </span>
            {nearLimit && (
              <span className="text-amber-700 dark:text-amber-400">
                Aproximando do limite — vou pedir pra resumir se passar
              </span>
            )}
          </div>
        </div>

        <div className="rounded-md border bg-muted/30 p-4">
          <p className="mb-2 text-xs font-medium">💡 Vale incluir:</p>
          <ul className="space-y-1 text-xs text-muted-foreground">
            <li>• O que você quer construir</li>
            <li>• Pra quem vai servir</li>
            <li>• Stack que você já decidiu (ou se ainda não decidiu)</li>
            <li>• Restrições, integrações esperadas, referências</li>
          </ul>
        </div>

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
              Criando squad e iniciando análise…
            </>
          ) : (
            'Próximo →'
          )}
        </Button>

        <p className="text-center text-xs text-muted-foreground">
          Upload de materiais de referência (PDFs, mockups, etc.) e scaffold
          inicial vêm em uma próxima atualização.
        </p>
      </form>
    </div>
  );
}

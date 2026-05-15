import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ArrowLeft, ArrowRight, Brain, Code2, Shield, Layers,
  CheckCircle2,
} from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';

/**
 * Tela C — Tour/Demo (D-14 do redesign, S-9).
 *
 * 3 passos sequenciais que explicam o produto sem pedir nada do cliente:
 *   1. "O que esses agentes fazem?" — descrição de cada tier
 *   2. "Como uma demanda flui?" — mock do diagrama de pipeline
 *   3. "Pronto pra começar?" — CTA pra voltar à Tela 0
 *
 * Implementação puramente client-side. Sem mock animado da pipeline em
 * tempo real (fica como melhoria futura — bastaria adicionar timers
 * client-side se quisermos).
 */
export default function SetupExplorePage() {
  const navigate = useNavigate();
  const [step, setStep] = useState(0);
  const totalSteps = 3;

  return (
    <div className="mx-auto max-w-2xl py-12 px-6 space-y-6">
      <Button
        variant="ghost"
        size="sm"
        className="-ml-2"
        onClick={() => navigate('/setup')}
      >
        <ArrowLeft className="mr-1 h-3 w-3" />
        Voltar
      </Button>

      <div className="flex items-center gap-1 text-xs text-muted-foreground">
        Passo {step + 1} de {totalSteps}
      </div>

      <Card>
        <CardContent className="p-8">
          {step === 0 && <StepAgents />}
          {step === 1 && <StepPipeline />}
          {step === 2 && <StepReady onStart={() => navigate('/setup')} />}
        </CardContent>
      </Card>

      <div className="flex justify-between">
        <Button
          variant="outline"
          disabled={step === 0}
          onClick={() => setStep(s => s - 1)}
        >
          <ArrowLeft className="mr-1 h-3 w-3" />
          Anterior
        </Button>
        {step < totalSteps - 1 && (
          <Button onClick={() => setStep(s => s + 1)}>
            Próximo
            <ArrowRight className="ml-1 h-3 w-3" />
          </Button>
        )}
      </div>
    </div>
  );
}


function StepAgents() {
  return (
    <div className="space-y-5">
      <h1 className="text-2xl font-semibold tracking-tight">
        O que esses agentes fazem?
      </h1>
      <p className="text-sm text-muted-foreground">
        Uma squad típica tem 4 papéis. Cada um cobre uma parte do trabalho de
        desenvolvimento — refinement, planejamento, código, review.
      </p>

      <ul className="space-y-4">
        <AgentRow
          icon={<Brain className="h-5 w-5" />}
          tier="Business Analyst"
          description="Pega uma demanda crua do Jira e refina em critérios de aceite claros, testáveis. Garante que o time vai construir a coisa certa."
        />
        <AgentRow
          icon={<Layers className="h-5 w-5" />}
          tier="Architect"
          description="Decompõe a demanda em sub-tarefas e delega pra Dev(s) — em paralelo quando toca múltiplas áreas. Coordenador da pipeline."
        />
        <AgentRow
          icon={<Code2 className="h-5 w-5" />}
          tier="Dev"
          description="Especialista numa stack (Python/FastAPI, React, etc.). Implementa o código, escreve testes, abre PR. Pode ter 1 ou mais Devs por squad."
        />
        <AgentRow
          icon={<Shield className="h-5 w-5" />}
          tier="Reviewer (opcional)"
          description="Revisa o PR antes do humano. Pega problemas óbvios e propõe ajustes — quality gate barato. Você ainda dá o OK final."
        />
      </ul>
    </div>
  );
}


function StepPipeline() {
  return (
    <div className="space-y-5">
      <h1 className="text-2xl font-semibold tracking-tight">
        Como uma demanda flui?
      </h1>
      <p className="text-sm text-muted-foreground">
        Toda demanda (do Jira ou criada direto no painel) passa pelo mesmo
        fluxo. Você intervém só quando o sistema precisa de você.
      </p>

      <div className="rounded-md border bg-muted/20 p-4 font-mono text-xs leading-relaxed text-foreground/80">
        <div>📋 Issue chega (Jira ou painel)</div>
        <div className="pl-4 text-muted-foreground">↓</div>
        <div>🧠 BA refina em ACs claros</div>
        <div className="pl-4 text-muted-foreground">↓</div>
        <div>🏗 Architect planeja e delega</div>
        <div className="pl-4 text-muted-foreground">↓</div>
        <div>🐍 Dev(s) implementam (em paralelo se multi-stack)</div>
        <div className="pl-4 text-muted-foreground">↓</div>
        <div>📥 PR aberto</div>
        <div className="pl-4 text-muted-foreground">↓</div>
        <div>🔍 Reviewer audita</div>
        <div className="pl-4 text-muted-foreground">↓</div>
        <div>👤 Você aprova ou ajusta</div>
        <div className="pl-4 text-muted-foreground">↓</div>
        <div>✅ Merge</div>
      </div>

      <p className="text-xs text-muted-foreground">
        Cada etapa registra custo individual, timeline e output que você pode
        auditar no detalhe da task.
      </p>
    </div>
  );
}


function StepReady({ onStart }: { onStart: () => void }) {
  return (
    <div className="space-y-5 text-center">
      <CheckCircle2 className="mx-auto h-10 w-10 text-emerald-600 dark:text-emerald-400" />
      <h1 className="text-2xl font-semibold tracking-tight">
        Pronto pra começar?
      </h1>
      <p className="text-sm text-muted-foreground">
        Você pode escolher entre 2 caminhos pra montar sua primeira squad:
        colar uma URL de repositório existente (cenário A) ou descrever um
        projeto novo do zero (cenário B).
      </p>
      <Button size="lg" onClick={onStart} className="mt-2">
        Começar minha squad
        <ArrowRight className="ml-2 h-4 w-4" />
      </Button>
    </div>
  );
}


function AgentRow({
  icon, tier, description,
}: { icon: React.ReactNode; tier: string; description: string }) {
  return (
    <li className="flex items-start gap-3">
      <div className="rounded-md bg-muted p-2 text-foreground/70">{icon}</div>
      <div className="flex-1">
        <p className="text-sm font-semibold">{tier}</p>
        <p className="mt-0.5 text-xs text-muted-foreground">{description}</p>
      </div>
    </li>
  );
}

import { useNavigate, useParams } from 'react-router-dom';
import { CheckCircle2, MessageSquare, Bot, Users } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';

/**
 * Tela 4 — Squad ativa (PR-8 entrega versão final; PR-7 ja deixa pronta
 * como destino do botão "Ativar minha squad").
 *
 * Confirmação concreta + 3 cards de next steps.
 */
export default function SetupReadyPage() {
  const navigate = useNavigate();
  const { squadId } = useParams<{ squadId: string }>();

  return (
    <div className="mx-auto max-w-2xl py-12 px-6">
      <header className="mb-8 space-y-3">
        <div className="flex items-center gap-2">
          <CheckCircle2 className="h-6 w-6 text-emerald-600 dark:text-emerald-400" />
          <h1 className="text-2xl font-semibold tracking-tight">
            Sua squad está ativa
          </h1>
        </div>
        <p className="text-muted-foreground">
          Provisionei seus agentes na Anthropic e conectei tudo. Quando você
          criar uma demanda no Jira (com <code>@agents</code> na descrição)
          ou direto pelo painel, sua squad começa a trabalhar.
        </p>
      </header>

      <div className="grid gap-4">
        <NextStepCard
          icon={<MessageSquare className="h-5 w-5" />}
          title="Crie sua primeira demanda"
          description="Pode ser no Jira (com @agents na descrição) ou direto aqui no painel."
          cta="Criar primeira demanda →"
          onClick={() => navigate(`/squads/${squadId}`)}
          primary
        />
        <NextStepCard
          icon={<Bot className="h-5 w-5" />}
          title="Ver sua squad em ação"
          description="Veja os agentes provisionados, prompts atuais, custos acumulados, histórico de runs."
          cta="Abrir painel da squad →"
          onClick={() => navigate(`/squads/${squadId}`)}
        />
        <NextStepCard
          icon={<Users className="h-5 w-5" />}
          title="Convidar mais pessoas do time"
          description="Adicione reviewers que aprovam PRs ou viewers que só acompanham."
          cta="Gerenciar membros →"
          onClick={() => navigate('/dashboard')}
        />
      </div>
    </div>
  );
}


interface NextStepCardProps {
  icon: React.ReactNode;
  title: string;
  description: string;
  cta: string;
  onClick: () => void;
  primary?: boolean;
}

function NextStepCard({
  icon, title, description, cta, onClick, primary = false,
}: NextStepCardProps) {
  return (
    <Card className={primary ? 'border-primary/40' : ''}>
      <CardContent className="space-y-3 p-5">
        <div className="flex items-center gap-3">
          <div
            className={`rounded-md p-2 ${
              primary ? 'bg-primary/10 text-primary' : 'bg-muted text-foreground/70'
            }`}
          >
            {icon}
          </div>
          <h2 className="text-base font-semibold">{title}</h2>
        </div>
        <p className="text-sm text-muted-foreground">{description}</p>
        <Button
          onClick={onClick}
          variant={primary ? 'default' : 'outline'}
          className="w-full"
        >
          {cta}
        </Button>
      </CardContent>
    </Card>
  );
}

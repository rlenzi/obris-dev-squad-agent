import { useNavigate } from 'react-router-dom';
import { Package, Sparkles, Compass } from 'lucide-react';

import { useAuth } from '@/lib/auth';
import { Card, CardContent } from '@/components/ui/card';

/**
 * Tela 0 — Porta de entrada do redesign do onboarding (PR-4 de 8).
 *
 * Classifica o cliente em 3 caminhos ANTES de pedir qualquer dado:
 *   1. Tem repositório existente → caminho A (cenário Orbis)
 *   2. Começando do zero → caminho B (greenfield, ainda em design)
 *   3. Explorando → caminho C (tour, ainda em design)
 *
 * Esta tela vive em /setup/start. O wizard antigo continua em /setup
 * até PR-8 fazer o switch final que aponta o gate de setup direto pra
 * tela 0.
 *
 * Princípios visuais:
 *   - 3 cards paritários (nenhum "recomendado")
 *   - Tempo estimado em cada card pra dar honestidade
 *   - Rodapé "pode mudar depois" desarma ansiedade
 *   - Voz em primeira pessoa ("Vou te ajudar a montar...")
 */
export default function SetupChoicePage() {
  const navigate = useNavigate();
  const { me } = useAuth();

  const greetingName =
    me?.user.full_name?.split(' ')[0] ?? me?.user.email?.split('@')[0] ?? null;

  return (
    <div className="mx-auto max-w-3xl py-12 px-6">
      <header className="mb-10 space-y-3">
        <h1 className="text-2xl font-semibold tracking-tight">
          {greetingName ? `Olá, ${greetingName}.` : 'Olá!'} Vou te ajudar a montar sua squad.
        </h1>
        <p className="text-muted-foreground">
          Os agentes vão trabalhar com você — refinar demandas, planejar, codar,
          revisar. Antes, me conta de onde você está partindo:
        </p>
      </header>

      <div className="grid gap-4">
        <ChoiceCard
          icon={<Package className="h-6 w-6" />}
          title="Tenho um repositório rodando"
          description={
            'Vou colar a URL e o sistema vai entender meu código pra propor ' +
            'os agentes certos.'
          }
          duration="~10 min"
          onClick={() => navigate('/setup/repository')}
        />
        <ChoiceCard
          icon={<Sparkles className="h-6 w-6" />}
          title="Estou começando do zero"
          description={
            'Vou descrever o projeto em texto e o sistema vai propor stack + ' +
            'agentes alinhados.'
          }
          duration="~5 min"
          onClick={() => navigate('/setup/greenfield')}
        />
        <ChoiceCard
          icon={<Compass className="h-6 w-6" />}
          title="Ainda estou explorando"
          description={
            'Quero ver um exemplo antes de configurar.'
          }
          duration="~2 min"
          onClick={() => navigate('/setup/explore')}
        />
      </div>

      <p className="mt-10 text-center text-sm text-muted-foreground">
        Pode mudar depois — nada aqui é definitivo.
      </p>
    </div>
  );
}


interface ChoiceCardProps {
  icon: React.ReactNode;
  title: string;
  description: string;
  duration: string;
  onClick: () => void;
}

function ChoiceCard({ icon, title, description, duration, onClick }: ChoiceCardProps) {
  return (
    <Card
      role="button"
      tabIndex={0}
      className="group cursor-pointer transition hover:border-primary hover:shadow-sm focus-visible:border-primary focus-visible:ring-1 focus-visible:ring-primary"
      onClick={onClick}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onClick();
        }
      }}
    >
      <CardContent className="flex items-start gap-4 p-5">
        <div className="mt-0.5 rounded-md bg-muted p-2 text-foreground/70 transition group-hover:bg-primary/10 group-hover:text-primary">
          {icon}
        </div>
        <div className="flex-1">
          <div className="flex items-center justify-between gap-2">
            <h2 className="text-base font-semibold">{title}</h2>
            <span className="text-xs text-muted-foreground">{duration}</span>
          </div>
          <p className="mt-1 text-sm text-muted-foreground">{description}</p>
        </div>
      </CardContent>
    </Card>
  );
}

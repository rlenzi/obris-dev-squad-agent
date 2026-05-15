import { useNavigate } from 'react-router-dom';
import { Sparkles, ArrowLeft } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';

/**
 * Placeholder do caminho "Estou começando do zero" (cenário B do redesign).
 *
 * O fluxo greenfield ainda não foi desenhado em detalhe — está no TODO de
 * design pós-implementação (ver docs/redesign-onboarding-2026-05-14.md
 * seção "Próximas rodadas de design"). Esta página existe pra dar UX
 * coerente: cliente clica no card da tela 0 e vê uma página que explica
 * o que está acontecendo, em vez de erro 404.
 */
export default function SetupGreenfieldPlaceholderPage() {
  const navigate = useNavigate();
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
      <Card>
        <CardContent className="space-y-4 p-8">
          <div className="flex items-center gap-3">
            <div className="rounded-md bg-muted p-2">
              <Sparkles className="h-6 w-6 text-foreground/70" />
            </div>
            <h1 className="text-xl font-semibold">Começar do zero</h1>
          </div>
          <p className="text-muted-foreground">
            Esse caminho ainda está sendo desenhado. A ideia é que você
            descreva seu projeto em texto livre (stack desejada, público,
            objetivos), suba materiais de referência opcionais (PRDs,
            mockups, exemplos de API) e o sistema crie a squad com agentes
            alinhados — sem você precisar de código existente.
          </p>
          <p className="text-muted-foreground">
            Por enquanto, se você quiser começar agora, recomendo criar um
            repositório vazio (mesmo com só o README) e usar o caminho{' '}
            <strong>"Tenho um repositório rodando"</strong>. Funciona como
            ponto de partida, e a gente expande quando o fluxo greenfield
            estiver pronto.
          </p>
          <div className="flex gap-3 pt-2">
            <Button onClick={() => navigate('/setup/start')} variant="outline">
              Voltar e escolher outro caminho
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

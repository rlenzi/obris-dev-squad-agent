import { useNavigate } from 'react-router-dom';
import { Compass, ArrowLeft } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';

/**
 * Placeholder do caminho "Ainda estou explorando" (cenário C do redesign).
 *
 * Tour interativo ou demo de squad fictícia em ação ainda não foi
 * desenhado — fica no TODO pós-implementação.
 */
export default function SetupExplorePlaceholderPage() {
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
              <Compass className="h-6 w-6 text-foreground/70" />
            </div>
            <h1 className="text-xl font-semibold">Explorando a plataforma</h1>
          </div>
          <p className="text-muted-foreground">
            Um tour interativo da plataforma ainda está em construção.
            Enquanto isso, você pode entender o que a plataforma faz lendo
            a documentação do projeto, ou seguir um dos caminhos
            ao lado se quiser começar de fato.
          </p>
          <div className="flex gap-3 pt-2">
            <Button onClick={() => navigate('/setup/start')} variant="outline">
              Voltar
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

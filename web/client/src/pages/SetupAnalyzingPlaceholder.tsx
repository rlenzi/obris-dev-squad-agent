import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { Loader2 } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';

/**
 * Placeholder da Tela 2 — Análise viva. PR-6 vai implementar a UI real
 * com polling do /onboarding-status e estados granulares por etapa.
 *
 * Por enquanto, esta página mostra que a análise foi iniciada e dá
 * caminho pro cliente acompanhar pelo painel da squad.
 */
export default function SetupAnalyzingPlaceholderPage() {
  const { squadId } = useParams<{ squadId: string }>();
  const [params] = useSearchParams();
  const taskId = params.get('task');
  const navigate = useNavigate();

  return (
    <div className="mx-auto max-w-2xl py-12 px-6">
      <Card>
        <CardContent className="space-y-4 p-8">
          <div className="flex items-center gap-3">
            <Loader2 className="h-6 w-6 animate-spin text-primary" />
            <h1 className="text-xl font-semibold">Analisando seu código…</h1>
          </div>
          <p className="text-muted-foreground">
            Iniciei a análise da squad{' '}
            {squadId && (
              <code className="rounded bg-muted px-1 text-xs">{squadId}</code>
            )}{' '}
            {taskId && (
              <>
                (task <code className="rounded bg-muted px-1 text-xs">{taskId}</code>)
              </>
            )}
            . Esta tela ainda mostra o estado mínimo — a versão viva com 6
            etapas e mensagens em primeira pessoa chega no próximo PR.
          </p>
          <p className="text-muted-foreground">
            Você pode fechar essa aba e voltar — a análise continua rodando
            em background. Acompanhe pelo painel da squad ou pela tela
            inicial.
          </p>
          <div className="flex gap-3 pt-2">
            <Button onClick={() => navigate('/dashboard')} variant="outline">
              Ir pro painel
            </Button>
            <Button onClick={() => navigate('/setup/start')} variant="ghost">
              Voltar ao início
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

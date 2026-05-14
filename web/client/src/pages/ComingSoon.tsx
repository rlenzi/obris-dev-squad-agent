import { Construction } from 'lucide-react';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';

export default function ComingSoonPage({
  title,
  description,
}: {
  title: string;
  description?: string;
}) {
  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <div className="grid size-14 place-items-center rounded-lg bg-muted">
          <Construction className="size-7 text-muted-foreground" />
        </div>
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">{title}</h1>
          <p className="text-muted-foreground">Em construção</p>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Disponível em breve</CardTitle>
          {description && <CardDescription>{description}</CardDescription>}
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">
          Esta página faz parte da Fase 1 do painel cliente. Está sendo
          construída.
        </CardContent>
      </Card>
    </div>
  );
}

import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Bot,
  Cpu,
  FileCode,
  KeyRound,
  Search,
  Sparkles,
  Wrench,
} from 'lucide-react';
import { fetchSkillTemplates, type AgentTier, type SkillTemplate } from '@/lib/api';
import { Badge } from '@/components/ui/badge';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';

const TIER_FILTERS: { value: AgentTier | 'all'; label: string }[] = [
  { value: 'all', label: 'Todos' },
  { value: 'ba', label: 'BA' },
  { value: 'architect', label: 'Architect' },
  { value: 'dev', label: 'Dev' },
  { value: 'reviewer', label: 'Reviewer' },
  { value: 'onboarding_analyst', label: 'Onboarding' },
];

export default function SkillsCatalogPage() {
  const [filter, setFilter] = useState<AgentTier | 'all'>('all');
  const [search, setSearch] = useState('');
  const [selected, setSelected] = useState<SkillTemplate | null>(null);

  const skillsQuery = useQuery({
    queryKey: ['skill-templates'],
    queryFn: fetchSkillTemplates,
  });

  const all = skillsQuery.data ?? [];

  const filtered = useMemo(() => {
    let list = all;
    if (filter !== 'all') {
      list = list.filter((s) => s.tier === filter);
    }
    if (search.trim()) {
      const q = search.toLowerCase();
      list = list.filter(
        (s) =>
          s.slug.toLowerCase().includes(q) ||
          s.name.toLowerCase().includes(q) ||
          (s.description ?? '').toLowerCase().includes(q),
      );
    }
    return list;
  }, [all, filter, search]);

  // Seleciona o primeiro automaticamente
  if (filtered.length > 0 && !selected) {
    setSelected(filtered[0]);
  }
  if (selected && !filtered.find((s) => s.id === selected.id)) {
    setSelected(filtered[0] ?? null);
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <div className="grid size-14 place-items-center rounded-lg bg-brand-500/10">
          <Sparkles className="size-7 text-brand-500" />
        </div>
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">Catálogo de Skills</h1>
          <p className="text-muted-foreground">
            Templates de agente disponíveis na plataforma
          </p>
        </div>
      </div>

      {/* Filtros */}
      <div className="flex flex-wrap items-center gap-2">
        {TIER_FILTERS.map((t) => (
          <Badge
            key={t.value}
            variant={filter === t.value ? 'default' : 'outline'}
            className="cursor-pointer"
            onClick={() => setFilter(t.value)}
          >
            {t.label}
          </Badge>
        ))}
        <div className="ml-auto flex w-full max-w-xs items-center gap-2 rounded-md border bg-card px-3 py-1.5">
          <Search className="size-4 text-muted-foreground" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Buscar slug, nome ou descrição…"
            className="flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
          />
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        {/* Lista */}
        <div className="space-y-2 lg:col-span-1">
          {skillsQuery.isLoading && (
            <p className="text-sm text-muted-foreground">Carregando…</p>
          )}
          {filtered.length === 0 && !skillsQuery.isLoading && (
            <p className="text-sm italic text-muted-foreground">
              Nenhum template encontrado com os filtros atuais.
            </p>
          )}
          {filtered.map((s) => (
            <button
              key={s.id}
              onClick={() => setSelected(s)}
              className={
                'w-full rounded-md border bg-card p-3 text-left transition-colors hover:border-brand-500 ' +
                (selected?.id === s.id ? 'border-brand-500 bg-brand-500/5' : 'border-border')
              }
            >
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-medium">{s.name}</div>
                  <div className="truncate font-mono text-xs text-muted-foreground">
                    {s.slug} (v{s.version})
                  </div>
                </div>
                <Badge variant="outline" className="shrink-0 text-[10px]">
                  {s.tier.toUpperCase()}
                </Badge>
              </div>
            </button>
          ))}
        </div>

        {/* Detalhe */}
        <div className="lg:col-span-2">
          {selected ? <SkillDetail skill={selected} /> : null}
        </div>
      </div>
    </div>
  );
}

function SkillDetail({ skill }: { skill: SkillTemplate }) {
  return (
    <div className="space-y-4">
      {/* Header */}
      <Card>
        <CardHeader>
          <div className="flex items-start justify-between gap-3">
            <div>
              <CardTitle>{skill.name}</CardTitle>
              <CardDescription>
                <code className="font-mono">{skill.slug}</code> (v{skill.version})
              </CardDescription>
            </div>
            <Badge variant="default">{skill.tier.toUpperCase()}</Badge>
          </div>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          {skill.description && (
            <p className="text-muted-foreground">{skill.description}</p>
          )}
          <div className="flex flex-wrap gap-2">
            <Badge variant="secondary">
              <Cpu className="mr-1 size-3" />
              {skill.model_alias}
            </Badge>
            {skill.active ? (
              <Badge variant="success">Ativo</Badge>
            ) : (
              <Badge variant="muted">Inativo</Badge>
            )}
            {skill.client_id === null && (
              <Badge variant="outline">System template</Badge>
            )}
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader className="flex flex-row items-center gap-2 space-y-0">
            <Wrench className="size-5 text-brand-500" />
            <CardTitle className="text-base">Tools</CardTitle>
          </CardHeader>
          <CardContent>
            {skill.tools_enabled.length === 0 ? (
              <p className="text-sm italic text-muted-foreground">Nenhuma tool habilitada.</p>
            ) : (
              <div className="flex flex-wrap gap-1">
                {skill.tools_enabled.map((t, i) => (
                  <Badge key={i} variant="secondary" className="font-mono text-xs">
                    {String(t)}
                  </Badge>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center gap-2 space-y-0">
            <KeyRound className="size-5 text-brand-500" />
            <CardTitle className="text-base">Knowledge partitions</CardTitle>
          </CardHeader>
          <CardContent>
            {skill.knowledge_partitions.length === 0 ? (
              <p className="text-sm italic text-muted-foreground">Sem partições.</p>
            ) : (
              <ul className="space-y-1">
                {skill.knowledge_partitions.map((p, i) => (
                  <li key={i} className="rounded bg-muted px-2 py-1 font-mono text-xs">
                    {String(p)}
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader className="flex flex-row items-center gap-2 space-y-0">
          <FileCode className="size-5 text-brand-500" />
          <CardTitle className="text-base">System prompt</CardTitle>
        </CardHeader>
        <CardContent>
          <code className="block rounded bg-muted px-3 py-2 font-mono text-sm">
            {skill.system_prompt_ref}
          </code>
          <p className="mt-2 text-xs text-muted-foreground">
            Referência ao arquivo no repo <code>dev-autonomo-config</code> (futuro). Carregado em runtime.
          </p>
        </CardContent>
      </Card>

      {Object.keys(skill.stack_primary ?? {}).length > 0 && (
        <Card>
          <CardHeader className="flex flex-row items-center gap-2 space-y-0">
            <Bot className="size-5 text-brand-500" />
            <CardTitle className="text-base">Stack</CardTitle>
          </CardHeader>
          <CardContent>
            <pre className="overflow-x-auto rounded bg-muted p-3 font-mono text-xs">
              {JSON.stringify(skill.stack_primary, null, 2)}
            </pre>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

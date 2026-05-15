# Redesign do onboarding cliente — 2026-05-14

> Sessão de design conduzida em 2026-05-14 entre Rubens (tech lead) e Claude.
> Captura as decisões de produto pra refazer o fluxo de setup do painel cliente.
>
> **Estado:** cenário A (cliente com código existente) **desenhado**.
> **Pendente de desenho:** cenário B (greenfield), cenário C (explorando), modais (editar/remover/adicionar agente), painel da squad (stacks/repos/agentes/cross-squad), fluxo de adicionar repo pós-setup, tela "criar primeira demanda".
>
> **⚠ Importante:** este doc cobre **só o cenário A**. A implementação dos PRs descritos abaixo entrega só essa parte. Antes ou depois de implementar A, o time precisa **retomar a sessão de design** pra cobrir B, C e detalhes — ver seção "Próximas rodadas de design" no fim.

---

## Contexto e motivação

O wizard cliente atual (6 passos: Boas-vindas, Credenciais, Squad, Manifesto, Análise & Agentes, Revisão) é um formulário burocrático que assume "todo cliente tem código". No dogfooding com a Orbis, expôs três problemas estruturais:

1. **Análise raquítica** — o Onboarding Analyst só extrai um `manifest.json`. Não indexa RAG, não detecta padrões finos, não propõe agentes com base no que viu.
2. **Greenfield sem caminho** — quem não tem código fica órfão: o wizard exige repo (validação adicionada no PR #88) sem nenhum fluxo alternativo.
3. **Cliente é examinado, não consultado** — preenche 6 campos antes de qualquer valor aparecer. A análise serve só pra confirmar o que ele já declarou no manifest.

Decisão estratégica: refazer o produto colocando o **cliente no centro**. Ele dialoga com o sistema. O sistema mastiga e propõe. Manifesto vira **resultado**, não entrada.

---

## Princípios

1. **Cliente é consultado, não examinado.** Sistema pergunta o mínimo, deriva o máximo.
2. **Voz em primeira pessoa.** O produto fala "Estou clonando…", "Olha o que encontrei…". Não "Sistema processando…".
3. **Credenciais just-in-time.** Só pede credencial quando o sistema descobre que precisa, no contexto. Não como passo formal upfront.
4. **Manifest é resultado da análise**, não input do cliente. Cliente revisa proposta, não preenche formulário.
5. **Stacks são entidades persistentes** da squad — cada stack detectada vira registro no banco (slug/nome/path/framework/convenções) e vive junto com a squad.
6. **Pipeline tem peças essenciais.** Architect + ≥1 Dev são obrigatórios. BA e Reviewer são removíveis, com aviso de consequência.
7. **Cross-squad é opt-in bilateral.** Ambas as squads precisam autorizar pra trocar demandas.
8. **Jira é descoberto, não pedido.** Análise escaneia commits/PR templates pra detectar projetos Jira; sistema sugere conectar.

---

## Cenário A — Cliente com código existente

5 telas em sequência.

### Tela 0 — Porta de entrada

```
┌─────────────────────────────────────────────────────────────┐
│   Olá, [Rubens]. Vou te ajudar a montar sua squad.          │
│                                                             │
│   Os agentes vão trabalhar com você — refinar demandas,     │
│   planejar, codar, revisar. Antes, me conta de onde         │
│   você está partindo:                                       │
│                                                             │
│   ┌──────────────────────────┐                              │
│   │  📦 Tenho um repositório │                              │
│   │  rodando                 │                              │
│   │  Vou colar a URL e o     │                              │
│   │  sistema vai entender    │                              │
│   │  meu código pra propor   │                              │
│   │  os agentes certos.      │                              │
│   │  ~10 min                 │                              │
│   └──────────────────────────┘                              │
│                                                             │
│   ┌──────────────────────────┐                              │
│   │  ✨ Estou começando      │                              │
│   │  do zero                 │                              │
│   │  Vou descrever o projeto │                              │
│   │  em texto e o sistema    │                              │
│   │  vai propor stack +      │                              │
│   │  agentes alinhados.      │                              │
│   │  ~5 min                  │                              │
│   └──────────────────────────┘                              │
│                                                             │
│   ┌──────────────────────────┐                              │
│   │  🧭 Ainda estou          │                              │
│   │  explorando              │                              │
│   │  Quero ver um exemplo    │                              │
│   │  antes de configurar.    │                              │
│   │  ~2 min                  │                              │
│   └──────────────────────────┘                              │
│                                                             │
│   Pode mudar depois — nada aqui é definitivo.               │
└─────────────────────────────────────────────────────────────┘
```

**Decisões:**
- 3 cards **paritários em peso visual** — nenhum tem badge "recomendado". Escolha reflete realidade, não preferência do produto.
- "Tenho repositório" é o primeiro só por frequência esperada em B2B dev.
- **Tempo estimado em cada card** dá honestidade — cliente sabe quanto vai investir.
- Frase "*Pode mudar depois — nada aqui é definitivo*" no rodapé desarma medo de decisão irreversível.
- A tela **não pede dado nenhum** ainda — só classifica.

### Tela 1 — Conectar repositório

```
┌─────────────────────────────────────────────────────────────┐
│  Conecta seu repositório                                    │
│                                                             │
│  Cola a URL do seu repositório principal. Você pode         │
│  adicionar outros depois sem refazer setup.                 │
│                                                             │
│  ┌─────────────────────────────────────────────────┐        │
│  │ https://github.com/_____________________________│        │
│  └─────────────────────────────────────────────────┘        │
│  + adicionar outro repositório                              │
│                                                             │
│  ─── quando detecta privado: ──────────                     │
│                                                             │
│  Esse repo é privado. Preciso de um token do GitHub:        │
│  ┌─────────────────────────────────────────────────┐        │
│  │ ghp_…                                           │        │
│  └─────────────────────────────────────────────────┘        │
│                                                             │
│  ▶ Como criar um token (1 min)                              │
│    [colapsado por default; expansível mostra:               │
│     - Passos numerados no GitHub Settings                   │
│     - Escopo `repo` (Full control of repos) — nada mais     │
│     - Botão atalho pra https://github.com/settings/tokens/  │
│       new?scopes=repo&description=dev-autonomo              │
│     - Aviso de segurança (cifrado, revogável)               │
│    ]                                                        │
│                                                             │
│  [ Conectar e começar análise → ]                           │
└─────────────────────────────────────────────────────────────┘
```

**Decisões:**
- **Apenas 1 input visível** (URL). Slug, nome da squad, domain, descrição, projetos Jira — tudo derivado pela análise. Não pergunta nada disso.
- **Credencial just-in-time**: o input do token só aparece quando o sistema detecta (via HEAD ao GitHub) que o repo é privado. Pra repo público, nem mostra.
- **Bloco expansível "Como criar um token"** colapsado por default. Quem já sabe não tropeça; quem nunca fez tem passo a passo completo aberto inline.
- Botão "**+ adicionar outro repositório**" inline pra cliente com multi-repo coerente (frontend+backend separados). Tela permanece simples pra quem só tem 1 repo.

### Tela 2 — Análise viva

```
┌─────────────────────────────────────────────────────────────┐
│  Analisando seu código                                      │
│                                                             │
│  Pode fechar essa aba e voltar — quando voltar a análise    │
│  continua do mesmo ponto.                                   │
│                                                             │
│  ✓  Clonando repositório                                    │
│     obris-dev-squad-agent · 247 MB                          │
│                                                             │
│  ✓  Escaneando arquivos                                     │
│     1.847 arquivos · 12 diretórios principais               │
│                                                             │
│  ⠿  Indexando conhecimento na RAG da squad                  │
│     ┌─────────────────────────────────────────────────┐     │
│     │ Esse é o passo mais demorado. Estou pegando     │     │
│     │ trechos do seu código e transformando em uma    │     │
│     │ base de busca que os agentes vão consultar      │     │
│     │ depois — quando precisarem entender uma         │     │
│     │ convenção, achar onde algo está implementado    │     │
│     │ ou seguir um padrão que você já usa.            │     │
│     └─────────────────────────────────────────────────┘     │
│     2.134 de 6.890 chunks indexados                         │
│     ████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░  31%               │
│                                                             │
│  ○  Detectando padrões e convenções                         │
│                                                             │
│  ○  Recomendando agentes                                    │
│                                                             │
│                                       ✕ Cancelar análise    │
└─────────────────────────────────────────────────────────────┘
```

**Decisões:**
- **Sem ETA, sem cronômetro**, mas **com progressão real** (etapas mensuráveis mostram contador + barra).
- **Mensagem em prosa primeira pessoa** aparece **só na etapa ativa**. Concluídas: ✓ + resultado seco. Pendentes: ○ + título.
- **Barra de progresso** só quando há quantidade conhecida (chunks indexados). Etapas opacas só têm spinner — não inventa percentual falso.
- Aviso "*pode fechar essa aba e voltar*" no topo — análise persiste no servidor, status persistido em DB.
- **Cancelar** disponível em qualquer momento.
- **Erro** inline na etapa que falhou (ícone `✗` vermelho + mensagem em prosa + botão "Tentar novamente"). Não reinicia do zero — retoma do ponto.

**Mensagens em prosa (uma por etapa):**

- **Clonando repositório:** *"Trazendo seu código pra eu poder ler. Não fico com cópia depois, é só durante a análise."*
- **Escaneando arquivos:** *"Estou olhando arquivo por arquivo pra entender a forma do projeto: que linguagens aparecem, que frameworks são usados, como as pastas estão organizadas, onde está o quê."*
- **Indexando conhecimento na RAG:** *"Esse é o passo mais demorado. Estou pegando trechos do seu código e transformando em uma base de busca que os agentes vão consultar depois — quando precisarem entender uma convenção, achar onde algo está implementado ou seguir um padrão que você já usa."*
- **Detectando padrões e convenções:** *"Agora estou notando como você escreve código no dia a dia: padrões de nome, organização dos testes, estilo dos commits, jeito de fazer PR. Os agentes vão seguir o seu estilo — não inventar um novo."*
- **Recomendando agentes:** *"Com tudo o que vi até agora, estou pensando quais agentes fazem sentido pra sua squad e quais não. Cada um vai cobrir uma área específica do seu projeto."*

### Tela 3 — Resultado e proposta

```
┌─────────────────────────────────────────────────────────────┐
│  ✓  Análise concluída                                       │
│                                                             │
│  Olha o que encontrei no seu projeto:                       │
│                                                             │
│  ┌─────────────────────────────────────────────────────────┐│
│  │ É um monorepo com 3 áreas principais:                   ││
│  │                                                         ││
│  │ • Backend Python (FastAPI + SQLAlchemy + alembic)       ││
│  │   em src/dev_autonomo/                                  ││
│  │ • Frontend React (Vite + TanStack Query + shadcn/ui)    ││
│  │   em web/client/ e web/admin/                           ││
│  │ • Scripts e infra (Docker compose, migrations)          ││
│  │   em scripts/dev/ e alembic/                            ││
│  │                                                         ││
│  │ Vi também: testes em pytest, CI no GitHub Actions,      ││
│  │ Jira project LEO referenciado em vários commits.        ││
│  │                                                         ││
│  │ Indexei 8.234 trechos do seu código na RAG da squad.    ││
│  │ Os agentes vão consultar isso quando trabalharem.       ││
│  └─────────────────────────────────────────────────────────┘│
│                                                             │
│  ─── Pra esse projeto, sugiro estes agentes ─────────       │
│                                                             │
│  ┌─────────────────────────────────────────────────┐        │
│  │ 🧠  Business Analyst              ✓ catálogo    │        │
│  │     Refina demandas em ACs claras               │        │
│  │     [✎ editar prompt]  [✕ remover]              │        │
│  └─────────────────────────────────────────────────┘        │
│                                                             │
│  ┌─────────────────────────────────────────────────┐        │
│  │ 🏗  Architect                     ✓ catálogo    │        │
│  │     Decompõe demandas e delega aos Devs         │        │
│  │     [✎ editar prompt]  [✕ remover (essencial)]  │        │
│  └─────────────────────────────────────────────────┘        │
│                                                             │
│  ┌─────────────────────────────────────────────────┐        │
│  │ 🐍  Dev Backend Python/FastAPI    🔧 NOVO       │        │
│  │     Especialista no seu backend FastAPI.        │        │
│  │     Conhece SQLAlchemy 2.0, alembic e o         │        │
│  │     padrão de routers em src/.../routers/.      │        │
│  │     [✎ editar prompt]  [✕ remover (essencial)]  │        │
│  └─────────────────────────────────────────────────┘        │
│                                                             │
│  ┌─────────────────────────────────────────────────┐        │
│  │ ⚛  Dev Frontend React/Vite        🔧 NOVO       │        │
│  │     Especialista no painel React. Conhece       │        │
│  │     TanStack Query, shadcn/ui e o padrão de     │        │
│  │     pages/components do seu projeto.            │        │
│  │     [✎ editar prompt]  [✕ remover]              │        │
│  └─────────────────────────────────────────────────┘        │
│                                                             │
│  ┌─────────────────────────────────────────────────┐        │
│  │ 🔍  Reviewer                      ✓ catálogo    │        │
│  │     Revisa PRs antes do humano (opcional)       │        │
│  │     [✎ editar prompt]  [✕ remover]              │        │
│  └─────────────────────────────────────────────────┘        │
│                                                             │
│  [+ adicionar outro agente do catálogo]                     │
│                                                             │
│  ─── Como sua squad vai trabalhar ──────────                │
│                                                             │
│      📋 Issue no Jira                                       │
│           ↓                                                 │
│           🧠 BA refina em ACs claras                        │
│           ↓                                                 │
│           🏗 Architect planeja e delega                     │
│           ↓                                                 │
│           🐍 Dev FastAPI  ⚛ Dev React  (em paralelo)        │
│           ↓                                                 │
│           PR aberto                                         │
│           ↓                                                 │
│           🔍 Reviewer audita o PR                           │
│           ↓                                                 │
│           👤 Você aprova ou ajusta                          │
│                                                             │
│  ─── Conectar seu Jira ─────────                            │
│                                                             │
│  Vi referências aos projetos LEO e ADMIN nos seus commits   │
│  e PR templates. Se você conectar seu Jira, os agentes vão  │
│  receber demandas direto dali sempre que uma issue desses   │
│  projetos for criada — sem você precisar abrir nada aqui.   │
│                                                             │
│  URL do workspace: [https://_____.atlassian.net]            │
│  API token:        [_____________________________]          │
│  ▶ Como gerar um API token (1 min)                          │
│                                                             │
│  Projetos cobertos:                                         │
│  ☑ LEO        ☑ ADMIN                                       │
│  + adicionar outro projeto                                  │
│                                                             │
│  [ Conectar Jira ]   [ Pular — conecto depois ]             │
│                                                             │
│  ─── Nome da squad (vai aparecer no painel) ───             │
│                                                             │
│  [ Plataforma dev-autonomo                       ]          │
│                                                             │
│  [ Ativar minha squad → ]                                   │
└─────────────────────────────────────────────────────────────┘
```

**Decisões:**

- **Relatório em prosa**, não em JSON/cards. Cliente lê como um analista descrevendo. Sinaliza que o sistema **entendeu** o projeto.
- **Distinção visual `🔧 NOVO` vs `✓ catálogo`** — preserva o que o Bloco E já implementou. NOVO = skill paramétrico gerado pelo OA refletindo o projeto. CATÁLOGO = skill template global de prateleira.
- **Cada agente editável/removível inline** — sem segunda tela. `[✎ editar prompt]` abre modal inline pra ajustar prompt + modelo.
- **Regras de remoção:**
  - **Architect + Dev (≥1): obrigatórios**. Clicar `✕` mostra toast: *"Esse agente é essencial pra pipeline. Você pode editar o prompt, mas não remover."*. Texto do botão indica isso visualmente: `[✕ remover (essencial)]`.
  - **BA + Reviewer: removíveis com modal de aviso** explicando o trade-off. Exemplo BA: *"Sem o BA, demandas do Jira vão direto pro Architect sem refinement prévio. Você precisará refinar manualmente cada issue antes de mandar pros agentes, ou o Architect vai planejar com a descrição original (geralmente menos preciso). Tem certeza?"*. Botões "Remover assim mesmo" / "Voltar".
- **Diagrama do fluxo** logo abaixo dos agentes — visualiza a pipeline. Quando o cliente remove BA, o diagrama atualiza dinamicamente (caixa BA some, flecha pula direto). Educação por design.
- **Botão `+ adicionar outro agente do catálogo`** abre modal "Adicionar agente":
  - Papel: BA adicional / Architect adicional / Dev (especialista em stack) / Reviewer
  - **Pra Dev**: stack(s) é **obrigatório** (multi-select das stacks detectadas). Dev sempre é especialista em algo.
  - **Pra BA/Architect/Reviewer**: stack(s) é **opcional** (default = todas). Marcar stack específica = especialização (ex: "Reviewer de segurança").
  - Opção `+ Criar stack nova` pra área que ainda não existe no código (ex: cliente vai começar app mobile preventivamente). Declara nome + path destino + framework esperado. Cria `stack_profile` vinculado à squad, com RAG vazia até ter código.
  - Modelo Claude dropdown.
- **Seção Jira** dentro da tela 3, não em tela separada. Descoberto pela análise (referências em commits/PR templates), projetos pré-marcados. Pode pular. Bloco expansível "Como gerar API token" mesmo padrão do GitHub token.
- **Nome da squad sugerido pelo OA**, editável. Não tem mais campo "slug", "domain", "description" — tudo derivado.
- **Botão final em verbo de ação**: "Ativar minha squad" — não "Concluir setup". Cliente entende que algo acontece (provisiona agents na Anthropic, ativa webhook GitHub, etc.).

### Tela 4 — Squad ativa

```
┌─────────────────────────────────────────────────────────────┐
│  ✓  Squad "Plataforma dev-autonomo" ativa                   │
│                                                             │
│  Provisionei 5 agentes na Anthropic e conectei seu repo     │
│  ao webhook do GitHub. Quando você criar uma issue no Jira  │
│  e marcar `@agents`, sua squad começa a trabalhar.          │
│                                                             │
│  ─── Próximos passos ───                                    │
│                                                             │
│  ┌──────────────────────────────────────────────┐           │
│  │  📋 Crie sua primeira demanda                │           │
│  │  Pode ser no Jira (com @agents na descrição) │           │
│  │  ou direto aqui no painel — eu te mostro     │           │
│  │  como em 30 segundos.                        │           │
│  │  [ Criar primeira demanda → ]                │           │
│  └──────────────────────────────────────────────┘           │
│                                                             │
│  ┌──────────────────────────────────────────────┐           │
│  │  🤖 Ver sua squad em ação                    │           │
│  │  Veja os 5 agentes, seus prompts, custos     │           │
│  │  acumulados, histórico de runs.              │           │
│  │  [ Abrir painel da squad → ]                 │           │
│  └──────────────────────────────────────────────┘           │
│                                                             │
│  ┌──────────────────────────────────────────────┐           │
│  │  👥 Convidar mais pessoas do time            │           │
│  │  Pode adicionar reviewers que aprovam PRs    │           │
│  │  ou viewers que só acompanham.               │           │
│  │  [ Gerenciar membros → ]                     │           │
│  └──────────────────────────────────────────────┘           │
└─────────────────────────────────────────────────────────────┘
```

**Decisões:**
- **Confirmação concreta no topo, em prosa**. Diz o que foi feito (5 agentes + webhook) e como começar a usar (Jira + `@agents`). Não "Setup completed!" genérico.
- **3 caminhos concretos** como next steps. Primeiro card é o principal (criar demanda); os outros 2 (ver squad, convidar time) são opções secundárias.
- Sem confetti, sem links pra docs externas, sem "tudo pronto, parabéns!" genérico.
- **Caso de erro parcial**: se Anthropic provisionar 3 de 5 agentes (rate limit, etc), tela mostra `⚠ Squad parcialmente ativa — 3 de 5 agentes provisionados` em vez de ✓, com botão `[ Tentar provisionar os outros 2 ]`. Cliente sempre retoma do ponto que parou — sem refazer setup.

---

## Decisões transversais

### Stacks como entidades persistentes

Cada stack detectada pela análise vira registro no banco com:
- `slug` (ex: `python-fastapi`)
- `nome` (ex: "Backend Python/FastAPI")
- `path(s)` no repo (ex: `src/dev_autonomo/`)
- `framework` + versão detectada
- `convenções` (regras observadas: ordem de imports, estilo de testes, etc.)
- Link com `stack_profile` global (template base) se houver match

Stacks ficam editáveis na **tela da squad** (a desenhar). Podem ser criadas manualmente quando o cliente quer abrir uma área nova ainda sem código.

### RAG da squad com filtros por stack

Coleção `playbook:{squad_id}` agrega chunks de **todos os repos da squad**, mas cada chunk tem `metadata.stack` pra retrieval filtrar quando o agente trabalha numa stack específica.

### Roteamento de PR por stack

Webhook GitHub `push`/`pull_request` em main → sistema identifica que stack(s) o PR toca (via path) → dispara o(s) Dev da(s) stack correspondente(s). Multi-stack = paralelismo natural.

### Reindex automático

Webhook GitHub push em main → consome `ReindexMessage` (já existe na fila desde antes; o consumer precisa ser confirmado/implementado completo) → atualiza chunks afetados na RAG da squad sem refazer indexação inteira.

### Cross-squad opt-in bilateral

Cada squad declara quais outras squads do mesmo tenant podem **delegar demandas pra ela** e pra quais ela pode **delegar**. Tabela `CrossSquadRequest` já existe no modelo. Não aparece no setup inicial — só quando o tenant tem 2+ squads.

### Jira por squad, descoberto pela análise

Cada squad cobre N projetos Jira. Lista de projetos é descoberta pela análise (referências em commits e PR templates). Cliente pode marcar/desmarcar e adicionar projetos não detectados. Conexão é opcional no setup.

### Tom em primeira pessoa

Em todas as telas, mensagens do produto são em primeira pessoa ("Estou clonando", "Olha o que encontrei", "Provisionei 5 agentes"). Voz consistente do produto inteiro, não só do wizard.

### Credenciais just-in-time

GitHub token, Jira token — todos são pedidos **no contexto** onde fazem sentido (ao colar repo privado, ao conectar Jira), não como passo "Credenciais" upfront. Cliente que não precisa de uma credencial específica não vê o input dela.

---

## Próximas rodadas de design (PENDENTE — não implementar sem desenhar antes)

Estas peças **ainda não foram conversadas** ou foram só esboçadas. **Não tentar implementar sem antes retomar a conversa de design** — risco alto de criar UX inconsistente com o cenário A.

### Cenário B — Greenfield (cliente sem código)

Cliente que está começando do zero. Não tem repo pra analisar. Caminho conceitual rascunhado:

1. Cliente clica "Estou começando do zero" na tela 0
2. Sistema abre **diálogo guiado** (não wizard de campos): pergunta o que quer construir, pra qual público, alguma decisão de stack já tomada
3. Cliente descreve em **texto livre**
4. Sistema sugere stack baseado na descrição (ex: "SaaS de gestão" → Python/FastAPI + React + Postgres)
5. Cliente confirma stacks
6. Sistema oferece upload opcional de materiais (mockups, PRD, exemplos de API) pra alimentar RAG inicial
7. Sistema **cria scaffold inicial num repo novo** (opcional — pode pular se cliente quer começar nu)
8. Agentes nascem com contexto declarado, sem RAG de código, com RAG dos materiais subidos

A RAG é populada por **declaração + uploads**, não por código existente.

### Cenário C — Explorando (não decidiu ainda)

Tour/demo curto do produto sem precisar configurar nada. Esboço: cliente vê um exemplo de squad fictícia em ação, lê o que cada agente faria, e tem CTA pra "começar de verdade" voltando à tela 0.

### Modais do cenário A (esboçados na tela 3, faltam detalhes)

- **Modal de edição de prompt** (clique em `[✎ editar]` num agente): editor de system prompt + dropdown de modelo + preview de variáveis paramétricas (se for skill paramétrico, mostrar quais variáveis serão renderizadas).
- **Modal de remoção com aviso** (BA/Reviewer): texto exato do aviso + diagrama atualizado da pipeline (com a peça removida) + botões "Remover assim mesmo" / "Voltar".
- **Modal "Adicionar agente"**: refinar fluxo de seleção de papel + escolha de stack(s) + "+ criar stack nova" + modelo. Esboço inicial na seção da tela 3 do cenário A.

### Painel da squad (página onde cliente cai depois do setup)

Estrutura proposta:
- Seção "Stacks" (lista, editar, criar nova manualmente)
- Seção "Repositórios" (status indexado/desatualizado, último reindex, +adicionar repo)
- Seção "Agentes" (lista, custo acumulado por mês, histórico de runs)
- Seção "Cross-squad" (só aparece se tenant tem 2+ squads; configura opt-in bilateral)
- Seção "Jira" (workspace, projetos cobertos, status da conexão)

### Fluxos pós-setup

- **Adicionar outro repositório à squad** em modo delta: análise vê stacks novas que o repo trouxe, propõe Dev extra se for stack ainda não coberta, indexa RAG incremental.
- **Tela "Criar primeira demanda"** (CTA principal da tela 4): pra cliente que ainda não conectou Jira ou prefere abrir demanda direto pelo painel.
- **Remover/desativar squad** — não desenhado.
- **Auditoria de RAG** — cliente ver/limpar chunks indexados, importante pra compliance.

### Disciplina recomendada

**Antes de implementar qualquer item acima, retomar sessão de design** com o mesmo formato dessa: prosa, 1 pergunta por turno, ASCII mocks, decisões deliberadas explicadas. Documentar resultado num novo doc (ou anexar a este) com data.

**O que NÃO fazer:** implementar B/C ou modais "de cabeça" só porque o cenário A já foi feito. Vai criar inconsistência de UX e produzir débito imediato.

---

## Estado da implementação atual (a ser refeita)

Os PRs A-H do roadmap stack-knowledge (mergeados em 2026-05-14) implementam uma **versão preliminar** do wizard que precisa ser refeita conforme este desenho. O que foi feito é base útil — schema, backend de RAG ingest, skill paramétrico, hook Dreaming — mas a UX do front cliente vai ser reescrita.

**PRs relevantes:**
- #79 — schema `stack_profiles` + `rag_sources` + skill paramétrico (Bloco A)
- #80 — seed de 15 stack profiles (Bloco B)
- #81 — RAG ingest backend + telas admin/cliente (Bloco C)
- #82 — `propose_skill_from_stack` (Bloco D)
- #83 — wizard cliente v1 (Bloco E) — **a ser substituído por este redesenho**
- #84 — feedback loop GitHub → padrões anonimizados (Bloco F)
- #85 — rerank de retrieval (Bloco G)
- #86 — hook Dreaming pós-task (Bloco H)
- #87 — normalize GitHub URL (sufixo `.git`)
- #88 — wizard exige ≥1 repo no Manifesto — **será removido**, manifest é derivado
- #89 — normalize enums `api_call_kind`/`api_provider` pra lowercase

**Implementação do cenário A — CONCLUÍDA em 2026-05-15.**

8 PRs sequenciais mergeados na main:

| PR | Sha | Entrega |
|---|---|---|
| 1 | `268d55c` | Endpoint `GET /client/github/repo-status` |
| 2 | `71169c4` | Entidade `Stack` persistente + CRUD |
| 3 | `f84bce8` | **Cérebro novo do OA** — 6 etapas + RAG ingest + grader Haiku |
| 4 | `b98b31c` | Tela 0 — porta de entrada (3 cards) |
| 5 | `0080d4d` | Tela 1 — cola URL + token JIT + debounce |
| 6 | `9194be0` | Tela 2 — análise viva com state granular |
| 7 | `96d7db8` | Tela 3 — relatório + agentes + diagrama + Jira inline + Tela 4 base |
| 8 | (este PR) | Switch final: `/setup` → tela 0, remove wizard antigo, Tela 4 polida |

### Itens NÃO incluídos nos 8 PRs (TODO pós-implementação)

Documentados explicitamente pra não sumirem:

- **Modal "Editar prompt"** do agente (botão visível mas disabled na Tela 3 com tooltip)
- **Modal "Adicionar agente do catálogo"** (não habilitado na Tela 3)
- **Configuração detalhada de stack pra Dev paramétrico** — `catalog_skill_slug` deriva por slug literal; integração completa com Bloco D fica pra PR futuro
- **Caso de erro parcial na Tela 4** — botão "tentar provisionar agents faltantes" sem refazer setup
- **Cenário B (greenfield)** — caminho completo (continua placeholder em `/setup/greenfield`)
- **Cenário C (explorando)** — tour/demo (continua placeholder em `/setup/explore`)
- **Painel da squad** com seções stacks/repos/agentes/cross-squad
- **Fluxo "adicionar outro repositório"** pós-setup em modo delta
- **Sweeper job de clones órfãos** > 24h (operacional)
- **AST chunking** — hoje usa sliding window (universal). AST melhora qualidade pra Python/TS/JS quando volume justificar.
- **Smokes pra pytest async** — hoje são scripts standalone em `tests/onboarding/`

---

## Critérios de pronto (aplicáveis a TODO PR do redesign)

**Disciplina central:** este redesign está sendo conduzido com a regra explícita de **não criar débito técnico**. Antes de marcar um PR como completo, eu (Claude) preciso produzir **evidência** de que cada critério abaixo foi cumprido — não basta dizer "acho que tá bom". O cliente (Rubens) usa essa lista como rubric pra cobrar — em qualquer ponto que falte evidência, devolve.

### Critérios gerais (todos os PRs do redesign)

- ☐ **Doc atualizada** — se o PR mudou padrão, comportamento descrito ou decisão estrutural, este `redesign-onboarding-2026-05-14.md` foi atualizado refletindo o estado real
- ☐ **Smoke test escrito e passando** — não confiar só em "compila" ou "import OK". Caso(s) concreto(s) exercitando a peça nova com asserts
- ☐ **Sem hardcode** de path/URL/timeout/credencial fora de `settings` ou parâmetros injetados
- ☐ **Tratamento explícito de erro** em pontos de I/O (rede, DB, filesystem). Captura exceção específica, NUNCA `except Exception` silencioso
- ☐ **Migrations alembic** com `upgrade()` E `downgrade()` funcionais. Downgrade testado se possível
- ☐ **Enums novos** seguem padrão lowercase + `values_callable=lambda e: [m.value for m in e]` + `PG_ENUM` em migration com `create_type=False`
- ☐ **Body do PR** lista decisões tomadas com **porquê** — não só "o que mudou"
- ☐ **Pendências documentadas** — se algo foi adiado, está no `TODO` da memória ou doc com data e motivo. Não some
- ☐ **Endpoint novo** tem schema Pydantic + `response_model` definido
- ☐ **Model novo** tem `TimestampMixin` e índices em FKs
- ☐ **Body de erro estruturado** — 400/409/422 com `detail` em prosa útil. Não retorna 500 cru
- ☐ **Hooks pre-commit não foram pulados** (`--no-verify` proibido)
- ☐ **Memória atualizada** se decisão estrutural foi tomada que deve sobreviver compactação
- ☐ **Sem palavras-gatilho de minimização** no body do PR ou comentários — frases como "*por simplicidade*", "*numa primeira versão*", "*pra ganhar tempo*", "*trivial*", "*basta*" requerem justificativa explícita do que está sendo cortado

### Critérios específicos do PR-3 (onboarding_analyzer v2)

- ☐ **State machine persistida** — cliente pode fechar aba durante análise e retomar de onde parou; estado granular em `tasks` (etapa atual, label, contadores)
- ☐ **JSON output do OA validado por Pydantic** — schema rígido; erro de validação dispara retry do OA com mensagem corretiva, **não** parsing heurístico
- ☐ **RAG ingest contabiliza `ExternalApiCall`** kind=`embedding` provider=`voyage` — custo visível na cost page
- ☐ **Chamada OA contabiliza `ExternalApiCall`** kind=`chat` provider=`anthropic` — custo visível na cost page
- ☐ **Outcome rubric definido com 5+ checks** — `scan_breadth`, `conventions_depth`, `anti_patterns_evidence`, `tests_examined`, `git_history_checked`. Grader é Claude Haiku (25× mais barato)
- ☐ **Stacks DETECTED** persistidas no DB consumindo PR-2; unique constraint `(squad_id, slug)` respeitada
- ☐ **Anti-patterns têm `path:line` concreto** — não generalização ("muitas exceções genéricas") sem evidência
- ☐ **Endpoint progress retorna estado granular** — `current_step`, `step_label`, `chunks_indexed`, `chunks_total`, `last_log_message`
- ☐ **Cancel da análise funciona** — frontend pode pedir cancel; backend libera recursos (Anthropic session.delete, qdrant nada a fazer ainda, task marcada CANCELLED)
- ☐ **Erro em qualquer etapa** marca task com motivo claro + retoma do ponto possível, não força refazer do zero
- ☐ **Schema de chunk_kind** preenchido corretamente (code/test/docs/config) por classificação determinística (path/extensão), antes da ingestão
- ☐ **`CLONE_BASE_DIR` é setting** (não hardcode); default `~/.local/share/dev-autonomo/clones`
- ☐ **Clones isolados** por `{CLONE_BASE_DIR}/{client_id}/{task_id}/` — tenant isolation por filesystem
- ☐ **Cleanup em `finally` block** executa em sucesso E em falha; não deixa /clones órfão por erro previsível
- ☐ **Sweeper de órfãos** documentado no TODO da memória pós-implementação (não bloqueia cenário A, mas não pode sumir do roadmap)

### Como esses critérios são cobrados

1. **Antes de cada PR começar**: Claude lista os critérios aplicáveis (gerais + específicos) e confirma com Rubens.
2. **Durante a implementação**: se Claude propor algo que ofende critério, Rubens interrompe e redireciona — não espera pra cobrar no fim.
3. **Antes de marcar PR como completo**: Claude produz **auto-grading** no body do PR, listando como verificou cada critério (com paths, comandos rodados, asserts dos smokes). Body sem auto-grading = PR rejeitado.
4. **Pós-merge**: critérios viram parte do checklist persistente — não decaem em sessões futuras.

Esta seção sobrevive compactação porque está no doc do repo. A memória `project_redesign_onboarding.md` aponta pra ela.

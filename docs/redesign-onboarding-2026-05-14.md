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

### Cenário B — Greenfield (cliente sem código) — DESENHADO em 2026-05-15

Cliente que está começando do zero. Não tem repo pra analisar. Reusa máximo de UI do cenário A, com 4 telas próprias e reaproveitando Tela 0 + Tela 4.

#### Tela B1 — "Conta sobre seu projeto" (texto livre puro)

- Cliente cai aqui após clicar "Estou começando do zero" na Tela 0.
- Único campo: textarea ~10 linhas, expansível.
- Placeholder com **exemplo realista** (SaaS de gestão pra psicólogos com mix de "tenho preferência de stack" + "não tenho certeza"). Ancora o nível de detalhe esperado.
- Dicas em prosa abaixo do textarea (não como campos obrigatórios): o que construir / pra quem / stack decidida ou não / restrições e referências.
- Validação: mín ~50 chars (evita "teste", "oi") — botão "Próximo" só habilita quando passa. Máx ~5000 chars com warning suave quando se aproxima.
- "Voltar" leva pra Tela 0.

#### Tela B2 — "Tem algum material de referência?" (upload opcional)

- Drag-and-drop área grande + fallback clique pra selecionar.
- Aceita PDF, Markdown, .txt, .docx (até 10 MB cada). Tipos visíveis no dropzone.
- Botão "+ Adicionar URL/link" — primeira classe, não escondido. Cliente pode adicionar artigos, repos open-source de referência, docs externos. Sistema baixa via `trafilatura` (já existe em `rag_ingest.py`) e indexa.
- Lista de adicionados com tamanho + botão remover. Sem reorder.
- **Aviso de PII em destaque:** *"Não subir dados de produção (CPFs, prontuários, etc) — o conteúdo vai pra base de busca da sua squad e fica visível pros agentes."*. Compliance, não estético.
- Botão "Pular" coexiste com "Próximo" — sempre opcional.

#### Análise B viva (3 etapas, equivalente da Tela 2 do A)

Versão enxuta da análise do A. Duração esperada: 30–90s (vs 10–20 min do A — não tem código pra escanear).

Etapas:
1. **Indexando materiais que você subiu** (skip se cliente pulou B2). Voyage embed + Qdrant upsert na coleção `playbook:{squad_id}`. Mostra contagem `X arquivos · Y chunks`.
2. **Pensando na stack ideal pro que você descreveu**. Claude (Opus) lê descrição B1 + sample dos materiais B2 → propõe stack + agentes em JSON estruturado (mesmo schema `OnboardingAnalysisOutput` do A, com ajustes: stacks são PROPOSTAS, sem anti-patterns).
3. **Definindo agentes**. Parte da mesma chamada Claude, separado visualmente pra clareza de progresso.

Reusa toda a UI da Tela 2 do A — só com 3 etapas em vez de 6. Mensagens em primeira pessoa, sem ETA, com cancel.

#### Tela B3 — "Olha o que eu propus pro seu projeto"

Reaproveita estrutura da Tela 3 do A. Diferenças deliberadas:

- **Header em prosa**: *"Olha o que eu propus pro seu projeto"* (proposição) em vez de *"Olha o que encontrei"* (descobrimento).
- **Summary** explica em primeira pessoa o que entendeu da descrição + materiais, e justifica a stack proposta.
- **Stacks com badge `PROPOSTA`** (em vez de `DETECTADA` do A). Cliente pode trocar mais livremente — não há evidência de código travando.
- **Sem seção "Pontos de atenção"** — não tem código pra ter anti-pattern.
- **Nova seção "Quer que eu crie um scaffold inicial?"** (opt-in, padrão DESLIGADO):
  - Cliente pode escolher receber repo vazio no GitHub dele com estrutura base da stack (Dockerfile, FastAPI/Vite/etc skeleton, alembic init, gitignore, README).
  - Pra ligar, precisa de GitHub token (just-in-time, mesma UX do A).
  - Padrão "Vou criar o repo eu mesmo depois" pra não ser invasivo.
  - Sai daqui com algo concreto pra começar, em vez de squad órfã.
- **Seção Jira inline**, nome da squad editável, botão "Ativar minha squad" — todos iguais ao A.

Após Ativar → mesma Tela 4 do A (squad ativa + 3 cards de next steps).

#### Diferenças arquiteturais cenário A vs B

| | Cenário A | Cenário B |
|---|---|---|
| RAG inicial | chunks do código clonado | chunks dos materiais subidos (opcional) |
| Stacks | detectadas via scan determinístico + Claude | propostas via Claude lendo descrição + materiais |
| Duração análise | 10–20 min | 30–90 s |
| Anti-patterns | sim, com `path:line` | não (sem código) |
| Scaffold | repo já existe | opt-in cria repo + estrutura base |
| Reuso de UI | — | Telas 0 e 4 idênticas; B1/B2/B-viva/B3 derivadas das do A |

### Cenário C — Explorando (não decidiu ainda)

Tour/demo curto do produto sem precisar configurar nada. Esboço: cliente vê um exemplo de squad fictícia em ação, lê o que cada agente faria, e tem CTA pra "começar de verdade" voltando à tela 0.

### Dashboard principal (D-02 — DESENHADO em 2026-05-15)

Tela que o cliente vê **toda vez que loga** depois do setup. Responde 3 perguntas em ordem:
1. *"Tem algo que precisa de mim agora?"*
2. *"O que meus agentes estão fazendo neste momento?"*
3. *"Estamos saudáveis?"*

**Seções (de cima pra baixo):**

1. **Header** — nome do cliente + squad ativa (com dropdown quando tenant tem 2+).

2. **⚠ Precisa da sua atenção (count)** — banner com cards que requerem ação:
   - 🟡 PR aguardando revisão (Reviewer aprovou, falta humano)
   - 🔴 Task falhou (grader rejeitou, infra explodiu, etc.)
   - 🟠 Alerta de custo (passou do threshold do plano)
   - 🟠 BA pediu clarificação na demanda
   - Cada card tem CTA direto pro local de ação.
   - **Quando vazio, a seção inteira some** — comunica saúde por ausência, não por mensagem repetitiva "tudo em ordem ✓".

3. **Em curso (count)** — linhas curtas (não cards), uma por task em execução agora:
   - `🔄 LEO-789 · BA refinando demanda · há 12min · $0.04`
   - Apenas observação. Sem ação requerida. Click vai pro detalhe (D-05).
   - Link "Ver todas as tasks →" pra lista completa (D-04).

4. **Visão geral do mês** — 3 KPIs:
   - **Custo do mês** (com comparativo ↑/↓ % vs anterior + link "Detalhar →" pra D-06)
   - **Concluídas** (count de demandas mergeadas no mês + comparativo)
   - **Saúde da squad** (número de agentes + status agregado + link "Painel →" pra D-03)
   - Sem charts wall. Detalhe profundo vive em `/cost` (D-06).

5. **Atividade recente** — feed cronológico de eventos (últimos 10), tipo "BA começou refinement", "Dev abriu PR #X", "LEO-450 mergeada · custo $1.23". Link "Ver tudo →".

6. **Ações rápidas** no rodapé — `[+ Criar demanda]` `[+ Nova squad]` `[Conectar Jira]`. Não no topo: atenção e em curso são mais importantes que iniciar coisas novas pra quem volta diariamente.

**Estados especiais:**

- **Cliente nunca criou demanda ainda** — "Em curso" e "Atividade" mostram CTA grande motivacional ("Sua squad está pronta — crie a primeira demanda") em vez de dashboard mocado.
- **Multi-squad (futuro)** — header com dropdown de squad; KPIs e "Em curso" filtram pela selecionada; toggle "Ver todas as squads" agrega.

### Detalhe de uma task (D-05 — DESENHADO em 2026-05-15)

A tela mais densa do produto. Cliente cai aqui quando clica "Ver detalhes" no Dashboard (cards "Precisa atenção" ou "Em curso") ou na lista de tasks. Precisa funcionar em 4 estados: em curso, PR aguardando humano, concluída, falhou.

**Princípio de integração com Jira:** Jira = fonte da verdade da DEMANDA. Painel = fonte da verdade da EXECUÇÃO. Os dois espelham — cliente lê/age nos dois sem trocar de contexto. Detalhes completos em D-16.

**Seções (de cima pra baixo):**

1. **Header** — `LEO-456 · "Implementar endpoint /users com autenticação"` + squad + status + tempo desde abertura/última atualização + 2 links externos `[Jira ↗]` `[PR ↗]`.

2. **Bloco "Demanda original (do Jira)"** — read-only no painel:
   - Título, autor, criada em, prioridade, sprint
   - Descrição da issue formatada (texto livre do Jira)
   - Botão `[Editar no Jira ↗]` pra modificar (Jira é fonte canônica — não editar no painel)

3. **Pipeline (timeline vertical)** — cada etapa tem:
   - Ícone de estado (`✓` done, `⠿` ativo, `○` pending, `✗` failed)
   - Nome em primeira pessoa ("BA refinou em ACs", "Architect planejou", "Dev FastAPI implementou", "PR aberto", "Reviewer auditou")
   - Timestamp + duração + custo
   - Expansível por default colapsado: BA expande pros ACs (lista numerada), Architect expande pro plan (markdown), Dev expande pro log de tool calls (summary curto por call), Reviewer expande pros issues + verdict.
   - **Comentários humanos do Jira aparecem inline na timeline** como mini-cards `💬 Maria comentou no Jira (14:08): "Atenção: precisa retornar 422 também"` — entre as etapas dos agentes, cronologicamente.

4. **Decisão humana INLINE** na etapa ativa quando aplicável — `[✓ Aprovar e mergear] [✗ Rejeitar com comentário]`. Não no rodapé — onde a decisão acontece.

5. **Custo total** + duração total no rodapé da pipeline.

6. **Caixa "Adicionar instrução"** sincroniza com Jira:
   - Quando preenchida, vira comentário no Jira automaticamente com prefix `[from dev-autonomo]`
   - Checkbox opcional "Só notifico aqui (não postar no Jira)" pra casos onde cliente não quer barulhar a issue
   - **Sempre visível** — comportamento varia por estado:
     - **Em curso**: instrução adicional pro agente ativo (próxima iteração consome)
     - **PR aguardando humano**: reabrir PR com refinement pro Dev
     - **Falhou**: diagnóstico do humano que vai pro grader interpretar
     - **Concluída e mergeada**: vira "criar follow-up" (nova task referenciada à anterior)

7. **Ações destrutivas no rodapé** com badge ⚠: `[✕ Cancelar task]` `[⏸ Pausar]` `[↻ Reabrir PR pra refinement]`. Separadas visualmente do caminho de click acidental.

**Estados especiais:**
- **Falhou** → etapa com `✗ vermelho` + log expandido por default + botão "Tentar novamente" inline.
- **Pausada** → overlay leve "Task pausada — retomar?" no topo.
- **Cancelada** → etapas posteriores cinzas + botão "Reabrir" disponível no rodapé.
- **Multi-Dev (multi-stack)** → "Dev" vira "Devs em paralelo" com sub-cards (1 por Dev), cada um com log/custo/duração separados.

### Painel da squad (D-03 — DESENHADO em 2026-05-15)

Página `/squads/:squadId` — drill-down de UMA squad específica. Cliente entra aqui pelo dashboard ("Painel →" no KPI), pelo nome da squad em outros lugares, ou direto via URL.

**Header:** nome + descrição + status (🟢 ativa / ⚠ provisioning / ⏸ pausada / 📦 arquivada) + métrica curta de "4 agentes · 1 repo · 5 stacks · criada há 3 dias".

**Tabs:** Visão geral · Agentes · Stacks · Repos · Jira · Config. Default = "Visão geral". URL com hash pra deep-link.

**Tab "Visão geral" — dashboard escopado à squad** (cliente vê tudo sem precisar trocar de tab):

- **⚠ Precisa atenção (count, some quando vazio)** — mesma lógica do Dashboard global, filtrada à squad
- **🔄 Em curso (count)** — linhas curtas de tasks rodando agora, com link "Ver todas →" pra lista tenant-wide
- **Agentes (count)** — cards leves com tier, nome, modelo, última run, custo do mês. CTAs inline `[+ Adicionar agente]` `[Gerenciar agentes →]`
- **KPIs do mês** — Custo · Concluídas · RAG chunks. Sem charts (vivem em D-06)
- **Stacks (count)** — lista compacta com slug + paths + framework version. `[+ Criar stack manual]` `[Gerenciar stacks →]`
- **Repositórios (count)** — lista com status de indexação visual (✓ fresh / ⚠ desatualizado / ✗ erro) + última reindex + count chunks + botão "Reindexar agora" inline. `[+ Adicionar repositório]`
- **Jira** — workspace + projetos cobertos + link configurar

**Tabs separadas (Agentes/Stacks/Repos/Jira)** — CRUD detalhado. Drill quando cliente quer fazer ação específica:
- Aba Agentes: histórico de runs, prompt atual, custo breakdown, edit/remove/add
- Aba Stacks: editar conventions, criar manual, arquivar
- Aba Repos: drill em arquivos indexados, reindex policy, adicionar/remover repo
- Aba Jira: workspace, projetos cobertos, mapeamento de status

**Tab "Config"** — nome/descrição/domain editáveis + zona perigosa (`Pausar squad` / `Arquivar squad`) — NÃO na visão geral pra evitar click acidental.

**Cross-squad** — tab adicional **só aparece quando tenant tem 2+ squads**. Esconder reduz cognitive load no caso comum (cliente com 1 squad).

**Estado especial:** squad ativada mas sem demanda nenhuma ainda → "Em curso" e "Precisa atenção" somem; KPIs zerados; CTA grande "Sua squad está pronta — crie a primeira demanda".

**CTAs inline disparam fluxos dedicados:**
- `+ Adicionar agente` → modal D-08
- `+ Adicionar repositório` → fluxo D-09 modo delta
- `+ Criar stack manual` → modal simples (parte da implementação de D-03)

### Lista de tasks (D-04 — DESENHADO em 2026-05-15)

Página `/tasks` — visão tenant-wide com filtros densos pra investigar padrões e achar tasks específicas do passado.

**Layout:** header com busca rápida + barra de filtros (squad, agente, status, tipo, período, custo) + tabela paginada.

**Tabela:** colunas — Jira key + título, squad, agente atual/último, status, started_at, duração, custo. Ordenação clicando coluna. Click numa linha → D-05 (detalhe). Sticky header.

**Filtros:** chips removíveis no topo. Combo de squad (multi-select), agente (multi-select), status (in_progress/completed/failed/cancelled), tipo (onboarding/feature/bug — derivado do label/prefixo), período (hoje/7d/30d/custom), faixa de custo (slider). URL com query params pra deep-link.

**Estado vazio:** sem nenhuma task no tenant → CTA "Sua squad está pronta — crie a primeira demanda". Com filtro mas sem match → "Nada bate seus filtros · [limpar filtros]".

**Bulk actions** (opcional, dependendo do volume): selecionar linhas pra exportar CSV / cancelar em massa. Fica fora do MVP.

### Painel de custos (D-06 — DESENHADO em 2026-05-15)

Página `/cost` — drill-down completo dos custos do tenant.

**Cards no topo (4):**
- Total do mês atual (com comparativo % vs mês anterior)
- Top squad cara (qual + custo)
- Top agente caro (qual + custo)
- Modelo Claude mais usado (Opus/Sonnet/Haiku + % do total)

**Gráfico** série temporal — custo diário do mês corrente em barras. Overlay tracejado do mês anterior pra comparação. Sem grandes ambições — Chart.js ou Recharts simples.

**Tabela top 20 tasks mais caras** do período — colunas: Jira key, squad, agente, custo, duração, status. Click → D-05.

**Filtros:** período (mês atual / mês anterior / últimos 90d / custom), squad, agente, modelo Claude, tipo de ApiCall (chat/embedding/skill_proposal).

**Alertas de plano:** quando custo do mês passa 80% do limite do plano → banner ⚠ no topo com link pra mudar plano. Quando passa 100% → bloqueio com explicação.

### Criar 2ª/3ª squad (D-07 — DESENHADO em 2026-05-15)

Cliente já tem squad rodando, quer criar mais. Reusa **Tela 0** com adaptação:

- Header muda pra "Suas squads (count): · [lista compacta] · Quer criar mais uma?"
- 3 cards idênticos (Tenho repositório / Começar do zero / Explorando)
- Não pede credenciais — **reusa GitHub/Jira tokens já cadastrados** automaticamente. Cliente só precisa colar URL (cenário A) ou descrever (cenário B).
- Tela 3 ganha seção "Cross-squad" inline (porque agora tem 2+ squads no tenant) — checkboxes pra autorizar delegação bilateral com squads existentes. Pode pular.

**Backend:** mesmos endpoints. Adição: `POST /client/squads/{new_id}/cross-squad/authorize` pra autorizações.

### Adicionar agente em squad existente (D-08 — DESENHADO em 2026-05-15)

Modal acessível pela Tela 3 (cenário A/B durante setup) E pelo painel da squad (D-03 aba Agentes ou CTA inline). 4 passos curtos:

1. **Qual papel?** Cards: BA / Architect / Dev / Reviewer com descrição curta.
2. **Em qual(is) stack(s)?** Pra Dev = obrigatório multi-select das stacks detectadas. Pros outros = opcional (default cobre tudo; marcar especializa). Botão `+ Criar stack nova` pra área futura.
3. **Prompt:** preset do catálogo (se BA/Architect/Reviewer) OU paramétrico via `propose_skill_from_stack` (se Dev). Textarea editável com aviso "Você pode customizar depois".
4. **Modelo Claude:** dropdown (sonnet-4-6 default, opus-4-7, haiku-4-5). Estimativa de custo/hora exibida.

Botão final `[ Adicionar agente ]` → cria SkillTemplate + provisiona Anthropic agent + cria AgentInstance.

### Adicionar repositório em squad (modo delta) (D-09 — DESENHADO em 2026-05-15)

Botão `+ Adicionar repositório` no painel da squad (D-03 aba Repos). Fluxo derivado da Tela 1 do cenário A:

1. **Cola URL** com detecção debounce (reusa endpoint `repo-status` PR-1)
2. **Token JIT** se privado (reusa credencial existente da squad se já tem; senão pede)
3. **Análise delta** — variação curta da Tela 2: clone + scan + indexar **chunks novos** em `playbook:{squad_id}` (sem reindexar repos já indexados) + detectar stacks **novas** (que repo trouxe além das existentes)
4. **Tela "Resultado delta"** — mostra: chunks novos indexados, stacks novas detectadas (se houver). Se tem stack nova, pergunta *"Quer adicionar um Dev pra essa stack nova?"* com mesmo fluxo de D-08.

### Knowledge da squad (D-10 — DESENHADO em 2026-05-15)

Página `/squads/:id/knowledge` (já existe `SquadKnowledgePage` mas é raso). Reescrever em **4 abas**:

1. **Visão geral:** total chunks, divisão por `chunk_kind` (code/test/docs/config), divisão por stack, lista de fontes (repos indexados + materiais manuais), última atualização.
2. **Adicionar conteúdo:** upload manual de PDF/MD/.txt/.docx + URL/link (mesma UX da B2 do cenário B). Indexa imediatamente em `playbook:{squad_id}` com chunk_kind=docs.
3. **Buscar:** playground de busca semântica pra cliente debugar o que o agente vê. Input de query → mostra top 10 chunks com score + path + preview. Útil pra compliance e troubleshooting.
4. **Limpar/Auditar:** lista de chunks com checkbox pra deletar em massa. Filtros por fonte/data/chunk_kind. Botão "Deletar selecionados" com confirmação. Importante pra LGPD / direito ao esquecimento.

### Modal "Editar prompt" + "Remover agente" (D-11 — DESENHADO em 2026-05-15)

**Editar prompt** — modal grande:
- Textarea com system prompt atual (preenchido do SkillTemplate)
- Dropdown modelo Claude (sonnet/opus/haiku) com estimativa de custo/run
- Se skill_template paramétrico: bloco "Variáveis renderizadas" mostrando preview de como `{{ build_command }}`, `{{ stack_version }}` etc. são substituídas pra esta squad
- Botão "Restaurar default" volta pro prompt do catálogo
- Salvar → `PATCH /client/squads/{id}/agents/{agent_id}` atualiza SkillTemplate + re-provisiona Anthropic agent (mesmo `anthropic_agent_id` pode ser atualizado via `beta.agents.update`)

**Remover** — já desenhado na Tela 3. Mesmo padrão: modal com aviso de consequência específica do tier. Remoção marca AgentInstance como ARCHIVED (soft delete). Re-ativar disponível.

### Cross-squad opt-in (D-12 — DESENHADO em 2026-05-15)

Aba "Cross-squad" no painel da squad (D-03) — **só aparece quando tenant tem 2+ squads**.

**Layout:** lista de outras squads do tenant. Cada uma com 2 checkboxes:
- ☐ Esta squad pode delegar demandas pra `<squad-X>`
- ☐ `<squad-X>` pode delegar demandas pra esta

Bilateral: ambas as squads precisam ter ambas marcadas pra cross-squad funcionar. UI mostra status visual: "Autorização bilateral ativa ✓" quando ambas confirmam; "Aguardando autorização de `<squad-X>`" quando só uma confirmou.

**Notificação** quando outra squad pede autorização: aparece no painel da squad com botão "Aceitar" / "Recusar" inline. Cliente pode revogar a qualquer momento.

### Configurações do tenant (D-13 — DESENHADO em 2026-05-15)

Página `/settings` com sub-páginas:

- **`/settings/plan`** — Plano atual (FIXED/PAY_PER_USE/HYBRID) + limite mensal + uso atual com barra de progresso. Histórico de cobranças. Botão "Mudar de plano" (modal com comparativo de planos disponíveis).
- **`/settings/credentials`** — Listagem de credenciais cadastradas (GitHub/Jira tokens), nome, kind, última rotação. Botão "Rotacionar" por credencial. Botão "+ Adicionar credencial" pra cadastros antecipados (ex: cliente quer adicionar mais um token GitHub pra outro org).
- **`/settings/members`** — Lista de users do tenant + role (client_admin/client_reviewer/client_viewer/system_admin). Convidar novo user (email + role). Remover user. Mudar role.
- **`/settings/notifications`** — Email on/off pra tipos de evento (PR aberto, task falhou, mês cruzou limite). Webhook URL pra eventos JSON (pra integração externa). Test webhook.

### Cenário C — Tour/Demo (D-14 — DESENHADO em 2026-05-15)

Página `/setup/explore` (placeholder hoje). Substituir por tour interativo com 3 abas/passos:

1. **"O que esses agentes fazem?"** — Cada tier (BA, Architect, Dev, Reviewer) explicado em 2-3 frases com exemplo concreto. Visualização do diagrama de pipeline (mesmo da Tela 3 do cenário A).
2. **"Como uma demanda flui?"** — Demo de UMA task fictícia executando. Mock client-side simulando os 6 estados do D-05 com timestamps acelerados. Cliente vê BA refinando → Architect planejando → Dev implementando → PR aberto → Reviewer auditando → mergeado, sem rodar nada de verdade.
3. **"Pronto pra começar?"** — CTA grande pra voltar à Tela 0 e escolher A (tenho repo) ou B (zero).

**Implementação:** puramente frontend, sem backend. Mock data em config TS.

### Arquivar squad + Audit log (D-15 — DESENHADO em 2026-05-15)

**Arquivar squad** — aba "Config" do painel da squad:
- Botão "Arquivar squad" → modal destrutivo com lista do que acontece:
  - Tasks em curso → canceladas
  - RAG indexada → preservada (read-only, não deletada — pode reativar squad depois)
  - Credentials → preservadas (são do tenant, não da squad)
  - Cross-squad refs → outras squads notificadas que perderam delegação
  - AgentInstances → marcados ARCHIVED (Anthropic agents NÃO deletados — beta.agents.delete pode ser caro/lento)
- Confirmação requer digitar o nome da squad (anti-click-acidental)
- Squad fica visível em `/squads?include_archived=true` por 90 dias, depois soft-delete completo

**Audit log** — página `/audit`:
- Listagem cronológica de eventos do tenant: squad criada/editada/arquivada, agente provisionado/removido, repo adicionado, configuração de membro alterada, credencial rotacionada, plano mudado
- Filtros: tipo de evento, ator (user), data
- Exportar CSV
- Tabela `audit_events` nova (backend) com `(client_id, actor_user_id, event_kind, payload_json, created_at)`

### Integração Jira bidirecional (D-16 — DESENHADO em 2026-05-15)

**Princípio reiterado:** Jira = fonte da DEMANDA, painel = fonte da EXECUÇÃO. Os dois espelham.

**Direção Jira → Sistema (entrada):**
- Webhook Jira: issue created/updated/commented/transitioned
- Sistema lê: title, description, priority, sprint, labels, comments, attachments
- Marcador de ativação: hoje `@agents` na descrição. Refinar pra **label configurável** (cliente define qual label dispara — `dev-autonomo`, `agentes`, etc.) ou **campo customizado**. Configurável em `/settings/integration/jira`.

**Direção Sistema → Jira (saída):**
- Cada etapa importante posta comentário no Jira:
  - BA: "ACs propostos: [lista]"
  - Architect: "Plano: [resumo]"
  - Dev: "PR aberto: [link]"
  - Reviewer: "Review concluída: [verdict + sugestões]"
- Quando humano decide no painel: status do Jira muda (configurável)

**Status mapping configurável** — cliente escolhe que status Jira corresponde a cada fase:
- "Em desenvolvimento" → quando agente trabalha
- "Em revisão" → quando aguarda humano (Reviewer aprovou)
- "Done" → quando PR mergeado
- "Cancelado" → quando task cancelada
- Default sensato baseado em workflow Jira padrão. Cliente pode customizar em `/settings/integration/jira`.

**Cliente sem Jira:**
- Página `/demands` no painel — listagem de demandas criadas direto no painel + botão "+ Criar demanda" abre modal:
  - Title (obrigatório)
  - Description (textarea, suporta markdown)
  - Priority (Low/Medium/High)
  - Labels (chips)
- Atrás dos panos cria Task com `jira_issue_key=null` (ou prefix `LOCAL-{seq}`) e `jira_workspace_url=null`
- D-05 detecta ausência de Jira e adapta header (mostra título + autor sem link externo)
- Quando cliente conectar Jira depois, demandas locais NÃO migram automaticamente (cliente decide se quer "promover" via botão "Sincronizar com Jira" — fica como melhoria futura).

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

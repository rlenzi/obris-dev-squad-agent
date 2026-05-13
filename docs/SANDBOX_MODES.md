# Sandbox modes — como agentes executam código de clientes

Referência arquitetural para a evolução de `run_repo_check` e do
`AgentRunner` em direção a execução isolada do código do cliente.

A plataforma é **stack-agnóstica** (cada cliente declara stack em
`.dev-autonomo.yml`) e **modo-agnóstica** (cada cliente declara como
o agente deve obter um ambiente de execução).

## Os 3 modos

### 1. Ephemeral (default — stacks leves)

Container Docker novo por execução do agente.

```yaml
# .dev-autonomo.yml
sandbox:
  mode: "ephemeral"
  image: "python:3.11-slim"
  workdir: "/work"
```

**Tempo de subida:** 5-30s.
**RAM típica:** 200MB-2GB.
**Quando usar:** Python, Node, Go, Ruby, Rails, Java Spring leve, .NET
core simples. Maioria dos clientes web/api.

**Como funciona:**
- `run_repo_check` clona o worktree no container.
- Executa o comando do check.
- Captura stdout/stderr.
- Destroi o container.

**Isolamento:** total. Cada run é tabula rasa.

---

### 2. Shared persistent (stacks pesadas)

Cliente mantém ambiente Docker rodando permanentemente (servidor de DEV
deles). Agente conecta naquele ambiente em vez de subir do zero.

```yaml
sandbox:
  mode: "shared"
  compose_file: "docker/compose.agent-sandbox.yml"
  services_ready:
    - "http://localhost:9001/hac/healthcheck"
    - "tcp://localhost:5432"
  warmup_seconds: 600
  isolation: "schema_per_run"  # cria schema postgres por run
```

**Tempo de subida:** zero (já está quente).
**RAM típica:** 8-32GB+ (uma vez, persistente).
**Quando usar:** SAP Commerce/Hybris, SAP ERP, Oracle DB com dados de
prod, Java EE, sistemas legados pesados.

**Como funciona:**
- Cliente roda `docker compose up -d` na infra dele uma vez.
- Plataforma valida `services_ready` antes de cada run.
- Cada run cria um **schema/namespace novo no banco compartilhado**
  pra isolar dados.
- Run termina → cleanup do schema, container continua.

**Isolamento:** parcial. Container compartilhado, dados isolados por
schema.

**Por que não ephemeral:** subir SAP Commerce do zero leva 5-10min e
exige 8-16GB RAM por instância. Inviável por run.

---

### 3. External (SaaS proprietário)

Plataforma não sobe ambiente — fala direto com ambiente de DEV/staging
do cliente via API.

```yaml
sandbox:
  mode: "external"
  endpoint: "https://acme--dev.sandbox.my.salesforce.com"
  auth_secret_kind: "SALESFORCE_TOKEN"
  health_check: "/services/data/v60.0/sobjects"
```

**Tempo de subida:** zero.
**RAM:** N/A (não executa nada local).
**Quando usar:** Salesforce, ServiceNow, Microsoft Dynamics, SharePoint,
qualquer SaaS sem on-prem.

**Como funciona:**
- Agente lê código local normalmente (worktree).
- Quando precisa executar/testar, chama API do tenant DEV do cliente.
- Credenciais vêm do vault da plataforma (`auth_secret_kind`).

**Isolamento:** zero — agente opera no mesmo tenant que devs humanos
do cliente. Cliente é responsável por gerenciar conflitos.

**Cuidado:** mudanças aplicadas via API são reais no tenant DEV.
Reverter é problema do cliente.

---

## Como o Onboarding Analyst escolhe o modo

Ao analisar repo novo de cliente, o Onboarding Analyst (Fase 3.4)
descobre/infere o modo:

1. **External**: identifica SaaS proprietário no stack (Salesforce DX,
   SFDX project, ServiceNow YAML, etc.) → `mode: external`.
2. **Shared**: cliente declara que tem ambiente DEV existente, OU
   `docker compose up` leva > 60s, OU stack inclui SAP/Oracle EE.
3. **Ephemeral**: default. Cliente comum web/api.

Em todos os casos, o Onboarding Analyst pode **perguntar ao humano do
cliente** se ele tem ambiente DEV existente pra reusar (shared) ou
prefere isolamento total (ephemeral).

---

## Estado atual da implementação

| Modo | Status |
|---|---|
| Ephemeral | ⚠️ Parcial — `run_repo_check` executa no host, não em container. Docker-in-Docker no agent runner é fase 2. |
| Shared | ❌ Não implementado. Schema `.dev-autonomo.yml` já reservou os campos. |
| External | ❌ Não implementado. Schema reservado. |

## Roadmap

1. **Fase A** — `run_repo_check` ganha modo `ephemeral` real (Docker-in-Docker
   no worktree do agente). Requer agent runtime rodar com `/var/run/docker.sock`
   montado ou Docker socket-less alternativo (sysbox, kaniko).

2. **Fase B** — Modo `shared`: validador de `services_ready`, isolation
   `schema_per_run` no Postgres do cliente, tool `db_create_schema`.

3. **Fase C** — Modo `external`: registry de adapters por SaaS
   (Salesforce SOQL, ServiceNow REST, Dynamics OData). Cliente declara
   o adapter via `external.adapter: "salesforce"` no yml.

4. **Fase D** — `Onboarding Analyst` aprende a discovery do modo via
   análise do repo + entrevista com cliente.

## Como o CI usa cada modo

- **Ephemeral**: GitHub Actions workflow já rodando.
- **Shared**: workflow precisaria de `--network host` ou DNS interno
  apontando pro ambiente DEV do cliente — não viável sem self-hosted
  runner. Cliente roda `dev-autonomo-ci` own infra.
- **External**: GitHub Actions com credentials do tenant DEV
  injetadas via secrets do repo. Cuidado com side-effects em prod.

## Decisões de design importantes

1. **Modo é declaração do cliente, não escolha da plataforma.** A
   plataforma se adapta ao que o cliente pode/quer fornecer.

2. **Mesmo `.dev-autonomo.yml` cobre os 3 modos.** Não há tipos
   diferentes de yml. Campos opcionais por modo.

3. **Tool `run_repo_check` é o ponto de extensão.** Quando ela aprender
   `shared` e `external`, todos os agentes Dev existentes continuam
   funcionando — só ganham mais cenários cobertos.

4. **Health-check antes de comando é universal.** Independente do modo,
   se há `services_ready` ou `health_check` no yml, validar antes.

"""Catalogo inicial de stack profiles — usado pelo script de seed (Bloco B).

Cada entry produz uma linha em stack_profiles. base_prompt_template e o
DEV AGENT prompt pra aquela stack (BA/Architect/Reviewer ficam fora —
usam prompts manuais existentes em prompts/{tier}/managed.md).

Templates sao concisos e usam Jinja2 placeholders que serao preenchidos
em runtime por propose_skill_from_stack() (Bloco D):
  {{ build_command }}, {{ test_command }}, {{ lint_command }},
  {{ entry_points }}, {{ key_directories }}, {{ stack_version }}

Quando uma RAG cross-tenant comecar a ter conteudo (Bloco F), agentes
desta stack vao consultar e enriquecer respostas; ate la, rodam com
Claude knowledge embutido + este template.
"""

from __future__ import annotations

DEFAULT_TOOLS_DEV: list[dict] = [{"type": "agent_toolset_20260401"}]
DEFAULT_MODEL_DEV = "claude-sonnet-4-6"

# Template base compartilhado por todas as stacks — cada profile injeta
# secao "Convencoes desta stack" especifica + conventions_seed.
_BASE_DEV_TEMPLATE = """\
# Dev Agent — {stack_name}

Voce e um **Dev sênior em {stack_name}**. Recebe issues Jira refinadas
pelo BA + plano do Architect e implementa via PR no GitHub.

Ambiente: Managed Agents da Anthropic com toolset nativo (`bash`, file
ops, web). Repo do cliente vem ja montado em `/mnt/repo/` via
`github_repository` resource. Tokens Jira/GitHub via `/mnt/secrets/jira.env`
(faz `source` no primeiro bash).

## Stack do projeto

- **Linguagem/framework primario:** {framework_main}
- **Build:** `{{{{ build_command }}}}` (resolvido em runtime do manifest)
- **Test:** `{{{{ test_command }}}}`
- **Lint:** `{{{{ lint_command }}}}`
- **Versao detectada:** `{{{{ stack_version }}}}`

## Convencoes desta stack

{stack_conventions}

## Fluxo obrigatorio

Siga `prompts/dev/managed.md` (fluxo geral). Pontos especificos
desta stack:

{stack_specific_flow}

## Regras inegociaveis

- Diff minimo — mexa so no que a issue pede.
- Testes existentes precisam continuar verdes apos sua mudanca.
- PR sempre draft=true.
- Use --no-gpg-sign no commit (signing falha no container).
- Sem secrets em logs ou commits.
- Se algo bloquear (build vermelho que voce nao sabe resolver,
  dependencia faltando, escopo ambiguo): pare, comente no Jira pedindo
  orientacao, encerre a sessao.

## Quando consultar a RAG da stack

Antes de implementar mudanca nao-trivial em padrao desconhecido, chame
`retrieve_knowledge` na particao `stack_patterns:{slug}` — pode haver
padrao field-proven extraido de PR mergeado anteriormente, ou doc oficial
curada pela Orbis. Cite a fonte no PR body se usar.
"""


def _make_dev_profile(
    *,
    slug: str,
    stack_name: str,
    framework_main: str,
    description: str,
    stack_conventions: str,
    stack_specific_flow: str,
    conventions_seed: dict,
) -> dict:
    template = _BASE_DEV_TEMPLATE.format(
        stack_name=stack_name,
        framework_main=framework_main,
        stack_conventions=stack_conventions,
        stack_specific_flow=stack_specific_flow,
        slug=slug,
    )
    return {
        "slug": slug,
        "name": stack_name,
        "description": description,
        "base_prompt_template": template,
        "default_tools": DEFAULT_TOOLS_DEV,
        "default_model_alias": DEFAULT_MODEL_DEV,
        "conventions_seed": conventions_seed,
        "active": True,
    }


STACK_PROFILES: list[dict] = [
    _make_dev_profile(
        slug="python-fastapi",
        stack_name="Python + FastAPI",
        framework_main="FastAPI (async REST API)",
        description="API REST/async em Python com FastAPI, Pydantic, SQLAlchemy 2.0.",
        stack_conventions="""\
- Endpoints I/O sao **async**. Endpoints sync so se nao houver I/O.
- Pydantic v2 para validacao de request/response. `model_config = ConfigDict(...)` em vez de `Config:` class.
- SQLAlchemy 2.0 com `Mapped[]` typed annotations + `AsyncSession`.
- Dependency Injection via `Depends()` — auth, db session, etc.
- Errors via `HTTPException` (status + detail) — nunca `return {error: ...}`.
- Roteamento por router (`APIRouter`) + tag por modulo.
""",
        stack_specific_flow="""\
- Migrations: `alembic revision --autogenerate -m "..."` + `alembic upgrade head`.
- Lembre de adicionar `__init__.py` em diretorios novos.
- Schemas Pydantic ficam em `schemas/`, models em `db/models/`.
""",
        conventions_seed={
            "language": "python",
            "framework": "FastAPI",
            "package_managers": ["uv", "pip", "poetry"],
            "test_frameworks": ["pytest", "pytest-asyncio"],
            "lint_tools": ["ruff", "black", "mypy"],
            "orm": "SQLAlchemy 2.0",
            "migration_tool": "alembic",
            "common_pitfalls": [
                "Esquecer `async` em endpoints I/O",
                "Pydantic v1 style `Config` class (use ConfigDict v2)",
                "Session sync em codigo async",
            ],
        },
    ),
    _make_dev_profile(
        slug="python-django",
        stack_name="Python + Django",
        framework_main="Django (sync/async ORM-first)",
        description="Web framework full-stack Python — ORM + admin + templates.",
        stack_conventions="""\
- Models em `<app>/models.py`. Migrations: `python manage.py makemigrations <app>` + `migrate`.
- Views: prefira CBV (Class-Based Views) para CRUDs; FBV para casos simples.
- DRF para APIs REST se ja estiver no projeto.
- Forms / Serializers separados — nao misture validacao Django Form com DRF Serializer.
- Settings split: `settings/base.py`, `settings/dev.py`, `settings/prod.py`.
""",
        stack_specific_flow="""\
- Sempre rodar `python manage.py check` antes de commit.
- Migrations: nunca editar migration ja mergeada — crie nova.
- Admin: registra modelo novo em `<app>/admin.py`.
""",
        conventions_seed={
            "language": "python",
            "framework": "Django",
            "package_managers": ["pip", "poetry"],
            "test_frameworks": ["pytest-django", "django.test"],
            "lint_tools": ["ruff", "black"],
            "orm": "Django ORM",
            "migration_tool": "Django migrations",
            "common_pitfalls": [
                "N+1 queries (use select_related/prefetch_related)",
                "Esquecer de rodar makemigrations apos mudar model",
                "Misturar logica em views FBV gigantes",
            ],
        },
    ),
    _make_dev_profile(
        slug="python-flask",
        stack_name="Python + Flask",
        framework_main="Flask (microframework WSGI)",
        description="Microframework Python — minimalista, extensivel via blueprints.",
        stack_conventions="""\
- Blueprints para organizar routes por modulo. App factory pattern (`create_app()`).
- Extensions oficiais: Flask-SQLAlchemy, Flask-Migrate, Flask-Login.
- Pra APIs, use Flask-RESTful ou Flask-Smorest (com Marshmallow).
- Config via env vars + `app.config.from_object()`.
""",
        stack_specific_flow="""\
- Migrations: Flask-Migrate (`flask db migrate -m "..."` + `flask db upgrade`).
- Run dev: `flask --app app.py run` ou `python app.py`.
- Testes: usa `app.test_client()` em pytest.
""",
        conventions_seed={
            "language": "python",
            "framework": "Flask",
            "package_managers": ["pip", "poetry"],
            "test_frameworks": ["pytest"],
            "lint_tools": ["ruff", "black"],
            "orm": "SQLAlchemy (via Flask-SQLAlchemy)",
            "common_pitfalls": [
                "App context fora de request handlers",
                "Esquecer de registrar blueprint no app factory",
            ],
        },
    ),
    _make_dev_profile(
        slug="typescript-react-vite",
        stack_name="TypeScript + React + Vite",
        framework_main="React 18+ com Vite, TypeScript, Tailwind",
        description="SPA moderna em React/TS com Vite, shadcn/ui, React Router, TanStack Query.",
        stack_conventions="""\
- Components funcionais + hooks. Sem class components.
- TanStack Query (React Query) para server state — nunca useState pra dados de API.
- Forms: react-hook-form + zod schema.
- shadcn/ui (Radix + Tailwind) como design system. Componentes em `components/ui/`.
- Pages em `pages/`, hooks em `hooks/`, libs em `lib/`.
- Import alias `@/` mapeia `src/`.
- Tipagem estrita: `strict: true` no tsconfig.
""",
        stack_specific_flow="""\
- `npm run build` antes de commit valida TypeScript.
- Tests: vitest + testing-library (`renderHook`, `render`, `screen`).
- Mock fetch via `vi.mock` ou MSW.
""",
        conventions_seed={
            "language": "typescript",
            "framework": "React + Vite",
            "package_managers": ["npm", "pnpm", "yarn"],
            "test_frameworks": ["vitest", "@testing-library/react"],
            "lint_tools": ["eslint", "prettier"],
            "state_management": "TanStack Query (server) + Zustand/Context (local)",
            "ui_lib": "shadcn/ui + Tailwind",
            "common_pitfalls": [
                "useEffect com array de deps incompleto",
                "Misturar TanStack Query com useState pra mesma data",
                "Imports relativos quando @ alias existe",
            ],
        },
    ),
    _make_dev_profile(
        slug="typescript-next",
        stack_name="TypeScript + Next.js",
        framework_main="Next.js 14+ App Router, RSC, Server Actions",
        description="Framework React full-stack com SSR, RSC e Server Actions.",
        stack_conventions="""\
- App Router (`app/`) — Pages Router (`pages/`) so se projeto legacy.
- Server Components por default — adicione `'use client'` so quando precisar.
- Server Actions para mutations (vs API routes legadas).
- Data fetching server-side em `async` server components.
- Metadata API para SEO em `layout.tsx` / `page.tsx`.
""",
        stack_specific_flow="""\
- `next build` valida tipos + roteamento.
- Tests: Playwright e2e + vitest unit (para utils/hooks).
""",
        conventions_seed={
            "language": "typescript",
            "framework": "Next.js",
            "package_managers": ["npm", "pnpm"],
            "test_frameworks": ["vitest", "playwright"],
            "lint_tools": ["eslint", "prettier"],
            "common_pitfalls": [
                "Misturar Server e Client components sem fronteira clara",
                "Esquecer `'use client'` em hooks customizados",
                "Cache de fetch inadequado (use `cache`, `next: { revalidate }`)",
            ],
        },
    ),
    _make_dev_profile(
        slug="typescript-angular",
        stack_name="TypeScript + Angular",
        framework_main="Angular 17+ standalone components, signals",
        description="Framework enterprise full-featured — DI, RxJS, módulos/standalone.",
        stack_conventions="""\
- Angular 17+ usa **standalone components** por default (sem NgModule).
- Signals (`signal()`, `computed()`) para state reativo — preferir sobre RxJS quando possivel.
- Services injetaveis com `@Injectable({ providedIn: 'root' })`.
- Routing: lazy load via `loadComponent` no router config.
- Form: Reactive Forms (FormBuilder) em vez de Template Forms.
""",
        stack_specific_flow="""\
- `ng build --configuration=production` valida AOT + tipos.
- Tests: Karma + Jasmine (legacy) ou Jest (moderno).
- Lint: angular-eslint.
""",
        conventions_seed={
            "language": "typescript",
            "framework": "Angular",
            "package_managers": ["npm"],
            "test_frameworks": ["karma+jasmine", "jest"],
            "lint_tools": ["@angular-eslint", "prettier"],
            "common_pitfalls": [
                "Subscribe sem unsubscribe (use takeUntilDestroyed)",
                "Misturar NgModule legacy com standalone",
                "ChangeDetection.Default em listas grandes (use OnPush)",
            ],
        },
    ),
    _make_dev_profile(
        slug="typescript-vue-nuxt",
        stack_name="TypeScript + Vue 3 + Nuxt",
        framework_main="Vue 3 Composition API + Nuxt 3",
        description="Framework progressivo Vue 3 com Nuxt 3 para SSR/SSG.",
        stack_conventions="""\
- Composition API (`<script setup>`) — Options API so em codigo legacy.
- Composables em `composables/` (auto-importadas).
- Pinia para state management.
- `definePageMeta` para layout/middleware por pagina.
- Server routes em `server/api/` (h3 handlers).
""",
        stack_specific_flow="""\
- `nuxt build` valida tipos + roteamento.
- Tests: vitest + @vue/test-utils.
""",
        conventions_seed={
            "language": "typescript",
            "framework": "Vue 3 + Nuxt 3",
            "package_managers": ["npm", "pnpm"],
            "test_frameworks": ["vitest", "@vue/test-utils"],
            "lint_tools": ["eslint", "prettier"],
            "common_pitfalls": [
                "Reatividade quebrada com destructure de reactive() — use toRefs",
                "useFetch vs $fetch (semantica diferente)",
            ],
        },
    ),
    _make_dev_profile(
        slug="javascript-node-express",
        stack_name="JavaScript + Node.js + Express",
        framework_main="Node.js LTS + Express",
        description="Backend Node.js classico com Express, middleware, routes.",
        stack_conventions="""\
- ES Modules (`"type": "module"` no package.json) preferido — CommonJS so em legacy.
- Middleware order matters — auth antes de routes, error handler por ultimo.
- Async handlers: use `express-async-errors` ou wrappear com `try/catch`.
- Validation: zod ou joi nos middlewares de entrada.
""",
        stack_specific_flow="""\
- Sem build step (a menos que use TypeScript). `node --watch` para dev.
- Tests: Jest ou Vitest.
""",
        conventions_seed={
            "language": "javascript",
            "framework": "Express",
            "package_managers": ["npm", "pnpm"],
            "test_frameworks": ["jest", "vitest"],
            "lint_tools": ["eslint", "prettier"],
            "common_pitfalls": [
                "Async handler sem catch (req nao termina)",
                "CORS configurado errado em prod",
            ],
        },
    ),
    _make_dev_profile(
        slug="java-spring-boot",
        stack_name="Java + Spring Boot",
        framework_main="Java 17+ LTS + Spring Boot 3.x",
        description="Stack enterprise Java — Spring Boot, JPA/Hibernate, Maven/Gradle.",
        stack_conventions="""\
- Layered architecture: Controller → Service → Repository.
- `@Service`, `@RestController`, `@Repository` — DI por construtor (final fields + Lombok @RequiredArgsConstructor).
- JPA Entities anotadas (`@Entity`), repos extendendo `JpaRepository<T, ID>`.
- DTOs separados de Entities — nunca expor Entity direto na API.
- Exception handling via `@ControllerAdvice` + `@ExceptionHandler`.
- Properties em `application.yml` (preferir YAML sobre .properties).
""",
        stack_specific_flow="""\
- Build: `./mvnw clean install` ou `./gradlew build`.
- Tests: JUnit 5 + Spring Boot Test + Mockito.
- Migrations: Flyway (`db/migration/V1__init.sql`) ou Liquibase.
""",
        conventions_seed={
            "language": "java",
            "framework": "Spring Boot",
            "package_managers": ["maven", "gradle"],
            "test_frameworks": ["junit5", "mockito", "@SpringBootTest"],
            "lint_tools": ["spotless", "checkstyle"],
            "migration_tool": "flyway",
            "common_pitfalls": [
                "N+1 com JPA lazy loading (use @EntityGraph ou fetch join)",
                "Misturar Entity com response DTO",
                "@Transactional em metodo public chamado de dentro da mesma classe (nao propaga)",
            ],
        },
    ),
    _make_dev_profile(
        slug="dotnet-core",
        stack_name=".NET Core / ASP.NET Core",
        framework_main=".NET 8+ LTS, ASP.NET Core, EF Core",
        description="Stack Microsoft moderna — minimal APIs ou controllers, EF Core.",
        stack_conventions="""\
- Minimal APIs preferidas para endpoints pequenos; Controllers para mais estrutura.
- Dependency Injection nativo (`builder.Services.AddScoped<...>`).
- EF Core com DbContext + migrations (`dotnet ef migrations add ...`).
- Records para DTOs imutaveis.
- Nullable reference types habilitado (`<Nullable>enable</Nullable>` no csproj).
""",
        stack_specific_flow="""\
- Build: `dotnet build`. Testes: `dotnet test` (xUnit / NUnit / MSTest).
- Migrations: `dotnet ef database update`.
""",
        conventions_seed={
            "language": "csharp",
            "framework": "ASP.NET Core",
            "package_managers": ["nuget"],
            "test_frameworks": ["xunit", "nunit", "mstest"],
            "lint_tools": ["dotnet format", "stylecop"],
            "orm": "Entity Framework Core",
            "common_pitfalls": [
                "Ignorar nullable warnings",
                "DbContext lifetime errado (Scoped, nao Singleton)",
            ],
        },
    ),
    _make_dev_profile(
        slug="go-gin",
        stack_name="Go + Gin",
        framework_main="Go 1.21+ + Gin HTTP framework",
        description="Backend Go performatico — Gin, GORM ou sqlc, gomod.",
        stack_conventions="""\
- Packages organizados por feature (`cmd/`, `internal/`, `pkg/`).
- Error handling explicito — sempre `if err != nil { return ..., err }`. Nunca panic em codigo de prod.
- Interfaces pequenas (Go proverb: "the bigger the interface, the weaker the abstraction").
- Goroutines com `context.Context` para cancelamento.
- GORM ou sqlc (preferencia: sqlc para tipos seguros).
""",
        stack_specific_flow="""\
- Build: `go build ./...`. Tests: `go test ./...`.
- Lint: `golangci-lint run`.
""",
        conventions_seed={
            "language": "go",
            "framework": "Gin",
            "package_managers": ["go modules"],
            "test_frameworks": ["go test (stdlib)", "testify"],
            "lint_tools": ["golangci-lint", "gofmt"],
            "common_pitfalls": [
                "Goroutine vazando (sem context)",
                "Shared mutable state sem mutex",
                "Ignorar errors com `_`",
            ],
        },
    ),
    _make_dev_profile(
        slug="ruby-rails",
        stack_name="Ruby + Rails",
        framework_main="Ruby 3+ + Rails 7+",
        description="Convention-over-configuration Ruby web framework — ActiveRecord, ActionPack, Hotwire.",
        stack_conventions="""\
- Convention over configuration — siga a "Rails Way" antes de inventar.
- ActiveRecord migrations (`rails generate migration ...` + `rails db:migrate`).
- Service objects em `app/services/` para logica complexa fora de models/controllers (Skinny Controller, Skinny Model).
- Hotwire (Turbo + Stimulus) para interatividade sem SPA.
- Strong parameters obrigatorios em controllers.
""",
        stack_specific_flow="""\
- Tests: RSpec ou Minitest. Factories: factory_bot.
- Linting: RuboCop.
""",
        conventions_seed={
            "language": "ruby",
            "framework": "Rails",
            "package_managers": ["bundler"],
            "test_frameworks": ["rspec", "minitest"],
            "lint_tools": ["rubocop"],
            "orm": "ActiveRecord",
            "common_pitfalls": [
                "N+1 queries (use includes/preload)",
                "Fat models / fat controllers — extraia para services",
            ],
        },
    ),
    _make_dev_profile(
        slug="java-hybris-sap-commerce",
        stack_name="Java + Hybris / SAP Commerce Cloud",
        framework_main="Hybris / SAP Commerce (Java, Spring-based extensions)",
        description="Plataforma de commerce enterprise — Hybris/SAP Commerce, ServiceLayer, ImpEx, OCC.",
        stack_conventions="""\
- ServiceLayer pattern — services injetados via `@Resource`, NUNCA acesso DAO direto.
- Extensions em `bin/custom/<name>/` — sempre extend, nunca modificar core.
- Models (jaloitems.xml + ImpEx) gerados via `ant clean all`.
- Strategy/Populator/Converter patterns para mapping (Model ↔ DTO).
- OCC (Omni Commerce Connect) APIs em `*-occaddon` para integracoes mobile/headless.
- Business Logic em Services; Persistencia via FlexibleSearchService; Workflow em hooks/listeners.
- ImpEx scripts para data seeding (em `resources/impex/`).
""",
        stack_specific_flow="""\
- Build: `ant clean all` (full) ou `ant build` (incremental). Lento.
- Tests: JUnit + Hybris test framework (`Web` / `IntegrationTest`).
- HAC (Hybris Administration Console) em `/hac` para debug + flexible search ad-hoc.
- Properties em `local.properties` do extension.
""",
        conventions_seed={
            "language": "java",
            "framework": "Hybris / SAP Commerce",
            "package_managers": ["ant", "maven (limited)"],
            "test_frameworks": ["junit", "hybris testframework"],
            "lint_tools": ["checkstyle"],
            "common_pitfalls": [
                "Acessar DAO direto (use ServiceLayer)",
                "Modificar core extension (sempre extend)",
                "FlexibleSearch sem index hints em queries grandes",
                "ImpEx com encoding errado (sempre UTF-8 com BOM)",
            ],
        },
    ),
    _make_dev_profile(
        slug="salesforce-apex",
        stack_name="Salesforce + Apex",
        framework_main="Apex (Java-like) + Lightning Web Components + Flow",
        description="Plataforma SaaS Salesforce — Apex, LWC, Flow, SOQL/SOSL.",
        stack_conventions="""\
- Apex governor limits: 100 SOQL queries, 150 DML, 50k rows, 6MB heap — sempre desenhar pra batch / bulk.
- SOQL bulkified — nunca query em loop. Use Maps/Sets pra batch.
- Triggers: 1 trigger por SObject (use Trigger Framework).
- Test classes com `@isTest`, cobertura minima 75%.
- LWC para UI moderna (vs Aura legacy).
- Flow para automacao declarativa antes de codigo.
- Named Credentials para integracao externa (vs hardcode de URL/token).
""",
        stack_specific_flow="""\
- Deploy: SFDX (`sf project deploy start`) ou Workbench / Change Set.
- Tests: `sf apex run test --code-coverage --result-format human`.
- Anonymous Apex em Developer Console para experimentos.
""",
        conventions_seed={
            "language": "apex",
            "framework": "Salesforce Platform",
            "package_managers": ["sfdx", "ant migration tool"],
            "test_frameworks": ["@isTest classes"],
            "lint_tools": ["pmd-apex", "sfdx-scanner"],
            "common_pitfalls": [
                "SOQL dentro de loop (governor limit)",
                "Trigger sem framework (multipla execucao)",
                "Test sem `Test.startTest()/stopTest()` para resetar limits",
                "DML em getter (proibido)",
            ],
        },
    ),
    _make_dev_profile(
        slug="java-atg-endeca",
        stack_name="Java + ATG / Oracle Commerce + Endeca",
        framework_main="ATG (Nucleus DI) + Endeca Search Guidance",
        description="Plataforma de commerce Oracle legacy — ATG Nucleus, repositories, Endeca records.",
        stack_conventions="""\
- Nucleus DI: componentes em `.properties` apontados por `globalScope`/`requestScope`/`sessionScope`.
- Repository pattern (XML-based) — definicao em `<module>-data.xml` + properties.
- Form Handlers para UI workflow (extends GenericFormHandler).
- DSP tags em JSPs (NUNCA mix com EL puro).
- Endeca: records indexados via `forge` + `dgidx`. Queries via Assembler API.
- Custom Cartridges para extensao da search.
""",
        stack_specific_flow="""\
- Build: `runAssembler` para gerar EAR. Deploy: WebLogic/JBoss.
- Tests: limitados — geralmente integration test contra ATG ServerRunner.
- ATG Server Console (Dynamo Admin) em `/dyn/admin` para inspecionar componentes.
""",
        conventions_seed={
            "language": "java",
            "framework": "ATG / Oracle Commerce + Endeca",
            "package_managers": ["ant"],
            "test_frameworks": ["junit (limited)", "ATG ServerRunner"],
            "lint_tools": ["checkstyle"],
            "common_pitfalls": [
                "Scope errado no Nucleus (request vs session vs global)",
                "Form handler com submit chain inconsistente",
                "Endeca: forge sem record_spec adequada",
                "DSP/EL mix em JSP — quebra parsing",
            ],
        },
    ),
]

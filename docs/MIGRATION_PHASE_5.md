# Fase 5 — Outcomes ativos

Este documento registra as mudanças introduzidas na Fase 5 da migração
para Managed Agents, com foco na ativação do mecanismo de Outcomes.

## O que mudou

- **Adição de `user.define_outcome` no fluxo do Dev:** o orquestrador
  agora chama `user.define_outcome` antes de despachar o agente,
  permitindo declarar explicitamente o resultado esperado da sessão e
  fornecendo ao agente um alvo concreto a atingir.
- **Rubric textual passada por sessão:** cada sessão recebe uma rubric
  em texto livre descrevendo os critérios de aceitação; o agente usa
  essa rubric para auto-avaliar suas entregas a cada iteração, sem
  depender de heurísticas genéricas.
- **Iteração automática até `max_iterations` ou rubric atendida:** o
  loop de execução roda automaticamente até que todos os critérios da
  rubric sejam satisfeitos ou o limite de `max_iterations` seja
  atingido, garantindo convergência sem intervenção humana a cada
  ciclo.

## Próximos passos

- **Fase 6 — Dreaming:** introdução de um agente de síntese offline
  que processa logs de sessões passadas para gerar insights e sugerir
  melhorias de prompt de forma assíncrona.
- **Fase 7 — RAG em camadas:** implementação de recuperação aumentada
  por geração em múltiplas camadas (contexto de projeto, base de
  conhecimento corporativa e memória de longo prazo) para enriquecer
  automaticamente o contexto dos agentes.

---

Consulte também: [MANAGED_AGENTS.md](MANAGED_AGENTS.md) e
[CONVENTIONS.md](../docs/CONVENTIONS.md).

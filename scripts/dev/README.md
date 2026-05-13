# scripts/dev

Scripts **descartaveis** usados durante o desenvolvimento da plataforma
para exercitar componentes que ainda nao tem UI/API consumindo eles.

Cada script aqui tem uma "data de validade": quando o equivalente
existir no painel/Control Plane, o script vira redundante e deve ser
removido (ou movido para `scripts/ops/` se virar utilitario operacional
legitimo, tipo "reindex emergencial").

**Nao confunda** com `tests/integration/` (testes permanentes que
exercitam componentes em CI) nem com `src/dev_autonomo/` (codigo da
plataforma em si).

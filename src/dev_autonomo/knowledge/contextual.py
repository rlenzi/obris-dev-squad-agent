"""Contextual Retrieval (Anthropic) — gera descrição curta situando cada
chunk dentro do documento antes de embedar.

Técnica: https://www.anthropic.com/news/contextual-retrieval
Redução de falha de busca: ~35% (embedding only) → ~50% combinado com BM25 +
rerank.

Implementação:
- Para cada chunk, passa (full_document, chunk_content) pro Haiku 4.5.
- Prompt pede 1-2 frases situando o trecho.
- Resultado é prefixado ao chunk antes de embedar.

Otimização de custo:
- Usa prompt caching nas chamadas (Haiku 4.5 input $1/MTok, cache read
  $0.10/MTok). Cache do full_document é reusado se múltiplos chunks
  vierem do mesmo arquivo.
- Caller deve batchear chunks por arquivo pra maximizar cache hit.

Custo típico: ~$1-3 USD por 1M tokens de código indexado (Haiku + cache).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal

import anthropic

from dev_autonomo.config import get_settings

logger = logging.getLogger(__name__)

HAIKU_MODEL = "claude-haiku-4-5"

SYSTEM_BASE = (
    "Você é um indexador semântico. Sua única função é produzir "
    "descrições curtas que situam trechos de código no contexto do "
    "arquivo todo, para uso em RAG."
)

CHUNK_PROMPT = """\
<chunk>
{chunk}
</chunk>

Forneça uma descrição **curta** (1-2 frases, máximo 80 palavras) que
situe esse trecho no contexto do documento todo (que está no system),
para uso em retrieval semântico. Capture:
- A que módulo/componente o trecho pertence.
- Qual é o seu papel ou responsabilidade dentro do arquivo.
- Qualquer convenção/decisão local que ajude a entender o trecho.

Não cite linha por linha. Não repita o conteúdo. Apenas a descrição
contextualizando.
"""


@dataclass(slots=True)
class ContextualResult:
    description: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_creation_tokens: int


class ContextualPrefixer:
    """Gera descrições contextualizadas via Haiku.

    Use ``contextualize(document, chunk)`` por chamada. Para múltiplos
    chunks do mesmo arquivo, chame em sequência — prompt caching de 5min
    pega o documento.
    """

    HAIKU_INPUT_USD_PER_MTOKEN = Decimal("1.00")
    HAIKU_OUTPUT_USD_PER_MTOKEN = Decimal("5.00")
    HAIKU_CACHE_READ_USD_PER_MTOKEN = Decimal("0.10")
    HAIKU_CACHE_WRITE_USD_PER_MTOKEN = Decimal("1.25")

    def __init__(self, anthropic_client: anthropic.Anthropic | None = None) -> None:
        if anthropic_client is None:
            anthropic_client = anthropic.Anthropic(
                api_key=get_settings().ANTHROPIC_API_KEY.get_secret_value()
            )
        self._client = anthropic_client

    def contextualize(self, document: str, chunk: str) -> ContextualResult:
        # Estrutura otimizada pra prompt caching:
        # - system tem 2 blocos: instrucao base (estavel) + documento
        #   com cache_control ephemeral. Chamadas subsequentes com o
        #   mesmo documento batem cache_read em vez de cache_write.
        # - user message contem so o chunk (varia por chamada).
        # Cache TTL ephemeral = 5min; caller deve batchear chunks do
        # mesmo arquivo em janela curta pra maximizar cache hit.
        response = self._client.messages.create(
            model=HAIKU_MODEL,
            max_tokens=200,
            system=[
                {"type": "text", "text": SYSTEM_BASE},
                {
                    "type": "text",
                    "text": f"<document>\n{document}\n</document>",
                    "cache_control": {"type": "ephemeral"},
                },
            ],
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": CHUNK_PROMPT.format(chunk=chunk),
                        }
                    ],
                }
            ],
        )

        text = ""
        for block in response.content:
            if hasattr(block, "text"):
                text += block.text

        usage = response.usage
        return ContextualResult(
            description=text.strip(),
            input_tokens=getattr(usage, "input_tokens", 0) or 0,
            output_tokens=getattr(usage, "output_tokens", 0) or 0,
            cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
            cache_creation_tokens=getattr(usage, "cache_creation_input_tokens", 0) or 0,
        )

    def cost_usd(self, result: ContextualResult) -> Decimal:
        return (
            Decimal(result.input_tokens) / Decimal("1000000") * self.HAIKU_INPUT_USD_PER_MTOKEN
            + Decimal(result.output_tokens) / Decimal("1000000") * self.HAIKU_OUTPUT_USD_PER_MTOKEN
            + Decimal(result.cache_read_tokens) / Decimal("1000000") * self.HAIKU_CACHE_READ_USD_PER_MTOKEN
            + Decimal(result.cache_creation_tokens) / Decimal("1000000") * self.HAIKU_CACHE_WRITE_USD_PER_MTOKEN
        )


def prefix_chunk_with_context(description: str, chunk_embedding_text: str) -> str:
    """Constrói o texto final a ser embeddado: contexto + chunk original.

    Mantém o chunk como-está; contexto vai em bloco prefixado claramente.
    """
    return f"[contexto]\n{description}\n[/contexto]\n\n{chunk_embedding_text}"

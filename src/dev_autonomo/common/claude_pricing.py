"""Tabela de pricing dos modelos Claude (USD por 1M tokens).

Valores baseados em pricing publico da Anthropic em 2026-Q2.
Cache: leitura custa 10% do input price; escrita custa 125% (25% extra).

ATUALIZAR quando Anthropic mudar pricing (https://www.anthropic.com/pricing).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class ModelPricing:
    input_usd_per_mtoken: Decimal
    output_usd_per_mtoken: Decimal
    cache_read_multiplier: Decimal = Decimal("0.1")
    cache_write_multiplier: Decimal = Decimal("1.25")

    def cost_usd(
        self,
        input_tokens: int,
        output_tokens: int,
        cache_read_tokens: int = 0,
        cache_write_tokens: int = 0,
    ) -> Decimal:
        per_token_in = self.input_usd_per_mtoken / Decimal("1000000")
        per_token_out = self.output_usd_per_mtoken / Decimal("1000000")
        cost = (
            per_token_in * Decimal(input_tokens)
            + per_token_out * Decimal(output_tokens)
            + per_token_in * self.cache_read_multiplier * Decimal(cache_read_tokens)
            + per_token_in * self.cache_write_multiplier * Decimal(cache_write_tokens)
        )
        return cost.quantize(Decimal("0.000001"))


# Pricing por modelo (alias -> ModelPricing)
PRICING: dict[str, ModelPricing] = {
    "claude-opus-4-7": ModelPricing(
        input_usd_per_mtoken=Decimal("15"),
        output_usd_per_mtoken=Decimal("75"),
    ),
    "claude-sonnet-4-6": ModelPricing(
        input_usd_per_mtoken=Decimal("3"),
        output_usd_per_mtoken=Decimal("15"),
    ),
    "claude-haiku-4-5": ModelPricing(
        input_usd_per_mtoken=Decimal("1"),
        output_usd_per_mtoken=Decimal("5"),
    ),
    # Aliases versionados (Anthropic retorna o ID exato no response.model)
    "claude-haiku-4-5-20251001": ModelPricing(
        input_usd_per_mtoken=Decimal("1"),
        output_usd_per_mtoken=Decimal("5"),
    ),
}


def get_pricing(model: str) -> ModelPricing:
    """Retorna pricing para o modelo. Cai no Sonnet se desconhecido (conservador)."""
    if model in PRICING:
        return PRICING[model]
    # fallback conservador: Sonnet pricing
    return PRICING["claude-sonnet-4-6"]

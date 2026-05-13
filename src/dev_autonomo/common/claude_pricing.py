"""Tabela de pricing dos modelos (Claude + Voyage + outros).

Valores baseados em pricing publico em 2026-Q2 (USD por 1M tokens).
ATUALIZAR quando provedor mudar pricing.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class ModelPricing:
    input_usd_per_mtoken: Decimal
    output_usd_per_mtoken: Decimal = Decimal("0")  # embeddings nao tem output
    cache_read_multiplier: Decimal = Decimal("0.1")
    cache_write_multiplier: Decimal = Decimal("1.25")

    def cost_usd(
        self,
        input_tokens: int,
        output_tokens: int = 0,
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


# ---- Claude (Anthropic) ----
CLAUDE_PRICING: dict[str, ModelPricing] = {
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
    "claude-haiku-4-5-20251001": ModelPricing(
        input_usd_per_mtoken=Decimal("1"),
        output_usd_per_mtoken=Decimal("5"),
    ),
}


# ---- Voyage AI ----
VOYAGE_PRICING: dict[str, ModelPricing] = {
    "voyage-code-3": ModelPricing(
        input_usd_per_mtoken=Decimal("0.18"),
    ),
    "voyage-3.5": ModelPricing(
        input_usd_per_mtoken=Decimal("0.06"),
    ),
    "voyage-3.5-lite": ModelPricing(
        input_usd_per_mtoken=Decimal("0.02"),
    ),
}


# Provedor -> tabela
ALL_PRICING: dict[str, dict[str, ModelPricing]] = {
    "anthropic": CLAUDE_PRICING,
    "voyage": VOYAGE_PRICING,
}


def get_pricing(model: str, provider: str = "anthropic") -> ModelPricing:
    """Retorna pricing para (model, provider). Fallback conservador no Sonnet."""
    table = ALL_PRICING.get(provider, CLAUDE_PRICING)
    if model in table:
        return table[model]
    # fallback: Sonnet pricing (conservador para Claude)
    return CLAUDE_PRICING["claude-sonnet-4-6"]

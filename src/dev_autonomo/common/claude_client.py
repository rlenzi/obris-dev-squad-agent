"""Wrapper async Anthropic com cost tracking automatico em external_api_calls."""

from __future__ import annotations

import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID

import anthropic
from anthropic.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from dev_autonomo.common.claude_pricing import get_pricing
from dev_autonomo.common.enums import ApiCallKind, ApiProvider
from dev_autonomo.config import get_settings
from dev_autonomo.db.models.cost import ExternalApiCall


@dataclass(slots=True)
class ClaudeResponse:
    text: str
    model: str
    raw: Message
    input_tokens: int
    output_tokens: int
    cache_creation_input_tokens: int
    cache_read_input_tokens: int
    cost_usd: Decimal
    latency_ms: int
    request_id: str | None

    @property
    def stop_reason(self) -> str | None:
        return self.raw.stop_reason


class ClaudeClient:
    """Cliente unificado para chamadas Claude com instrumentation.

    Grava cada chamada em external_api_calls com provider=ANTHROPIC, kind=CHAT.
    """

    def __init__(
        self,
        session: AsyncSession | None = None,
        anthropic_client: anthropic.AsyncAnthropic | None = None,
    ) -> None:
        self._session = session
        if anthropic_client is None:
            settings = get_settings()
            anthropic_client = anthropic.AsyncAnthropic(
                api_key=settings.ANTHROPIC_API_KEY.get_secret_value(),
            )
        self._anthropic = anthropic_client

    async def complete(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        system: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 1.0,
        client_id: UUID | None = None,
        task_id: UUID | None = None,
        agent_instance_id: UUID | None = None,
        extra_kwargs: dict[str, Any] | None = None,
    ) -> ClaudeResponse:
        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": messages,
            "temperature": temperature,
        }
        if system:
            kwargs["system"] = system
        if extra_kwargs:
            kwargs.update(extra_kwargs)

        start = time.monotonic()
        error: str | None = None
        msg: Message | None = None
        try:
            msg = await self._anthropic.messages.create(**kwargs)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            latency_ms = int((time.monotonic() - start) * 1000)
            if self._session is not None and client_id is not None:
                if msg is not None:
                    await self._record_call(
                        msg=msg,
                        latency_ms=latency_ms,
                        client_id=client_id,
                        task_id=task_id,
                        agent_instance_id=agent_instance_id,
                    )
                elif error is not None:
                    await self._record_error(
                        model=model,
                        latency_ms=latency_ms,
                        client_id=client_id,
                        task_id=task_id,
                        agent_instance_id=agent_instance_id,
                        error=error,
                    )

        assert msg is not None
        return self._build_response(msg, latency_ms)

    # ---- Helpers ----

    def _build_response(self, msg: Message, latency_ms: int) -> ClaudeResponse:
        text = "".join(
            block.text for block in msg.content if getattr(block, "type", None) == "text"
        )

        usage = msg.usage
        input_tokens = usage.input_tokens
        output_tokens = usage.output_tokens
        cache_creation = getattr(usage, "cache_creation_input_tokens", 0) or 0
        cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0

        pricing = get_pricing(msg.model, provider="anthropic")
        cost = pricing.cost_usd(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=cache_read,
            cache_write_tokens=cache_creation,
        )

        return ClaudeResponse(
            text=text,
            model=msg.model,
            raw=msg,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_creation_input_tokens=cache_creation,
            cache_read_input_tokens=cache_read,
            cost_usd=cost,
            latency_ms=latency_ms,
            request_id=getattr(msg, "id", None),
        )

    async def _record_call(
        self,
        *,
        msg: Message,
        latency_ms: int,
        client_id: UUID,
        task_id: UUID | None,
        agent_instance_id: UUID | None,
    ) -> None:
        assert self._session is not None
        response = self._build_response(msg, latency_ms)
        call = ExternalApiCall(
            client_id=client_id,
            task_id=task_id,
            agent_instance_id=agent_instance_id,
            provider=ApiProvider.ANTHROPIC,
            kind=ApiCallKind.CHAT,
            model=msg.model,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            cache_creation_input_tokens=response.cache_creation_input_tokens,
            cache_read_input_tokens=response.cache_read_input_tokens,
            cost_usd=response.cost_usd,
            latency_ms=latency_ms,
            request_id=response.request_id,
        )
        self._session.add(call)
        await self._session.flush()

    async def _record_error(
        self,
        *,
        model: str,
        latency_ms: int,
        client_id: UUID,
        task_id: UUID | None,
        agent_instance_id: UUID | None,
        error: str,
    ) -> None:
        assert self._session is not None
        call = ExternalApiCall(
            client_id=client_id,
            task_id=task_id,
            agent_instance_id=agent_instance_id,
            provider=ApiProvider.ANTHROPIC,
            kind=ApiCallKind.CHAT,
            model=model,
            input_tokens=0,
            output_tokens=0,
            cost_usd=Decimal("0"),
            latency_ms=latency_ms,
            error=error,
        )
        self._session.add(call)
        await self._session.flush()

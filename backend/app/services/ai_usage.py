"""Exact AI cost tracking.

Every OpenAI call reports the exact tokens it used (response.usage). The LLM
and embedding providers pass that to record(), which writes one
ai_usage_log row with the cost worked out from PRICES below. Recording must
never break the real work, so every failure here is swallowed and logged.

Which job/candidate a call belongs to is set by the caller with
usage_context(job_id=..., candidate_id=...) -- e.g. resume ingestion sets
the candidate, AI scoring sets both.
"""
from __future__ import annotations

import contextvars
import logging
import uuid
from contextlib import contextmanager

logger = logging.getLogger(__name__)

# USD per 1 million tokens: (input, cached input, output). Check
# https://openai.com/api/pricing and update if OpenAI changes prices.
PRICES: dict[str, tuple[float, float, float]] = {
    "gpt-5": (1.25, 0.125, 10.00),
    "gpt-5-mini": (0.25, 0.025, 2.00),
    "gpt-5-nano": (0.05, 0.005, 0.40),
    "text-embedding-3-large": (0.13, 0.13, 0.0),
    "text-embedding-3-small": (0.02, 0.02, 0.0),
}

# Used for "AI score N candidates (~₹x)" until real scoring calls exist to average.
DEFAULT_SCORING_COST_USD = 0.0026

_ctx: contextvars.ContextVar[dict] = contextvars.ContextVar("ai_usage_ctx", default={})


@contextmanager
def usage_context(*, job_id=None, candidate_id=None):
    current = dict(_ctx.get())
    if job_id is not None:
        current["job_id"] = job_id
    if candidate_id is not None:
        current["candidate_id"] = candidate_id
    token = _ctx.set(current)
    try:
        yield
    finally:
        _ctx.reset(token)


def _price_for(model: str) -> tuple[float, float, float] | None:
    if model in PRICES:
        return PRICES[model]
    # dated snapshots, e.g. "gpt-5-mini-2025-08-07"
    for name in sorted(PRICES, key=len, reverse=True):
        if model.startswith(name):
            return PRICES[name]
    return None


def cost_usd(model: str, input_tokens: int, cached_tokens: int, output_tokens: int) -> tuple[float, bool]:
    price = _price_for(model or "")
    if price is None:
        return 0.0, False
    p_in, p_cached, p_out = price
    uncached = max(0, input_tokens - cached_tokens)
    return (uncached * p_in + cached_tokens * p_cached + output_tokens * p_out) / 1_000_000, True


def _as_uuid(value):
    if value is None or isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except ValueError:
        return None


def _usage_numbers(usage) -> tuple[int, int, int, int]:
    """(input, cached input, output, reasoning) from an OpenAI usage object."""
    if usage is None:
        return 0, 0, 0, 0
    inp = getattr(usage, "prompt_tokens", None) or getattr(usage, "total_tokens", 0) or 0
    out = getattr(usage, "completion_tokens", 0) or 0
    cached = 0
    details = getattr(usage, "prompt_tokens_details", None)
    if details is not None:
        cached = getattr(details, "cached_tokens", 0) or 0
    reasoning = 0
    out_details = getattr(usage, "completion_tokens_details", None)
    if out_details is not None:
        reasoning = getattr(out_details, "reasoning_tokens", 0) or 0
    return int(inp), int(cached), int(out), int(reasoning)


async def record(task: str, model: str, usage) -> None:
    """Writes one ai_usage_log row. Never raises."""
    try:
        from app.db.session import AsyncSessionLocal
        from app.models.ai_usage_log import AIUsageLog

        inp, cached, out, reasoning = _usage_numbers(usage)
        usd, priced = cost_usd(model, inp, cached, out)
        ctx = _ctx.get()
        async with AsyncSessionLocal() as db:
            db.add(AIUsageLog(
                task=task[:40],
                model=(model or "")[:100],
                input_tokens=inp,
                cached_input_tokens=cached,
                output_tokens=out,
                reasoning_tokens=reasoning,
                cost_usd=usd,
                priced=priced,
                job_id=_as_uuid(ctx.get("job_id")),
                candidate_id=_as_uuid(ctx.get("candidate_id")),
            ))
            await db.commit()
    except Exception:
        logger.warning("Could not record AI usage for %s/%s", task, model, exc_info=True)

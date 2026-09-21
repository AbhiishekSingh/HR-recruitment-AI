from app.config import settings
from app.services.llm.base import LLMProvider
from app.services.llm.gpt5_provider import GPT5Provider


def get_llm_provider() -> LLMProvider:
    """Swap point: change settings.llm_provider and add a branch here to use a
    different reasoning model without touching any calling code."""
    if settings.llm_provider == "gpt5":
        return GPT5Provider()
    raise ValueError(f"Unknown LLM provider: {settings.llm_provider}")

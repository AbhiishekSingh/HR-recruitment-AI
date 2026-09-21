from app.config import settings
from app.services.embeddings.base import EmbeddingProvider
from app.services.embeddings.openai_provider import OpenAIEmbeddingProvider


def get_embedding_provider() -> EmbeddingProvider:
    """Swap point: change settings.embedding_provider and add a branch here.
    NOTE: changing providers also changes vector dimensions (see
    models/candidate_embedding.py EMBEDDING_DIM) — re-embedding the whole pool
    and a migration are required, not just a config change."""
    if settings.embedding_provider == "openai":
        return OpenAIEmbeddingProvider()
    raise ValueError(f"Unknown embedding provider: {settings.embedding_provider}")

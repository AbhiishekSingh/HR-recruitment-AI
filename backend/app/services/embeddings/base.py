from abc import ABC, abstractmethod


class EmbeddingProvider(ABC):
    """Abstraction so the embedding model can be swapped (OpenAI / Voyage / Cohere /
    self-hosted BGE) without touching ingestion or matching logic elsewhere."""

    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError

    @property
    @abstractmethod
    def model_version(self) -> str:
        raise NotImplementedError

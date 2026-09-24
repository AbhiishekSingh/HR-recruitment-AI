import openai
from openai import AsyncOpenAI
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import settings
from app.services.embeddings.base import EmbeddingProvider

REQUEST_TIMEOUT_SECONDS = 60

# Same reasoning as gpt5_provider.py: only retry errors that can plausibly
# succeed on a second attempt.
RETRYABLE_ERRORS = (
    openai.RateLimitError,
    openai.APIConnectionError,
    openai.APITimeoutError,
    openai.InternalServerError,
)


class OpenAIEmbeddingProvider(EmbeddingProvider):
    def __init__(self):
        if not settings.embedding_api_key:
            raise RuntimeError(
                "EMBEDDING_API_KEY is not set -- resume/JD embedding cannot "
                "run without it. Set it in the backend's .env."
            )
        self.client = AsyncOpenAI(api_key=settings.embedding_api_key, timeout=REQUEST_TIMEOUT_SECONDS)
        self.model = settings.embedding_model_name

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=20),
        retry=retry_if_exception_type(RETRYABLE_ERRORS),
        reraise=True,
    )
    async def embed(self, texts: list[str]) -> list[list[float]]:
        response = await self.client.embeddings.create(model=self.model, input=texts)
        return [item.embedding for item in response.data]

    @property
    def model_version(self) -> str:
        return self.model

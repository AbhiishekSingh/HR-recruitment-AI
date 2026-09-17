import json

from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings
from app.services.llm.base import LLMProvider
from app.services.llm.prompts.jd_extraction import build_jd_extraction_prompt
from app.services.llm.prompts.resume_extraction import build_resume_extraction_prompt
from app.services.llm.prompts.candidate_scoring import build_scoring_prompt


class GPT5Provider(LLMProvider):
    def __init__(self):
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
        self.model = settings.llm_model_name

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=20))
    async def _call(self, messages: list[dict]) -> dict:
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0,
        )
        content = response.choices[0].message.content
        return json.loads(content)  # raises on malformed JSON -> triggers retry

    async def extract_jd(self, jd_text: str) -> dict:
        return await self._call(build_jd_extraction_prompt(jd_text))

    async def extract_resume(self, resume_text: str) -> dict:
        return await self._call(build_resume_extraction_prompt(resume_text))

    async def score_candidate(self, jd_requirements: dict, candidate_profile: dict) -> dict:
        return await self._call(build_scoring_prompt(jd_requirements, candidate_profile))

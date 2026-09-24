import json

import openai
from openai import AsyncOpenAI
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import settings
from app.services.llm.base import LLMProvider
from app.services.llm.prompts.jd_extraction import build_jd_extraction_prompt
from app.services.llm.prompts.resume_extraction import build_resume_extraction_prompt, build_resume_vision_prompt
from app.services.llm.prompts.candidate_scoring import build_scoring_prompt
from app.services.llm.validation import coerce_jd_extraction, coerce_resume_extraction, coerce_score_result

# Client-side timeout per call. gpt-5 is a reasoning model -- structured JSON
# extraction over a full resume (and especially the vision-extraction path
# with multiple page images) can genuinely take well past a minute, so 60s
# was cutting off in-flight requests that would have succeeded, not just
# catching real hangs. Worse: a client-side timeout doesn't cancel the
# request on OpenAI's side, so a request that had already started generating
# gets billed even though this process never saw the response -- every
# timeout-then-retry cycle was silently paying twice (or more) for one
# resume. 180s gives real requests room to finish before that happens.
REQUEST_TIMEOUT_SECONDS = 180

# Only retry errors that can plausibly succeed on a second attempt: rate
# limits, transient connection issues, server-side 5xx, and malformed JSON in
# the response. Retrying AuthenticationError/PermissionDeniedError/
# BadRequestError is pure waste -- a bad API key or an invalid request will
# fail identically every time, so without this filter every such call was
# burning the full 3-attempt exponential backoff (~20+ seconds) before
# surfacing the real error.
RETRYABLE_ERRORS = (
    openai.RateLimitError,
    openai.APIConnectionError,
    openai.APITimeoutError,
    openai.InternalServerError,
    json.JSONDecodeError,
)


class GPT5Provider(LLMProvider):
    def __init__(self):
        if not settings.openai_api_key:
            # Fail loudly and immediately at construction time (e.g. when a
            # Celery task first calls get_llm_provider()) rather than a
            # confusing 401 from the OpenAI SDK three retries deep into the
            # first real request.
            raise RuntimeError(
                "OPENAI_API_KEY is not set -- the GPT-5 matching/extraction "
                "pipeline cannot run without it. Set it in the backend's .env."
            )
        self.client = AsyncOpenAI(api_key=settings.openai_api_key, timeout=REQUEST_TIMEOUT_SECONDS)
        # Two model tiers, not one: plain field-extraction (resume/JD ->
        # structured JSON) doesn't need full gpt-5's reasoning depth, and
        # gpt-5-mini is roughly 5x cheaper on both input and output tokens
        # for work that's really just "read this and fill in this schema".
        # Scoring is kept on the full model since match-quality judgment is
        # where the extra reasoning actually earns its cost.
        self.model = settings.llm_model_name
        self.extraction_model = settings.llm_extraction_model_name

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=20),
        retry=retry_if_exception_type(RETRYABLE_ERRORS),
        reraise=True,
    )
    async def _call(
        self,
        messages: list[dict],
        model: str,
        reasoning_effort: str,
        max_output_tokens: int,
    ) -> dict:
        # No `temperature` param: GPT-5 (like the o-series reasoning models
        # before it) only accepts the API default and rejects any explicit
        # value -- including 0 -- with a 400 BadRequestError on every call.
        # Determinism for extraction/scoring comes from the prompt being
        # fully structured + response_format=json_object, not from pinning
        # temperature.
        #
        # reasoning_effort caps how much hidden "thinking" the model does
        # before writing its answer. Those reasoning tokens are billed as
        # output tokens -- the expensive side of GPT-5-family pricing --
        # but never appear in the response, so an uncapped call can spend
        # hundreds to thousands of tokens reasoning about a task as simple
        # as "extract these fields" without it showing up anywhere except
        # the bill. "minimal"/"low" is plenty for schema-shaped extraction
        # and rubric-based scoring; this is the single biggest cost lever
        # available here.
        #
        # max_completion_tokens (not the deprecated max_tokens) caps total
        # output including reasoning tokens, as a hard ceiling against any
        # one call running away regardless of effort setting.
        #
        # Both are sent via extra_body rather than as direct keyword
        # arguments. reasoning_effort is a real, supported field on
        # OpenAI's /chat/completions API, but it was only added to this
        # SDK version's (openai==1.51.0, see requirements.txt) *typed*
        # create() signature later than that -- calling it as a normal
        # kwarg raises "TypeError: unexpected keyword argument" client-side
        # before any request is even sent, regardless of what the API
        # itself supports. extra_body merges its dict straight into the
        # outgoing JSON body, bypassing the SDK's typed-argument check
        # entirely, so this works on the current pinned version with no
        # dependency upgrade required. (Upgrading `openai` in
        # requirements.txt would let these move back to plain kwargs, but
        # isn't necessary for this to work.)
        response = await self.client.chat.completions.create(
            model=model,
            messages=messages,
            response_format={"type": "json_object"},
            extra_body={
                "reasoning_effort": reasoning_effort,
                "max_completion_tokens": max_output_tokens,
            },
        )
        # A content-filtered or empty response comes back as None here, not
        # an exception -- treat it the same as malformed JSON so it goes
        # through the same retryable path instead of raising an unfiltered
        # TypeError from json.loads(None).
        content = response.choices[0].message.content or ""
        return json.loads(content)  # raises on malformed JSON -> triggers retry

    async def extract_jd(self, jd_text: str) -> dict:
        # Coerced before returning: response_format=json_object only
        # guarantees valid JSON syntax, not that every key is present or
        # correctly typed. See services/llm/validation.py.
        raw = await self._call(
            build_jd_extraction_prompt(jd_text),
            model=self.extraction_model,
            reasoning_effort="minimal",
            max_output_tokens=800,
        )
        return coerce_jd_extraction(raw)

    async def extract_resume(self, resume_text: str) -> dict:
        raw = await self._call(
            build_resume_extraction_prompt(resume_text),
            model=self.extraction_model,
            reasoning_effort="minimal",
            max_output_tokens=1200,
        )
        return coerce_resume_extraction(raw)

    async def extract_resume_from_images(self, images_b64: list[str]) -> dict:
        raw = await self._call(
            build_resume_vision_prompt(images_b64),
            model=self.extraction_model,
            reasoning_effort="minimal",
            max_output_tokens=1200,
        )
        return coerce_resume_extraction(raw)

    async def score_candidate(self, jd_requirements: dict, candidate_profile: dict) -> dict:
        # Stays on the full model with a bit more reasoning headroom than
        # extraction ("low" vs "minimal") -- this is the judgment call that
        # actually decides who gets shortlisted, so it's the one place
        # worth spending more than the bare minimum.
        raw = await self._call(
            build_scoring_prompt(jd_requirements, candidate_profile),
            model=self.model,
            reasoning_effort="low",
            max_output_tokens=600,
        )
        return coerce_score_result(raw)
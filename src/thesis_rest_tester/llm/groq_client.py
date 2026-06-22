"""Groq implementation of the provider-neutral LLM client."""

from __future__ import annotations

import os
from typing import Any

from groq import Groq

from thesis_rest_tester.domain.models import TokenUsage
from thesis_rest_tester.llm.base import LLMClient, LLMResponse


class GroqLLMClient(LLMClient):
    def __init__(
        self,
        model: str,
        default_temperature: float = 0.1,
        default_max_tokens: int = 4096,
        sdk_client: Any | None = None,
    ) -> None:
        api_key = os.getenv("GROQ_API_KEY")
        if sdk_client is None and not api_key:
            raise ValueError(
                "GROQ_API_KEY is missing. Set it in the environment or a local .env file, "
                "or use --dry-run."
            )
        self._client = (
            sdk_client if sdk_client is not None else Groq(api_key=api_key, max_retries=2)
        )
        self._model = model
        self._default_temperature = default_temperature
        self._default_max_tokens = default_max_tokens

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=self._default_temperature if temperature is None else temperature,
            max_completion_tokens=self._default_max_tokens if max_tokens is None else max_tokens,
        )
        content = response.choices[0].message.content
        if not content:
            raise RuntimeError("Groq returned an empty response")

        usage = getattr(response, "usage", None)
        token_usage = None
        if usage is not None:
            token_usage = TokenUsage(
                prompt_tokens=getattr(usage, "prompt_tokens", None),
                completion_tokens=getattr(usage, "completion_tokens", None),
                total_tokens=getattr(usage, "total_tokens", None),
            )
        return LLMResponse(
            text=content,
            token_usage=token_usage,
            model=getattr(response, "model", self._model),
        )

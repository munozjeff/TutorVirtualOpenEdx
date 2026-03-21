"""
AI provider abstraction layer.

Supports:
 - Google Gemini (default) via google-genai SDK
 - Ollama (local models)
"""
from __future__ import annotations

import logging
from typing import Protocol

from app.config import get_settings

log = logging.getLogger(__name__)
settings = get_settings()


class AIProvider(Protocol):
    async def chat(
        self,
        system_prompt: str,
        history: list[dict],
        user_message: str,
    ) -> str:
        """
        Send a chat turn and return the assistant reply.
        history = [{"role": "user"|"assistant", "content": "..."}]
        """
        ...


# ─── Gemini Provider ──────────────────────────────────────────────────────────

class GeminiProvider:
    """
    Google Gemini via the google-genai SDK.

    - Model: gemini-flash-lite-latest (configurable via GEMINI_MODEL)
    - thinking_budget=0  → disable chain-of-thought for faster responses
    - GoogleSearch tool  → enables web grounding when relevant
    - Full conversation history is sent on every turn
    - Student sessions are fully isolated (isolation_key ensures no cross-user data)
    """

    def __init__(self) -> None:
        from google import genai
        self._client = genai.Client(api_key=settings.gemini_api_key)
        self._model = settings.gemini_model
        log.info("GeminiProvider ready: model=%s", self._model)

    async def chat(
        self,
        system_prompt: str,
        history: list[dict],
        user_message: str,
    ) -> str:
        from google import genai  # noqa: F401 — needed for type resolution
        from google.genai import types

        # Build conversation contents
        # Gemini uses "model" for assistant turns (not "assistant")
        contents: list[types.Content] = []
        for msg in history:
            role = "model" if msg["role"] == "assistant" else "user"
            contents.append(
                types.Content(
                    role=role,
                    parts=[types.Part.from_text(text=msg["content"])],
                )
            )
        contents.append(
            types.Content(
                role="user",
                parts=[types.Part.from_text(text=user_message)],
            )
        )

        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
            tools=[types.Tool(googleSearch=types.GoogleSearch())],
        )

        response = await self._client.aio.models.generate_content(
            model=self._model,
            contents=contents,
            config=config,
        )

        # Collect text parts (grounding chunks may not have text)
        text = ""
        if response.candidates:
            for part in response.candidates[0].content.parts:
                if part.text:
                    text += part.text

        return text or "Lo siento, no pude generar una respuesta. Intenta de nuevo."


# ─── Ollama Provider ──────────────────────────────────────────────────────────

class OllamaProvider:
    def __init__(self) -> None:
        import ollama
        self._client = ollama.AsyncClient(host=settings.ollama_base_url)
        self._model = settings.ollama_model
        log.info("OllamaProvider ready: model=%s", self._model)

    async def chat(
        self,
        system_prompt: str,
        history: list[dict],
        user_message: str,
    ) -> str:
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history)
        messages.append({"role": "user", "content": user_message})

        response = await self._client.chat(model=self._model, messages=messages)
        return response["message"]["content"]


# ─── Factory ──────────────────────────────────────────────────────────────────

_provider: AIProvider | None = None


def get_ai_provider() -> AIProvider:
    global _provider
    if _provider is not None:
        return _provider

    provider_name = settings.ai_provider.lower()
    if provider_name == "gemini":
        _provider = GeminiProvider()
    elif provider_name == "ollama":
        _provider = OllamaProvider()
    else:
        raise ValueError(f"Unknown AI provider: {provider_name!r}. Use 'gemini' or 'ollama'.")

    return _provider

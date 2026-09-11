"""Optional engine for OpenAI-compatible chat APIs (OpenAI itself, or any local server
that speaks the same protocol, e.g. LM Studio / vLLM's OpenAI-compatible endpoint).
Requires `pip install relay-oss[openai]`."""

from .base import Engine, CompletionResult


class OpenAIEngine(Engine):
    name = "openai"

    def __init__(self, model: str, api_key: str = "", base_url: str = None):
        try:
            from openai import OpenAI
        except ImportError as e:
            raise RuntimeError(
                "The 'openai' package is required for this engine. "
                "Install with: pip install relay-oss[openai]"
            ) from e
        # A base_url lets you point this at any OpenAI-compatible local server
        # (LM Studio, vLLM, etc.) and use it as a free engine too, with no API key.
        self._client = OpenAI(api_key=api_key or "not-needed", base_url=base_url)
        self.model = model

    def complete(self, system: str, prompt: str, max_tokens: int = 4096) -> CompletionResult:
        resp = self._client.chat.completions.create(
            model=self.model,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        )
        text = resp.choices[0].message.content or ""
        usage = getattr(resp, "usage", None)
        return CompletionResult(
            text=text,
            input_tokens=getattr(usage, "prompt_tokens", 0) if usage else 0,
            output_tokens=getattr(usage, "completion_tokens", 0) if usage else 0,
            model=self.model,
        )

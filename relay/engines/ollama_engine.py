"""Free, local engine backed by Ollama (https://ollama.com). This is Relay's default —
running the builder tier here means the bulk of your tokens never leave your machine
and never cost a cent."""

import requests

from .base import Engine, CompletionResult


class OllamaEngine(Engine):
    name = "ollama"

    def __init__(self, model: str, base_url: str = "http://localhost:11434", timeout: int = 300):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def complete(self, system: str, prompt: str, max_tokens: int = 4096) -> CompletionResult:
        try:
            resp = requests.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": prompt},
                    ],
                    "stream": False,
                    "options": {"num_predict": max_tokens},
                },
                timeout=self.timeout,
            )
        except requests.exceptions.ConnectionError as e:
            raise RuntimeError(
                f"Could not reach Ollama at {self.base_url}. Is it running? "
                f"Install from https://ollama.com and run `ollama serve` "
                f"(or `ollama pull {self.model}` first if you haven't)."
            ) from e
        resp.raise_for_status()
        data = resp.json()
        text = data.get("message", {}).get("content", "")
        return CompletionResult(
            text=text,
            input_tokens=data.get("prompt_eval_count", 0),
            output_tokens=data.get("eval_count", 0),
            model=self.model,
        )

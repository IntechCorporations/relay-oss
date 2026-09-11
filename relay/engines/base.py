"""Common interface every model engine (Ollama, Anthropic, OpenAI, mock) implements."""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class CompletionResult:
    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""


class Engine(ABC):
    name: str = "base"
    model: str = ""

    @abstractmethod
    def complete(self, system: str, prompt: str, max_tokens: int = 4096) -> CompletionResult:
        """Send one system+user prompt to the model and return its text plus token usage."""
        raise NotImplementedError

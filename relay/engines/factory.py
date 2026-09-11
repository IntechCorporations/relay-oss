import os

from .base import Engine


class EngineConfigError(Exception):
    pass


def build_engine(tier_cfg: dict) -> Engine:
    provider = tier_cfg.get("provider", "ollama")

    if provider == "ollama":
        from .ollama_engine import OllamaEngine

        return OllamaEngine(
            model=tier_cfg["model"],
            base_url=tier_cfg.get("base_url", "http://localhost:11434"),
        )

    if provider == "anthropic":
        from .anthropic_engine import AnthropicEngine

        api_key = tier_cfg.get("api_key") or os.environ.get("ANTHROPIC_API_KEY")
        return AnthropicEngine(model=tier_cfg["model"], api_key=api_key)

    if provider == "openai":
        from .openai_engine import OpenAIEngine

        api_key = tier_cfg.get("api_key") or os.environ.get("OPENAI_API_KEY", "")
        return OpenAIEngine(
            model=tier_cfg["model"],
            api_key=api_key,
            base_url=tier_cfg.get("base_url"),
        )

    if provider == "mock":
        from .mock_engine import MockEngine

        return MockEngine(model=tier_cfg.get("model", "mock-1"))

    raise EngineConfigError(
        f"Unknown provider '{provider}'. Expected one of: ollama, anthropic, openai, mock."
    )

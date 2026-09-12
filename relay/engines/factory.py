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
        workspace_id = tier_cfg.get("workspace_id") or os.environ.get("ANTHROPIC_WORKSPACE_ID")
        return AnthropicEngine(model=tier_cfg["model"], api_key=api_key, workspace_id=workspace_id)

    if provider == "openai":
        from .openai_engine import OpenAIEngine

        api_key = tier_cfg.get("api_key") or os.environ.get("OPENAI_API_KEY", "")
        return OpenAIEngine(
            model=tier_cfg["model"],
            api_key=api_key,
            base_url=tier_cfg.get("base_url"),
        )

    if provider == "openai_compatible":
        # Any server that speaks the OpenAI chat-completions protocol: Groq, Together,
        # Fireworks, vLLM, LM Studio's local server, etc. Distinguished from "openai"
        # only so the UI can show a friendly platform name/preset base_url while both
        # ultimately share the same client.
        from .openai_engine import OpenAIEngine

        api_key = tier_cfg.get("api_key") or os.environ.get("OPENAI_API_KEY", "")
        base_url = tier_cfg.get("base_url")
        if not base_url:
            raise EngineConfigError(
                "openai_compatible provider requires a base_url (e.g. Groq's "
                "https://api.groq.com/openai/v1, or LM Studio's http://localhost:1234/v1)."
            )
        return OpenAIEngine(model=tier_cfg["model"], api_key=api_key, base_url=base_url)

    if provider == "gemini":
        from .gemini_engine import GeminiEngine

        api_key = (
            tier_cfg.get("api_key")
            or os.environ.get("GEMINI_API_KEY")
            or os.environ.get("GOOGLE_API_KEY", "")
        )
        return GeminiEngine(model=tier_cfg["model"], api_key=api_key)

    if provider == "mock":
        from .mock_engine import MockEngine

        return MockEngine(model=tier_cfg.get("model", "mock-1"))

    raise EngineConfigError(
        f"Unknown provider '{provider}'. Expected one of: ollama, anthropic, openai, "
        f"openai_compatible, gemini, mock."
    )


# Well-known OpenAI-compatible platforms, so the UI can offer them as one-click presets
# instead of making you look up base URLs. Feel free to add more — anything that speaks
# the OpenAI chat-completions protocol works with provider: openai_compatible.
KNOWN_PLATFORMS = {
    "groq": {"label": "Groq", "base_url": "https://api.groq.com/openai/v1", "needs_key": True},
    "xai": {"label": "xAI (Grok)", "base_url": "https://api.x.ai/v1", "needs_key": True},
    "together": {"label": "Together AI", "base_url": "https://api.together.xyz/v1", "needs_key": True},
    "fireworks": {"label": "Fireworks AI", "base_url": "https://api.fireworks.ai/inference/v1", "needs_key": True},
    "lmstudio": {"label": "LM Studio (local)", "base_url": "http://localhost:1234/v1", "needs_key": False},
    "vllm": {"label": "vLLM (local)", "base_url": "http://localhost:8000/v1", "needs_key": False},
}

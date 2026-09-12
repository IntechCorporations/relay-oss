"""Optional engine for tiers where you want to spend a frontier Claude model's tokens
(planning / verification are the recommended spots — they're a small share of total
tokens). Requires `pip install relay-oss[anthropic]` and an ANTHROPIC_API_KEY."""

from .base import Engine, CompletionResult


class AnthropicEngine(Engine):
    name = "anthropic"

    def __init__(self, model: str, api_key: str, workspace_id: str | None = None):
        try:
            import anthropic
        except ImportError as e:
            raise RuntimeError(
                "The 'anthropic' package is required for this engine. "
                "Install with: pip install relay-oss[anthropic]"
            ) from e
        if not api_key:
            raise RuntimeError(
                "No Anthropic API key found. Set ANTHROPIC_API_KEY or add "
                "api_key to this tier's config."
            )
        self.model = model
        # Some Console-generated API keys are scoped to a specific workspace rather
        # than the whole organization. Those keys return a 400 invalid_request_error
        # ("This API key is not scoped to a workspace...") unless every request also
        # carries the anthropic-workspace-id header naming that workspace. Find your
        # workspace ID at console.anthropic.com under Settings -> Workspaces.
        extra_headers = {"anthropic-workspace-id": workspace_id} if workspace_id else None
        self._client = anthropic.Anthropic(api_key=api_key, default_headers=extra_headers)

    def complete(self, system: str, prompt: str, max_tokens: int = 4096) -> CompletionResult:
        resp = self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(getattr(block, "text", "") for block in resp.content)
        return CompletionResult(
            text=text,
            input_tokens=resp.usage.input_tokens,
            output_tokens=resp.usage.output_tokens,
            model=self.model,
        )

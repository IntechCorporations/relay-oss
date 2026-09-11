"""Optional engine for Google's Gemini API. A reasonable "strong but cheaper than
Claude/GPT-4-class" option to point the planner/verifier tiers at if you want a hosted
model in the loop without the top-tier price. Requires `pip install relay-oss[gemini]`
and a GEMINI_API_KEY (or GOOGLE_API_KEY)."""

from .base import Engine, CompletionResult


class GeminiEngine(Engine):
    name = "gemini"

    def __init__(self, model: str, api_key: str):
        try:
            import google.generativeai as genai
        except ImportError as e:
            raise RuntimeError(
                "The 'google-generativeai' package is required for this engine. "
                "Install with: pip install relay-oss[gemini]"
            ) from e
        if not api_key:
            raise RuntimeError(
                "No Gemini API key found. Set GEMINI_API_KEY (or GOOGLE_API_KEY) or "
                "add api_key to this tier's config."
            )
        genai.configure(api_key=api_key)
        self.model = model
        self._genai = genai
        self._client = genai.GenerativeModel(model)

    def complete(self, system: str, prompt: str, max_tokens: int = 4096) -> CompletionResult:
        client = self._genai.GenerativeModel(self.model, system_instruction=system)
        resp = client.generate_content(
            prompt,
            generation_config=self._genai.types.GenerationConfig(max_output_tokens=max_tokens),
        )
        text = getattr(resp, "text", "") or ""
        usage = getattr(resp, "usage_metadata", None)
        return CompletionResult(
            text=text,
            input_tokens=getattr(usage, "prompt_token_count", 0) if usage else 0,
            output_tokens=getattr(usage, "candidates_token_count", 0) if usage else 0,
            model=self.model,
        )

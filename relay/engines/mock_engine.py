"""A zero-setup engine used by `relay run --demo` and by the test suite. It returns
deterministic, canned JSON that exercises the full planner -> builder -> verifier
pipeline without needing Ollama, an API key, or any network access at all."""

import json

from .base import Engine, CompletionResult


class MockEngine(Engine):
    name = "mock"

    def __init__(self, model: str = "mock-1"):
        self.model = model

    def complete(self, system: str, prompt: str, max_tokens: int = 4096) -> CompletionResult:
        if "PLANNING tier" in system:
            text = json.dumps(
                {
                    "summary": "Demo plan: create hello.txt with a friendly greeting.",
                    "steps": [
                        {
                            "id": "1",
                            "description": "Create hello.txt with a friendly greeting",
                            "target_files": ["hello.txt"],
                        }
                    ],
                }
            )
        elif "BUILDING tier" in system:
            text = json.dumps(
                {
                    "files": {"hello.txt": "Hello from Relay!\n"},
                    "shell_commands": [],
                    "notes": "Created hello.txt",
                }
            )
        else:  # verifier
            text = json.dumps({"passed": True, "issues": [], "suggestions": []})
        return CompletionResult(text=text, input_tokens=120, output_tokens=40, model=self.model)

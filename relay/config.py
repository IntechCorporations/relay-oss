"""Config loading for Relay. Defaults to an all-Ollama (fully free, fully local)
setup. Override ~/.relay/config.yaml to mix in Anthropic/OpenAI for the planner and
verifier tiers, which is Relay's recommended setup: those tiers are a small slice of
total tokens, so spending a stronger model there while the free local model does the
bulk of the building keeps real-world cost close to zero."""

import copy
from pathlib import Path

import yaml

DEFAULT_CONFIG_PATH = Path.home() / ".relay" / "config.yaml"

DEFAULT_CONFIG = {
    # Manual per-tier assignment. This is what's used when router.enabled is False —
    # you're picking exactly which engine handles planning/building/verification.
    "engines": {
        "planner": {
            "provider": "ollama",
            "model": "llama3.1:8b",
            "base_url": "http://localhost:11434",
        },
        "builder": {
            "provider": "ollama",
            "model": "qwen2.5-coder:7b",
            "base_url": "http://localhost:11434",
        },
        "verifier": {
            "provider": "ollama",
            "model": "llama3.1:8b",
            "base_url": "http://localhost:11434",
        },
    },
    # Auto-router: when enabled, the BUILDER tier's steps are routed per-step to the
    # cheapest rung ("cheap" / "mid" / "strong") that looks capable of that step,
    # instead of always using engines.builder. Planner/verifier stay manually assigned
    # above, since they're already a small slice of total tokens.
    "router": {
        "enabled": False,
        "escalate_on_verify_fail": True,
        "max_tokens_per_run": None,
        "thresholds": {"mid": 0.35, "strong": 0.7},
        "rungs": {
            "cheap": {
                "provider": "ollama",
                "model": "qwen2.5-coder:7b",
                "base_url": "http://localhost:11434",
            },
            "mid": None,
            "strong": None,
        },
    },
    # Saved provider connections, managed from the dashboard's Settings screen. Each
    # entry is reusable across engines/rungs so you configure an API key once. This
    # list is metadata for the UI; engines/router entries above are what's actually
    # used at run time (the UI keeps them in sync when you assign a connection).
    "connections": [],
    "safety": {
        "require_shell_confirmation": True,
        "allowed_shell_commands": [
            "git", "npm", "pip", "pip3", "pytest", "python", "python3",
            "yarn", "pnpm", "node", "ls", "cat", "go", "cargo",
        ],
        "max_file_bytes": 200_000,
    },
    "verification": {
        "max_fix_retries": 2,
    },
    "desktop_control": {
        "enabled": False,
        "kill_switch_hotkey": "ctrl+shift+x",
        "action_delay_seconds": 0.15,
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
    return base


def load_config(path=None) -> dict:
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    resolved = Path(path) if path else DEFAULT_CONFIG_PATH
    if resolved.exists():
        with open(resolved) as f:
            user_cfg = yaml.safe_load(f) or {}
        _deep_merge(cfg, user_cfg)
    return cfg


def init_config(path=None) -> Path:
    resolved = Path(path) if path else DEFAULT_CONFIG_PATH
    resolved.parent.mkdir(parents=True, exist_ok=True)
    if not resolved.exists():
        with open(resolved, "w") as f:
            yaml.safe_dump(DEFAULT_CONFIG, f, sort_keys=False)
    return resolved

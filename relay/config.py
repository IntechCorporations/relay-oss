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

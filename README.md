# Relay

Relay is a free, local, multi-tier AI coding orchestrator. It's a from-scratch,
open build inspired by paid tools like Savr — same core idea, no subscription,
no account, and your code stays on your machine unless you deliberately point a
tier at a cloud model.

## How it works

Relay splits a coding task across three tiers instead of throwing one model at
the whole thing:

1. **Planner** — reads the task and your project's file tree and writes a
   step-by-step plan (what changes, in which files). It doesn't write any code.
2. **Builder** — executes the plan one step at a time: writes the actual file
   contents and can request shell commands (installing a dependency, running
   tests). This is where the bulk of the tokens go, so it's the tier meant to
   run on a free local model.
3. **Verifier** — reviews the full diff against the original task, flags
   problems, and can send it back to the builder for a bounded number of
   fix-up passes.

Which model powers each tier is entirely up to your config — see
`examples/config.free.yaml` (100% local Ollama, $0) and
`examples/config.hybrid.yaml` (a stronger model for planning/verification,
                               free Ollama for the actual building — this is the closest match to how paid
                               tools like Savr use tiering to control cost, minus the subscription).

## Install

```bash
git clone <this repo, or unzip what you were given>
cd relay-oss
pip install -e .
```

Optional extras:

```bash
pip install -e ".[anthropic]"   # to use Claude for a tier
pip install -e ".[openai]"      # to use OpenAI (or any OpenAI-compatible local server)
pip install -e ".[desktop]"     # for the experimental screen-control layer
pip install -e ".[postgres]"    # for the Postgres connector
```

## Quickstart

Try it with zero setup, no models required, using the built-in mock engine:

```bash
mkdir /tmp/demo && relay run --task "Add a greeting file" --project /tmp/demo --demo --yes
cat /tmp/demo/hello.txt
```

For a real run:

```bash
# 1. Install Ollama: https://ollama.com
ollama pull llama3.1:8b
ollama pull qwen2.5-coder:7b

# 2. Write a default config (100% local, 100% free)
relay init

# 3. Point it at a real project
relay run --task "Add input validation to the signup form" --project ~/code/my-app
```

Prefer a browser? `relay dashboard` starts a local web UI at
`http://127.0.0.1:8765` with a live log stream and the same plan/build/verify
breakdown.

## What's real vs. what's a stub

Built, tested, and working (see `tests/`, all passing):

- The full plan -> build -> verify pipeline, with a retry loop when verification fails
- Ollama, Anthropic, and OpenAI-compatible engines (mix and match per tier)
- Filesystem connector (bounded project tree + read/write)
- Shell connector, gated by an allowlist and per-command confirmation
- HTTP webhook connector
- CLI (`relay init` / `relay run` / `relay dashboard`) and a local web dashboard

Included but experimental / opt-in, and **not exercised by the test suite**
because it needs a real display:

- `relay/desktop_control.py` — screen click/type/scroll via `pyautogui`, with a
  hotkey kill switch (`keyboard`) checked before every single action, plus
  pyautogui's own screen-corner fail-safe as a second abort path
- `relay/overlay.py` — a small on-screen marker showing where the desktop
  control layer is about to click

Test these two on your own machine in a throwaway window before trusting them
with anything real — that's true of any tool that can move your mouse and
type on your behalf, this one included.

Also included but minimal: `relay/connectors/postgres.py`, a thin query
connector you can wire into a step manually — Relay doesn't yet auto-decide
when a task needs a database, it just gives you the hook.

## Safety notes

- Shell commands are blocked unless their binary is in `safety.allowed_shell_commands`
  in your config, and by default each one asks for confirmation
  (`relay run --yes` skips confirmation — only use that once you trust the plan).
- The builder tier writes full file contents, not raw diffs applied blindly —
  every write goes through `filesystem.write_file`, and Relay keeps a unified
  diff of every change in the run's report so you can review what happened.
- Desktop control defaults to `enabled: false` in config and is a separate
  install extra — it does nothing until you deliberately turn it on.

## Project layout

```
relay/
  cli.py                 entry point: init / run / dashboard
  config.py               config loading + defaults (all-Ollama out of the box)
  orchestrator.py          the plan -> build -> verify pipeline
  engines/                 ollama / anthropic / openai / mock model backends
  connectors/              filesystem / shell / webhook / postgres
  desktop_control.py       experimental screen control + kill switch
  overlay.py                experimental on-screen cursor marker
  web/                     FastAPI dashboard + single-file HTML/JS frontend
tests/                     pytest suite (mock-engine based, no network needed)
examples/                  ready-to-copy config files
```

## License

MIT — it's yours, do what you want with it.

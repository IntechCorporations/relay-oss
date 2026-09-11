import sys

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from . import config as config_mod
from .engines.factory import build_engine, EngineConfigError
from .orchestrator import Orchestrator

console = Console()


@click.group()
def main():
    """Relay: a free, local, multi-tier AI coding orchestrator."""


@main.command()
@click.option("--path", default=None, help="Where to write the config file")
def init(path):
    """Create a default ~/.relay/config.yaml"""
    p = config_mod.init_config(path)
    console.print(f"[green]Wrote default config to {p}[/green]")
    console.print(
        "It's set up to run entirely on free local Ollama models. Edit it to add an "
        "Anthropic/OpenAI API key for the planner/verifier tiers if you want a "
        "stronger model reviewing the work — see the README for the recommended hybrid setup."
    )


@main.command()
@click.option("--task", required=True, help="Natural language description of what to build/change")
@click.option("--project", default=".", help="Path to the project directory to work in")
@click.option("--config", "config_path", default=None, help="Path to config.yaml")
@click.option("--yes", is_flag=True, help="Auto-approve shell commands (skip confirmation prompts)")
@click.option("--demo", is_flag=True, help="Use the built-in mock engine — no setup, no models required")
def run(task, project, config_path, yes, demo):
    """Run the plan -> build -> verify pipeline against a project."""
    cfg = config_mod.load_config(config_path)
    if demo:
        for tier in cfg["engines"]:
            cfg["engines"][tier] = {"provider": "mock"}

    try:
        planner = build_engine(cfg["engines"]["planner"])
        builder = build_engine(cfg["engines"]["builder"])
        verifier = build_engine(cfg["engines"]["verifier"])
    except (EngineConfigError, RuntimeError) as e:
        console.print(f"[red]Engine setup failed:[/red] {e}")
        sys.exit(1)

    def confirm_shell(cmd):
        if yes or not cfg["safety"].get("require_shell_confirmation", True):
            return True
        return click.confirm(f"Run shell command: {cmd!r}?", default=False)

    orch = Orchestrator(
        planner,
        builder,
        verifier,
        safety_cfg=cfg["safety"],
        verification_cfg=cfg["verification"],
        project_dir=project,
        logger=console.print,
        confirm_shell=confirm_shell,
    )
    console.print(Panel.fit(f"[bold]Task:[/bold] {task}\n[bold]Project:[/bold] {project}", title="Relay"))
    try:
        report = orch.run(task)
    except Exception as e:
        console.print(f"[red]Run failed:[/red] {e}")
        sys.exit(1)
    _print_report(report)


def _print_report(report):
    console.print(Panel.fit(report["plan"].get("summary", ""), title="Plan summary"))
    for r in report["build_results"]:
        step = r["step"]
        console.print(f"[bold cyan]Step {step.get('id')}[/bold cyan]: {step.get('description')}")
        for f in r["diffs"]:
            console.print(f"  wrote {f}")
        for sr in r["shell_results"]:
            outcome = sr.get("error") or sr.get("returncode")
            console.print(f"  ran: {sr.get('cmd')} -> {outcome}")

    v = report["verify_result"]
    status = "[green]PASSED[/green]" if v.get("passed") else "[red]FAILED[/red]"
    issues = v.get("issues") or ["none"]
    console.print(Panel.fit(f"Verification: {status}\nIssues: {issues}", title="Verifier"))

    table = Table(title="Token usage by tier")
    table.add_column("Tier")
    table.add_column("Model")
    table.add_column("Input", justify="right")
    table.add_column("Output", justify="right")
    for tier, stats in report["token_totals"].items():
        table.add_row(tier, stats["model"], str(stats["input"]), str(stats["output"]))
    console.print(table)
    console.print(f"[bold]Total tokens:[/bold] {report['grand_total_tokens']}")


@main.command()
@click.option("--host", default="127.0.0.1")
@click.option("--port", default=8765)
def dashboard(host, port):
    """Launch the local web dashboard at http://host:port"""
    import uvicorn

    from .web.app import app

    console.print(f"[green]Relay dashboard running at http://{host}:{port}[/green]")
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()

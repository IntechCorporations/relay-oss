"""The core of Relay: a three-tier plan -> build -> verify pipeline.

  planner   (small share of tokens) reads the task + project tree and decides
            WHAT needs to change and WHERE, without writing any code.
  builder   (bulk of tokens, meant to run on a free local model) writes the
            actual file contents for each step and can request shell commands.
  verifier  (small share of tokens) reviews the full diff and can send it back
            to the builder for a bounded number of fix-up passes.

This mirrors the "route most tokens to a cheap model, spend the expensive model
sparingly on planning and review" idea that makes tools like this affordable —
except here the split is yours to configure, down to $0 if every tier points at
a local Ollama model.
"""

import difflib
import json
import re
from dataclasses import dataclass, field

from .connectors import filesystem, shell

PLANNER_SYSTEM = """You are the PLANNING tier of Relay, a local multi-model coding orchestrator.
Given a coding task and a project file tree, produce a step-by-step implementation plan.
Do NOT write any code. Only decide WHAT needs to change and WHERE.
Respond with a single JSON object only, no prose, no markdown fences, matching this schema:
{
  "summary": "<one paragraph summary of the approach>",
  "steps": [
    {"id": "1", "description": "<what to do>", "target_files": ["relative/path.ext", ...]}
  ]
}
Keep steps small and independently buildable. Prefer editing existing files over inventing new architecture.
"""

BUILDER_SYSTEM = """You are the BUILDING tier of Relay, a local multi-model coding orchestrator.
You will be given one implementation step and the CURRENT full contents of its target files
(an empty string means the file does not exist yet and should be created).
Write the COMPLETE new contents for every file you touch. Do not use diffs or ellipses — always
output the full file content. You may also request shell commands to run (e.g. installing a
dependency), but only when clearly necessary.
Respond with a single JSON object only, no prose, no markdown fences, matching this schema:
{
  "files": {"relative/path.ext": "<complete new file content>"},
  "shell_commands": ["<command>", ...],
  "notes": "<short note on what you changed and why>"
}
"""

VERIFIER_SYSTEM = """You are the VERIFICATION tier of Relay, a local multi-model coding orchestrator.
You will be given the original task and a unified diff of all changes made by the builder tier.
Carefully review the diff for correctness, missing pieces, obvious bugs, and whether it actually
accomplishes the task.
Respond with a single JSON object only, no prose, no markdown fences, matching this schema:
{
  "passed": true or false,
  "issues": ["<specific problem>", ...],
  "suggestions": ["<specific fix tied to a file or step>", ...]
}
"""


def _extract_json(text: str) -> dict:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    else:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end != -1 and end > start:
            text = text[start:end + 1]
    return json.loads(text)


@dataclass
class TokenLedger:
    entries: list = field(default_factory=list)

    def record(self, tier: str, result) -> None:
        self.entries.append((tier, result.input_tokens, result.output_tokens, result.model))

    def totals(self) -> dict:
        by_tier = {}
        for tier, i, o, model in self.entries:
            t = by_tier.setdefault(tier, {"input": 0, "output": 0, "model": model})
            t["input"] += i
            t["output"] += o
        return by_tier

    def grand_total(self) -> int:
        return sum(i + o for _, i, o, _ in self.entries)


class Orchestrator:
    def __init__(
        self,
        planner,
        builder,
        verifier,
        safety_cfg: dict,
        verification_cfg: dict,
        project_dir: str,
        logger=print,
        confirm_shell=None,
    ):
        self.planner = planner
        self.builder = builder
        self.verifier = verifier
        self.safety_cfg = safety_cfg
        self.verification_cfg = verification_cfg
        self.project_dir = project_dir
        self.log = logger
        self.confirm_shell = confirm_shell
        self.ledger = TokenLedger()

    def _gather_context(self) -> str:
        return "\n".join(filesystem.list_tree(self.project_dir))

    def plan(self, task: str) -> dict:
        prompt = f"Task:\n{task}\n\nProject file tree:\n{self._gather_context()}\n"
        result = self.planner.complete(system=PLANNER_SYSTEM, prompt=prompt)
        self.ledger.record("planner", result)
        return _extract_json(result.text)

    def build_step(self, task: str, step: dict) -> dict:
        max_bytes = self.safety_cfg.get("max_file_bytes", 200_000)
        current = {
            rel: filesystem.read_file(self.project_dir, rel, max_bytes)
            for rel in step.get("target_files", [])
        }
        prompt = (
            f"Task:\n{task}\n\nStep {step.get('id')}: {step.get('description')}\n\n"
            f"Current contents of target files (JSON):\n{json.dumps(current)}\n"
        )
        result = self.builder.complete(system=BUILDER_SYSTEM, prompt=prompt)
        self.ledger.record("builder", result)
        parsed = _extract_json(result.text)

        diffs = {}
        for rel, new_content in parsed.get("files", {}).items():
            old_content = current.get(rel, filesystem.read_file(self.project_dir, rel))
            filesystem.write_file(self.project_dir, rel, new_content)
            diffs[rel] = "\n".join(
                difflib.unified_diff(
                    old_content.splitlines(),
                    new_content.splitlines(),
                    fromfile=f"a/{rel}",
                    tofile=f"b/{rel}",
                    lineterm="",
                )
            )

        shell_results = []
        for cmd in parsed.get("shell_commands", []):
            try:
                shell_results.append(
                    shell.run_command(
                        cmd,
                        cwd=self.project_dir,
                        allowed_commands=self.safety_cfg.get("allowed_shell_commands", []),
                        confirm_fn=self.confirm_shell,
                    )
                )
            except shell.ShellPermissionError as e:
                shell_results.append({"cmd": cmd, "error": str(e)})

        return {
            "step": step,
            "diffs": diffs,
            "shell_results": shell_results,
            "notes": parsed.get("notes", ""),
        }

    def verify(self, task: str, full_diff: str) -> dict:
        prompt = f"Task:\n{task}\n\nFull diff of all changes:\n{full_diff or '(no changes were made)'}\n"
        result = self.verifier.complete(system=VERIFIER_SYSTEM, prompt=prompt)
        self.ledger.record("verifier", result)
        return _extract_json(result.text)

    def run(self, task: str) -> dict:
        self.log("[planner] analyzing task and project...")
        plan = self.plan(task)
        self.log(f"[planner] {len(plan.get('steps', []))} step(s) planned")

        build_results = []
        for step in plan.get("steps", []):
            self.log(f"[builder] step {step.get('id')}: {step.get('description')}")
            build_results.append(self.build_step(task, step))

        def _full_diff():
            return "\n\n".join(d for r in build_results for d in r["diffs"].values() if d)

        self.log("[verifier] reviewing full diff...")
        verify_result = self.verify(task, _full_diff())

        retries = self.verification_cfg.get("max_fix_retries", 2)
        while not verify_result.get("passed", True) and retries > 0:
            self.log(f"[verifier] issues found, sending back to builder ({retries} left)")
            fix_step = {
                "id": "fix",
                "description": "Fix the following issues found during verification: "
                + "; ".join(verify_result.get("issues", [])),
                "target_files": sorted({f for r in build_results for f in r["diffs"].keys()}),
            }
            build_results.append(self.build_step(task, fix_step))
            verify_result = self.verify(task, _full_diff())
            retries -= 1

        return {
            "task": task,
            "plan": plan,
            "build_results": build_results,
            "verify_result": verify_result,
            "token_totals": self.ledger.totals(),
            "grand_total_tokens": self.ledger.grand_total(),
        }

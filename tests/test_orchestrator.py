import os
import tempfile

from relay.engines.mock_engine import MockEngine
from relay.orchestrator import Orchestrator


def test_full_pipeline_creates_file_and_passes_verification():
    with tempfile.TemporaryDirectory() as tmp:
        orch = Orchestrator(
            planner=MockEngine(),
            builder=MockEngine(),
            verifier=MockEngine(),
            safety_cfg={"allowed_shell_commands": [], "max_file_bytes": 200_000},
            verification_cfg={"max_fix_retries": 1},
            project_dir=tmp,
            logger=lambda *_: None,
            confirm_shell=lambda cmd: True,
        )
        report = orch.run("Add a greeting file")

        assert report["verify_result"]["passed"] is True
        out_path = os.path.join(tmp, "hello.txt")
        assert os.path.exists(out_path)
        with open(out_path) as f:
            assert "Hello from Relay" in f.read()

        assert report["grand_total_tokens"] > 0
        assert set(report["token_totals"].keys()) == {"planner", "builder", "verifier"}


def test_report_structure():
    with tempfile.TemporaryDirectory() as tmp:
        orch = Orchestrator(
            planner=MockEngine(),
            builder=MockEngine(),
            verifier=MockEngine(),
            safety_cfg={"allowed_shell_commands": []},
            verification_cfg={"max_fix_retries": 0},
            project_dir=tmp,
            logger=lambda *_: None,
        )
        report = orch.run("Do a thing")
        assert "plan" in report and "steps" in report["plan"]
        assert len(report["build_results"]) == 1
        step_result = report["build_results"][0]
        assert "hello.txt" in step_result["diffs"]

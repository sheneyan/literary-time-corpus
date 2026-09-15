from __future__ import annotations

import json
from pathlib import Path

import pytest


VALIDATE_FIXTURES = Path(__file__).parent / "fixtures" / "validate"
REPORT_FIXTURE = Path(__file__).parent / "fixtures" / "report" / "candidates.jsonl"


@pytest.mark.parametrize(
    "command",
    [
        "normalize",
        "extract",
        "report",
        "validate-analysis",
        "validate-candidate",
        "validate-review",
        "validate-rights",
    ],
)
def test_all_input_positions_reject_symlink_loops_without_touching_output(
    run_ltc, tmp_path: Path, command: str
) -> None:
    loop = tmp_path / "loop"
    loop.symlink_to(loop)
    output = tmp_path / "output.json"
    original = b"preserve existing output\n"
    output.write_bytes(original)

    if command in {"normalize", "extract", "report"}:
        arguments = [command, "--input", loop, "--output", output]
    else:
        paths = {
            "analysis": VALIDATE_FIXTURES / "analysis.json",
            "candidate": VALIDATE_FIXTURES / "candidate.json",
            "review": VALIDATE_FIXTURES / "review.json",
            "rights": VALIDATE_FIXTURES / "rights.json",
        }
        paths[command.removeprefix("validate-")] = loop
        arguments = ["validate"]
        for name in ("analysis", "candidate", "review", "rights"):
            arguments.extend((f"--{name}", paths[name]))
        arguments.extend(("--output", output))

    result = run_ltc(*arguments)

    assert result.returncode == 2
    assert json.loads(result.stderr)["error"] == {
        "code": "invalid-input-path",
        "message": "could not resolve input path",
    }
    assert output.read_bytes() == original

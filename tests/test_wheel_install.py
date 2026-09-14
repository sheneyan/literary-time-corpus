from __future__ import annotations

import os
import subprocess
import sys
import zipfile
from pathlib import Path, PurePosixPath


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_ARTIFACTS = {
    "normalized.json",
    "candidates.jsonl",
    "report.json",
    "review.md",
    "run.json",
}


def test_wheel_installs_standalone_scanner_without_repository_content(
    tmp_path: Path,
) -> None:
    dist = tmp_path / "dist"
    environment = tmp_path / "environment"
    source = tmp_path / "book.txt"
    output = tmp_path / "scan"
    source.write_text("At 13:15 the synthetic clock chimed.\n", encoding="utf-8")

    subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(dist)],
        cwd=REPOSITORY_ROOT,
        check=True,
    )
    wheel = next(dist.glob("*.whl"))
    with zipfile.ZipFile(wheel) as archive:
        members = [PurePosixPath(name) for name in archive.namelist()]

    assert members
    assert all(
        member.parts[0] == "literary_time_corpus"
        or member.parts[0].startswith("literary_time_corpus-")
        and member.parts[0].endswith(".dist-info")
        for member in members
    )
    assert all(
        member.parts[0] != "literary_time_corpus"
        or member.suffix == ".py"
        for member in members
    )
    forbidden_parts = {
        ".local",
        "docs",
        "fixtures",
        "scans",
        "source",
        "sources",
        "tests",
    }
    assert not [member for member in members if forbidden_parts.intersection(member.parts)]

    subprocess.run([sys.executable, "-m", "venv", str(environment)], check=True)
    python = environment / "bin" / "python"
    ltc = environment / "bin" / "ltc"
    subprocess.run(
        [str(python), "-m", "pip", "install", "--no-deps", str(wheel)],
        check=True,
    )
    result = subprocess.run(
        [str(ltc), "scan", str(source), "--output", str(output)],
        cwd=tmp_path,
        env={"PATH": os.defpath},
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert {path.name for path in output.iterdir()} == EXPECTED_ARTIFACTS

from __future__ import annotations

import os
import shutil
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
ALLOWED_DIST_INFO_MEMBERS = {
    PurePosixPath("METADATA"),
    PurePosixPath("RECORD"),
    PurePosixPath("WHEEL"),
    PurePosixPath("entry_points.txt"),
    PurePosixPath("licenses/LICENSE"),
}


def tracked_working_tree_paths() -> list[PurePosixPath]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
    )
    return [
        PurePosixPath(raw.decode("utf-8"))
        for raw in result.stdout.split(b"\0")
        if raw
    ]


def export_tracked_working_tree(destination: Path) -> list[PurePosixPath]:
    tracked = tracked_working_tree_paths()
    for relative_path in tracked:
        source = REPOSITORY_ROOT.joinpath(*relative_path.parts)
        target = destination.joinpath(*relative_path.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    return tracked


def venv_executables(environment: Path, *, os_name: str) -> tuple[Path, Path]:
    if os_name == "nt":
        scripts = environment / "Scripts"
        return scripts / "python.exe", scripts / "ltc.exe"
    scripts = environment / "bin"
    return scripts / "python", scripts / "ltc"


def test_venv_executable_paths_cover_windows_and_posix_layouts() -> None:
    environment = Path("environment")

    assert venv_executables(environment, os_name="nt") == (
        environment / "Scripts/python.exe",
        environment / "Scripts/ltc.exe",
    )
    assert venv_executables(environment, os_name="posix") == (
        environment / "bin/python",
        environment / "bin/ltc",
    )


def test_wheel_installs_standalone_scanner_without_repository_content(
    tmp_path: Path,
) -> None:
    dist = tmp_path / "dist"
    export = tmp_path / "export"
    environment = tmp_path / "environment"
    source = tmp_path / "book.txt"
    output = tmp_path / "scan"
    private_probe = REPOSITORY_ROOT / "src/literary_time_corpus/private_probe.py"
    source.write_text("At 13:15 the synthetic clock chimed.\n", encoding="utf-8")

    assert not private_probe.exists()
    private_probe.write_text("PRIVATE_PROBE = True\n", encoding="utf-8")
    try:
        tracked = export_tracked_working_tree(export)
        assert PurePosixPath(
            "src/literary_time_corpus/private_probe.py"
        ) not in tracked
        assert not (export / "src/literary_time_corpus/private_probe.py").exists()
        subprocess.run(
            ["uv", "build", "--wheel", "--out-dir", str(dist)],
            cwd=export,
            check=True,
        )
    finally:
        private_probe.unlink()

    wheel = next(dist.glob("*.whl"))
    with zipfile.ZipFile(wheel) as archive:
        members = [PurePosixPath(name) for name in archive.namelist()]

    expected_package_members = {
        PurePosixPath(*path.parts[1:])
        for path in tracked
        if path.parts[:2] == ("src", "literary_time_corpus")
        and path.suffix == ".py"
    }
    actual_package_members = {
        member for member in members if member.parts[0] == "literary_time_corpus"
    }
    dist_info_roots = {
        member.parts[0]
        for member in members
        if member.parts[0].startswith("literary_time_corpus-")
        and member.parts[0].endswith(".dist-info")
    }

    assert actual_package_members == expected_package_members
    assert PurePosixPath("literary_time_corpus/private_probe.py") not in members
    assert len(dist_info_roots) == 1
    dist_info_root = next(iter(dist_info_roots))
    assert {
        PurePosixPath(*member.parts[1:])
        for member in members
        if member.parts[0] == dist_info_root
    } == ALLOWED_DIST_INFO_MEMBERS
    assert all(
        member.parts[0] == "literary_time_corpus"
        or member.parts[0] == dist_info_root
        for member in members
    )

    subprocess.run([sys.executable, "-m", "venv", str(environment)], check=True)
    python, ltc = venv_executables(environment, os_name=os.name)
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

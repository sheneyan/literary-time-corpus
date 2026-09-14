from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from pathlib import Path

import pytest

import literary_time_corpus.scan as scan_module
from literary_time_corpus.cli import main


ARTIFACTS = {
    "normalized.json",
    "candidates.jsonl",
    "report.json",
    "review.md",
    "run.json",
}


def tree_bytes(path: Path) -> dict[str, bytes]:
    return {
        entry.relative_to(path).as_posix(): entry.read_bytes()
        for entry in path.rglob("*")
        if entry.is_file()
    }


def error_from(result) -> dict[str, object]:
    assert result.returncode == 2
    assert result.stdout == ""
    return json.loads(result.stderr)["error"]


def test_existing_output_is_preserved_without_force(run_ltc, tmp_path: Path) -> None:
    source = tmp_path / "book.txt"
    output = tmp_path / "scan"
    source.write_text("At 13:15.", encoding="utf-8")
    output.mkdir()
    (output / "keep.txt").write_bytes(b"old\x00bytes")

    error = error_from(run_ltc("scan", source, "--output", output))

    assert error["code"] == "output-exists"
    assert tree_bytes(output) == {"keep.txt": b"old\x00bytes"}


def test_force_replaces_existing_output_with_exact_inventory(
    run_ltc, tmp_path: Path
) -> None:
    source = tmp_path / "book.txt"
    output = tmp_path / "scan"
    source.write_text("At 13:15.", encoding="utf-8")
    output.mkdir()
    (output / "keep.txt").write_bytes(b"old")
    sibling = tmp_path / "unrelated"
    sibling.write_bytes(b"keep sibling")

    result = run_ltc("scan", source, "--output", output, "--force")

    assert result.returncode == 0, result.stderr
    assert {entry.name for entry in output.iterdir()} == ARTIFACTS
    assert sibling.read_bytes() == b"keep sibling"
    assert sorted(entry.name for entry in tmp_path.iterdir()) == [
        "book.txt",
        "scan",
        "unrelated",
    ]


@pytest.mark.parametrize("failure", ["utf8", "markers", "metadata"])
def test_force_generation_failure_preserves_old_tree_and_discloses_retention(
    run_ltc, tmp_path: Path, failure: str
) -> None:
    source = tmp_path / "book.txt"
    output = tmp_path / "scan"
    output.mkdir()
    (output / "nested").mkdir()
    (output / "nested" / "keep.bin").write_bytes(b"old\x00tree")
    arguments: list[object] = ["scan", source, "--output", output, "--force"]
    if failure == "utf8":
        source.write_bytes(b"At 13:15.\xff")
    else:
        source.write_text("At 13:15.", encoding="utf-8")
    if failure == "markers":
        arguments += ["--start-marker", "BEGIN", "--end-marker", "END"]
    elif failure == "metadata":
        arguments += ["--title", "unsafe\nmetadata"]

    error = error_from(run_ltc(*arguments))

    assert tree_bytes(output) == {"nested/keep.bin": b"old\x00tree"}
    if failure == "metadata":
        assert not any(entry.name.startswith(".") for entry in tmp_path.iterdir())
        assert error["details"] == {"stage": "metadata"}
    else:
        retained = error["details"]["retainedPathBasename"]
        leftovers = [entry for entry in tmp_path.iterdir() if entry.name == retained]
        assert leftovers == [tmp_path / retained]
        assert (tmp_path / retained).stat().st_mode & 0o777 == 0o700


@pytest.mark.parametrize("kind", ["symlink", "file", "same", "inside", "root", "dot"])
def test_unsafe_output_targets_are_rejected_without_mutation(
    run_ltc, tmp_path: Path, project_root: Path, kind: str
) -> None:
    source = tmp_path / "book.txt"
    source.write_bytes(b"At 13:15.")
    link_target = tmp_path / "target"
    link_target.mkdir()
    (link_target / "keep").write_bytes(b"target")
    sibling = tmp_path / "sibling"
    sibling.write_bytes(b"sibling")
    if kind == "symlink":
        output = tmp_path / "scan"
        output.symlink_to(link_target, target_is_directory=True)
    elif kind == "file":
        output = tmp_path / "scan"
        output.write_bytes(b"output file")
    elif kind == "same":
        output = source
    elif kind == "inside":
        output = tmp_path
    elif kind == "root":
        output = Path("/")
    else:
        output = Path(".")

    error = error_from(run_ltc("scan", source, "--output", output, "--force"))

    assert error["code"] == "unsafe-output-path"
    assert source.read_bytes() == b"At 13:15."
    assert (link_target / "keep").read_bytes() == b"target"
    assert sibling.read_bytes() == b"sibling"
    assert not any(entry.name.startswith(".scan") for entry in tmp_path.iterdir())


@pytest.mark.parametrize("kind", ["missing-parent", "file-parent", "loop"])
def test_invalid_output_parent_is_rejected_without_mutation(
    run_ltc, tmp_path: Path, kind: str
) -> None:
    source = tmp_path / "book.txt"
    source.write_bytes(b"At 13:15.")
    if kind == "missing-parent":
        output = tmp_path / "missing" / "scan"
    elif kind == "file-parent":
        parent = tmp_path / "parent"
        parent.write_bytes(b"parent")
        output = parent / "scan"
    else:
        first = tmp_path / "first"
        second = tmp_path / "second"
        first.symlink_to(second)
        second.symlink_to(first)
        output = first / "scan"

    error = error_from(run_ltc("scan", source, "--output", output, "--force"))

    assert error["code"] in {"invalid-output-path", "unsafe-output-path"}
    assert source.read_bytes() == b"At 13:15."


def test_force_detects_final_component_replacement_before_switch(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    source = tmp_path / "book.txt"
    output = tmp_path / "scan"
    moved_old = tmp_path / "moved-old"
    target = tmp_path / "target"
    source.write_text("At 13:15.", encoding="utf-8")
    output.mkdir()
    (output / "keep").write_bytes(b"old")
    target.mkdir()
    (target / "keep").write_bytes(b"target")
    verify = scan_module._verify_staging
    calls = 0

    def replace_after_verification(*args, **kwargs):
        nonlocal calls
        result = verify(*args, **kwargs)
        calls += 1
        if calls == 1:
            output.rename(moved_old)
            output.symlink_to(target, target_is_directory=True)
        return result

    monkeypatch.setattr(scan_module, "_verify_staging", replace_after_verification)

    exit_code = main(["scan", str(source), "--output", str(output), "--force"])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert json.loads(captured.err)["error"]["details"]["stage"] == "publication"
    assert output.is_symlink()
    assert (target / "keep").read_bytes() == b"target"
    assert (moved_old / "keep").read_bytes() == b"old"


def test_force_detects_output_parent_replacement_before_generation(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    parent = tmp_path / "parent"
    moved_parent = tmp_path / "moved-parent"
    target = tmp_path / "target"
    parent.mkdir()
    target.mkdir()
    (target / "unrelated").write_bytes(b"target")
    source = parent / "book.txt"
    output = parent / "scan"
    source.write_text("At 13:15.", encoding="utf-8")
    output.mkdir()
    (output / "keep").write_bytes(b"old")
    mkdtemp = scan_module.tempfile.mkdtemp
    replaced = False

    def replace_parent_before_staging(*args, **kwargs):
        nonlocal replaced
        if not replaced:
            replaced = True
            parent.rename(moved_parent)
            parent.symlink_to(target, target_is_directory=True)
        return mkdtemp(*args, **kwargs)

    monkeypatch.setattr(scan_module.tempfile, "mkdtemp", replace_parent_before_staging)
    try:
        exit_code = main(["scan", str(source), "--output", str(output), "--force"])
        captured = capsys.readouterr()
        assert exit_code == 2
        error = json.loads(captured.err)["error"]
        assert error["code"] == "unsafe-output-path"
        assert error["details"]["stage"] == "publication"
        assert (target / "unrelated").read_bytes() == b"target"
        assert not (target / "scan").exists()
        assert (moved_parent / "scan" / "keep").read_bytes() == b"old"
    finally:
        if parent.is_symlink():
            parent.unlink()
        if moved_parent.exists():
            moved_parent.rename(parent)


def test_force_black_box_fifo_coordinated_path_replacement_is_bounded(
    tmp_path: Path, project_root: Path
) -> None:
    source = tmp_path / "book.txt"
    output = tmp_path / "scan"
    moved_old = tmp_path / "moved-old"
    target = tmp_path / "target"
    signal_fifo = tmp_path / "staging-ready"
    source.write_text("ordinary text\n" * 1_000_000, encoding="utf-8")
    output.mkdir()
    (output / "keep").write_bytes(b"old")
    target.mkdir()
    (target / "keep").write_bytes(b"target")
    os.mkfifo(signal_fifo)

    def announce_staging() -> None:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if any(tmp_path.glob(".scan.scan-*")):
                with signal_fifo.open("wb", buffering=0) as fifo:
                    fifo.write(b"1")
                return
            time.sleep(0.001)

    watcher = threading.Thread(target=announce_staging, daemon=True)
    watcher.start()
    process = subprocess.Popen(
        ["uv", "run", "ltc", "scan", str(source), "--output", str(output), "--force"],
        cwd=project_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    fifo_fd = os.open(signal_fifo, os.O_RDONLY | os.O_NONBLOCK)
    try:
        deadline = time.monotonic() + 10
        signal = b""
        while time.monotonic() < deadline and not signal:
            try:
                signal = os.read(fifo_fd, 1)
            except BlockingIOError:
                signal = b""
            if process.poll() is not None:
                break
            time.sleep(0.001)
    finally:
        os.close(fifo_fd)
    assert signal == b"1"
    output.rename(moved_old)
    output.symlink_to(target, target_is_directory=True)
    stdout, stderr = process.communicate(timeout=15)
    watcher.join(timeout=1)

    assert process.returncode == 2
    assert stdout == ""
    assert json.loads(stderr)["error"]["details"]["stage"] == "publication"
    assert output.is_symlink()
    assert (target / "keep").read_bytes() == b"target"
    assert (moved_old / "keep").read_bytes() == b"old"


def test_force_rolls_back_when_staging_publication_fails(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    source = tmp_path / "book.txt"
    output = tmp_path / "scan"
    source.write_text("At 13:15.", encoding="utf-8")
    output.mkdir()
    (output / "keep").write_bytes(b"old")
    rename_no_replace = scan_module._rename_no_replace

    def fail_staging_move(source_path, destination_path, *args, **kwargs):
        if Path(source_path).name.startswith(".scan.scan-") and Path(destination_path) == output:
            raise PermissionError("synthetic publication failure")
        return rename_no_replace(source_path, destination_path, *args, **kwargs)

    monkeypatch.setattr(scan_module, "_rename_no_replace", fail_staging_move)

    exit_code = main(["scan", str(source), "--output", str(output), "--force"])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert tree_bytes(output) == {"keep": b"old"}
    assert json.loads(captured.err)["error"]["details"]["stage"] == "publication"


def test_force_rollback_never_overwrites_replacement_at_official_path(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    source = tmp_path / "book.txt"
    output = tmp_path / "scan"
    target = tmp_path / "target"
    source.write_text("At 13:15.", encoding="utf-8")
    output.mkdir()
    (output / "keep").write_bytes(b"old")
    target.mkdir()
    (target / "keep").write_bytes(b"replacement")
    rename_no_replace = scan_module._rename_no_replace

    def collide_with_staging_move(source_path, destination_path, *args, **kwargs):
        if Path(source_path).name.startswith(".scan.scan-") and Path(destination_path) == output:
            output.symlink_to(target, target_is_directory=True)
            return rename_no_replace(source_path, destination_path, *args, **kwargs)
        return rename_no_replace(source_path, destination_path, *args, **kwargs)

    monkeypatch.setattr(scan_module, "_rename_no_replace", collide_with_staging_move)

    exit_code = main(["scan", str(source), "--output", str(output), "--force"])
    captured = capsys.readouterr()

    assert exit_code == 2
    error = json.loads(captured.err)["error"]
    assert error["details"]["stage"] == "publication"
    assert error["details"]["officialPathStatus"] == "present"
    retained_backup = tmp_path / error["details"]["retainedBackupBasename"]
    assert (retained_backup / "entry" / "keep").read_bytes() == b"old"
    assert output.is_symlink()
    assert (output / "keep").read_bytes() == b"replacement"


def test_force_restores_old_output_after_post_publish_verification_failure(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    source = tmp_path / "book.txt"
    output = tmp_path / "scan"
    source.write_text("At 13:15.", encoding="utf-8")
    output.mkdir()
    (output / "keep").write_bytes(b"old")
    verify = scan_module._verify_staging
    calls = 0

    def fail_post_publish(*args, **kwargs):
        nonlocal calls
        calls += 1
        result = verify(*args, **kwargs)
        if calls == 2:
            raise scan_module.ScanError(
                "scan-verification-failed", "synthetic", stage="verification"
            )
        return result

    monkeypatch.setattr(scan_module, "_verify_staging", fail_post_publish)

    exit_code = main(["scan", str(source), "--output", str(output), "--force"])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert tree_bytes(output) == {"keep": b"old"}
    details = json.loads(captured.err)["error"]["details"]
    assert details["stage"] == "verification"
    assert details["officialPathStatus"] == "present"
    assert Path(details["retainedPathBasename"]).name == details["retainedPathBasename"]


def test_force_cleanup_retains_mismatched_backup_replacement(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    source = tmp_path / "book.txt"
    output = tmp_path / "scan"
    moved_old = tmp_path / "moved-old"
    source.write_text("At 13:15.", encoding="utf-8")
    output.mkdir()
    (output / "keep").write_bytes(b"old")
    verify = scan_module._verify_staging
    calls = 0

    def replace_backup_after_post_verification(*args, **kwargs):
        nonlocal calls
        result = verify(*args, **kwargs)
        calls += 1
        if calls == 2:
            containers = list(tmp_path.glob(".scan.backup-*"))
            assert len(containers) == 1
            entry = containers[0] / "entry"
            entry.rename(moved_old)
            entry.mkdir()
            (entry / "replacement").write_bytes(b"do not delete")
        return result

    monkeypatch.setattr(
        scan_module, "_verify_staging", replace_backup_after_post_verification
    )

    exit_code = main(["scan", str(source), "--output", str(output), "--force"])
    captured = capsys.readouterr()

    assert exit_code == 2
    error = json.loads(captured.err)["error"]
    assert error["code"] == "scan-cleanup-failed"
    assert error["details"]["stage"] == "cleanup"
    retained = tmp_path / error["details"]["retainedBackupBasename"]
    assert (retained / "entry" / "replacement").read_bytes() == b"do not delete"
    assert (moved_old / "keep").read_bytes() == b"old"
    assert {entry.name for entry in output.iterdir()} == ARTIFACTS


def test_force_cleanup_never_deletes_replaced_backup_child(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    source = tmp_path / "book.txt"
    output = tmp_path / "scan"
    moved_old_file = tmp_path / "moved-old-file"
    source.write_text("At 13:15.", encoding="utf-8")
    output.mkdir()
    (output / "keep").write_bytes(b"old child")
    stat_function = scan_module.os.stat
    injected = False

    def replace_child_after_snapshot(path, *args, **kwargs):
        nonlocal injected
        status = stat_function(path, *args, **kwargs)
        if path == "keep" and kwargs.get("dir_fd") is not None and not injected:
            injected = True
            containers = list(tmp_path.glob(".scan.backup-*"))
            assert len(containers) == 1
            child = containers[0] / "entry" / "keep"
            child.rename(moved_old_file)
            child.write_bytes(b"replacement child")
        return status

    monkeypatch.setattr(scan_module.os, "stat", replace_child_after_snapshot)

    exit_code = main(["scan", str(source), "--output", str(output), "--force"])
    captured = capsys.readouterr()

    assert exit_code == 2
    error = json.loads(captured.err)["error"]
    retained = tmp_path / error["details"]["retainedBackupBasename"]
    assert (retained / "entry" / "keep").read_bytes() == b"replacement child"
    assert moved_old_file.read_bytes() == b"old child"

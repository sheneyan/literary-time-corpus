from __future__ import annotations

import errno
import json
import threading
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


def test_force_event_coordinated_final_component_replacement_before_switch(
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
    verification_ready = threading.Event()
    resume_publication = threading.Event()

    def pause_after_verification(*args, **kwargs):
        nonlocal calls
        result = verify(*args, **kwargs)
        calls += 1
        if calls == 1:
            verification_ready.set()
            assert resume_publication.wait(timeout=5)
        return result

    monkeypatch.setattr(scan_module, "_verify_staging", pause_after_verification)
    outcome: list[int] = []
    worker = threading.Thread(
        target=lambda: outcome.append(
            main(["scan", str(source), "--output", str(output), "--force"])
        )
    )
    worker.start()
    assert verification_ready.wait(timeout=5)
    output.rename(moved_old)
    output.symlink_to(target, target_is_directory=True)
    resume_publication.set()
    worker.join(timeout=5)
    assert not worker.is_alive()
    captured = capsys.readouterr()

    assert outcome == [2]
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
        assert error["details"]["parentPathStatus"] == "replaced"
        assert error["details"]["retentionScope"] == "replacement-parent"
        retained = error["details"]["retainedPathBasename"]
        assert (target / retained / "entry").is_dir()
        assert (target / "unrelated").read_bytes() == b"target"
        assert not (target / "scan").exists()
        assert (moved_parent / "scan" / "keep").read_bytes() == b"old"
    finally:
        if parent.is_symlink():
            parent.unlink()
        if moved_parent.exists():
            moved_parent.rename(parent)


def test_force_parent_swap_after_old_backup_restores_with_original_parent_anchor(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    parent = tmp_path / "parent"
    moved_parent = tmp_path / "moved-parent"
    parent.mkdir()
    source = parent / "book.txt"
    output = parent / "scan"
    source.write_text("At 13:15.", encoding="utf-8")
    output.mkdir()
    (output / "keep").write_bytes(b"old")
    rename_no_replace = scan_module._rename_no_replace
    swapped = False

    def swap_parent_after_old_backup(source_path, destination_path, *args, **kwargs):
        nonlocal swapped
        result = rename_no_replace(
            source_path, destination_path, *args, **kwargs
        )
        if Path(source_path).name == "scan" and not swapped:
            swapped = True
            parent.rename(moved_parent)
            parent.mkdir()
            (parent / "unrelated").write_bytes(b"replacement parent")
        return result

    monkeypatch.setattr(
        scan_module, "_rename_no_replace", swap_parent_after_old_backup
    )

    exit_code = main(["scan", str(source), "--output", str(output), "--force"])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert captured.out == ""
    error = json.loads(captured.err)["error"]
    assert error["details"]["stage"] == "publication"
    assert error["details"]["parentPathStatus"] == "replaced"
    assert error["details"]["retentionScope"] == "original-parent"
    retained = error["details"]["retainedPathBasename"]
    assert (moved_parent / "scan" / "keep").read_bytes() == b"old"
    assert (moved_parent / retained / "entry").is_dir()
    assert (parent / "unrelated").read_bytes() == b"replacement parent"
    assert not (parent / retained).exists()


def test_force_backup_creation_stays_in_anchored_parent_during_swap(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    parent = tmp_path / "parent"
    moved_parent = tmp_path / "moved-parent"
    parent.mkdir()
    source = parent / "book.txt"
    output = parent / "scan"
    source.write_text("At 13:15.", encoding="utf-8")
    output.mkdir()
    (output / "keep").write_bytes(b"old")
    mkdir = scan_module.os.mkdir
    swapped = False

    def swap_during_backup_creation(path, *args, **kwargs):
        nonlocal swapped
        if ".backup-" in str(path) and kwargs.get("dir_fd") is not None and not swapped:
            swapped = True
            parent.rename(moved_parent)
            parent.mkdir()
            (parent / "unrelated").write_bytes(b"replacement parent")
        return mkdir(path, *args, **kwargs)

    monkeypatch.setattr(scan_module.os, "mkdir", swap_during_backup_creation)
    monkeypatch.setattr(
        scan_module.os,
        "supports_dir_fd",
        {*scan_module.os.supports_dir_fd, swap_during_backup_creation},
    )

    exit_code = main(["scan", str(source), "--output", str(output), "--force"])
    captured = capsys.readouterr()

    assert exit_code == 2
    error = json.loads(captured.err)["error"]
    details = error["details"]
    assert details["parentPathStatus"] == "replaced"
    assert details["retentionScope"] == "original-parent"
    assert (moved_parent / "scan" / "keep").read_bytes() == b"old"
    assert not any(entry.name.startswith(".scan.backup-") for entry in parent.iterdir())
    assert (parent / "unrelated").read_bytes() == b"replacement parent"


def test_force_quarantine_creation_stays_in_anchored_parent_during_swap(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    parent = tmp_path / "parent"
    moved_parent = tmp_path / "moved-parent"
    parent.mkdir()
    source = parent / "book.txt"
    output = parent / "scan"
    source.write_text("At 13:15.", encoding="utf-8")
    output.mkdir()
    (output / "keep").write_bytes(b"old")
    verify = scan_module._verify_staging
    mkdtemp = scan_module.tempfile.mkdtemp
    mkdir = scan_module.os.mkdir
    calls = 0
    swapped = False

    def fail_post_publish(*args, **kwargs):
        nonlocal calls
        calls += 1
        result = verify(*args, **kwargs)
        if calls == 2:
            raise scan_module.ScanError(
                "scan-verification-failed", "synthetic", stage="verification"
            )
        return result

    def swap_parent() -> None:
        nonlocal swapped
        if not swapped:
            swapped = True
            parent.rename(moved_parent)
            parent.mkdir()
            (parent / "unrelated").write_bytes(b"replacement parent")

    def swap_during_path_quarantine(*args, **kwargs):
        if ".quarantine-" in str(kwargs.get("prefix", "")):
            swap_parent()
        return mkdtemp(*args, **kwargs)

    def swap_during_anchored_quarantine(path, *args, **kwargs):
        if ".quarantine-" in str(path) and kwargs.get("dir_fd") is not None:
            swap_parent()
        return mkdir(path, *args, **kwargs)

    monkeypatch.setattr(scan_module, "_verify_staging", fail_post_publish)
    monkeypatch.setattr(scan_module.tempfile, "mkdtemp", swap_during_path_quarantine)
    monkeypatch.setattr(scan_module.os, "mkdir", swap_during_anchored_quarantine)
    monkeypatch.setattr(
        scan_module.os,
        "supports_dir_fd",
        {*scan_module.os.supports_dir_fd, swap_during_anchored_quarantine},
    )

    exit_code = main(["scan", str(source), "--output", str(output), "--force"])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert captured.out == ""
    details = json.loads(captured.err)["error"]["details"]
    assert details["stage"] == "verification"
    assert details["parentPathStatus"] == "replaced"
    assert details["retentionScope"] == "original-parent"
    retained = details["retainedPathBasename"]
    assert (moved_parent / "scan" / "keep").read_bytes() == b"old"
    assert (moved_parent / retained / "entry").is_dir()
    assert (parent / "unrelated").read_bytes() == b"replacement parent"


def test_force_rechecks_parent_identity_immediately_before_success(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    parent = tmp_path / "parent"
    moved_parent = tmp_path / "moved-parent"
    parent.mkdir()
    source = parent / "book.txt"
    output = parent / "scan"
    source.write_text("At 13:15.", encoding="utf-8")
    output.mkdir()
    (output / "keep").write_bytes(b"old")
    verify = scan_module._verify_staging
    calls = 0

    def move_parent_after_final_verification(*args, **kwargs):
        nonlocal calls
        result = verify(*args, **kwargs)
        calls += 1
        if calls == 3:
            parent.rename(moved_parent)
            parent.mkdir()
            (parent / "unrelated").write_bytes(b"replacement parent")
        return result

    monkeypatch.setattr(
        scan_module, "_verify_staging", move_parent_after_final_verification
    )

    exit_code = main(["scan", str(source), "--output", str(output), "--force"])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert captured.out == ""
    details = json.loads(captured.err)["error"]["details"]
    assert details["stage"] == "verification"
    assert details["parentPathStatus"] == "replaced"
    assert details["retentionScope"] == "original-parent"
    assert details["officialPathStatus"] == "present"
    assert {entry.name for entry in (moved_parent / "scan").iterdir()} == ARTIFACTS
    assert (parent / "unrelated").read_bytes() == b"replacement parent"


# FIFO inputs are intentionally rejected as non-regular source files. The
# in-process Event barrier above coordinates the exact pre-publication window;
# run_ltc force-success tests still exercise the real subprocess CLI boundary.


def test_force_rechecks_published_output_after_backup_cleanup(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    source = tmp_path / "book.txt"
    output = tmp_path / "scan"
    moved_new = tmp_path / "moved-new"
    source.write_text("At 13:15.", encoding="utf-8")
    output.mkdir()
    (output / "keep").write_bytes(b"old")
    remove_backup = scan_module._remove_owned_backup

    def replace_official_during_cleanup(*args, **kwargs):
        result = remove_backup(*args, **kwargs)
        output.rename(moved_new)
        output.mkdir()
        (output / "competing").write_bytes(b"do not overwrite")
        return result

    monkeypatch.setattr(
        scan_module, "_remove_owned_backup", replace_official_during_cleanup
    )

    exit_code = main(["scan", str(source), "--output", str(output), "--force"])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert captured.out == ""
    error = json.loads(captured.err)["error"]
    assert error["code"] == "scan-verification-failed"
    assert error["details"]["stage"] == "verification"
    assert (output / "competing").read_bytes() == b"do not overwrite"
    assert {entry.name for entry in moved_new.iterdir()} == ARTIFACTS


def test_force_quarantines_owned_output_corrupted_after_backup_cleanup(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    source = tmp_path / "book.txt"
    output = tmp_path / "scan"
    source.write_text("At 13:15.", encoding="utf-8")
    output.mkdir()
    (output / "keep").write_bytes(b"old")
    remove_backup = scan_module._remove_owned_backup

    def corrupt_official_during_cleanup(*args, **kwargs):
        result = remove_backup(*args, **kwargs)
        (output / "review.md").write_bytes(b"corrupt")
        return result

    monkeypatch.setattr(
        scan_module, "_remove_owned_backup", corrupt_official_during_cleanup
    )

    exit_code = main(["scan", str(source), "--output", str(output), "--force"])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert captured.out == ""
    error = json.loads(captured.err)["error"]
    assert error["code"] == "scan-verification-failed"
    retained = tmp_path / error["details"]["retainedPathBasename"]
    assert error["details"]["officialPathStatus"] == "absent"
    assert (retained / "entry" / "review.md").read_bytes() == b"corrupt"
    assert not output.exists()


def test_force_retains_owned_output_on_unexpected_final_verifier_failure(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    source = tmp_path / "book.txt"
    output = tmp_path / "scan"
    source.write_text("At 13:15.", encoding="utf-8")
    output.mkdir()
    (output / "keep").write_bytes(b"old")
    verify = scan_module._verify_staging
    calls = 0

    def fail_third_verification(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 3:
            raise RuntimeError("private final verifier failure")
        return verify(*args, **kwargs)

    monkeypatch.setattr(scan_module, "_verify_staging", fail_third_verification)

    exit_code = main(["scan", str(source), "--output", str(output), "--force"])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert captured.out == ""
    error = json.loads(captured.err)["error"]
    assert error["code"] == "internal-generation-failed"
    assert error["details"]["stage"] == "staging"
    retained = tmp_path / error["details"]["retainedPathBasename"]
    assert (retained / "entry").is_dir()
    assert not output.exists()
    assert "private final verifier failure" not in captured.err


def test_force_rechecks_identity_after_final_verifier_swaps_to_symlink(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    source = tmp_path / "book.txt"
    output = tmp_path / "scan"
    moved_valid = tmp_path / "moved-valid"
    source.write_text("At 13:15.", encoding="utf-8")
    output.mkdir()
    (output / "keep").write_bytes(b"old")
    verify = scan_module._verify_staging
    calls = 0

    def swap_after_final_verification(*args, **kwargs):
        nonlocal calls
        result = verify(*args, **kwargs)
        calls += 1
        if calls == 3:
            output.rename(moved_valid)
            output.symlink_to(moved_valid, target_is_directory=True)
        return result

    monkeypatch.setattr(
        scan_module, "_verify_staging", swap_after_final_verification
    )

    exit_code = main(["scan", str(source), "--output", str(output), "--force"])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert captured.out == ""
    error = json.loads(captured.err)["error"]
    assert error["code"] == "scan-verification-failed"
    assert error["details"] == {
        "officialPathStatus": "present",
        "stage": "verification",
    }
    assert output.is_symlink()
    assert {entry.name for entry in moved_valid.iterdir()} == ARTIFACTS


def test_force_reports_backup_container_when_private_setup_fails(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    source = tmp_path / "book.txt"
    output = tmp_path / "scan"
    source.write_text("At 13:15.", encoding="utf-8")
    output.mkdir()
    (output / "keep").write_bytes(b"old")
    chmod = scan_module.os.chmod

    def fail_backup_chmod(path, *args, **kwargs):
        if ".backup-" in str(path) and kwargs.get("dir_fd") is not None:
            raise PermissionError("synthetic backup chmod failure")
        return chmod(path, *args, **kwargs)

    monkeypatch.setattr(scan_module.os, "chmod", fail_backup_chmod)
    monkeypatch.setattr(
        scan_module.os,
        "supports_dir_fd",
        {*scan_module.os.supports_dir_fd, fail_backup_chmod},
    )
    monkeypatch.setattr(
        scan_module.os,
        "supports_follow_symlinks",
        {*scan_module.os.supports_follow_symlinks, fail_backup_chmod},
    )

    exit_code = main(["scan", str(source), "--output", str(output), "--force"])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert captured.out == ""
    error = json.loads(captured.err)["error"]
    retained_name = error["details"]["retainedBackupBasename"]
    assert Path(retained_name).name == retained_name
    assert (tmp_path / retained_name).is_dir()
    assert tree_bytes(output) == {"keep": b"old"}


def test_force_keeps_backup_disclosure_when_staging_retention_also_fails(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    source = tmp_path / "book.txt"
    output = tmp_path / "scan"
    source.write_text("At 13:15.", encoding="utf-8")
    output.mkdir()
    (output / "keep").write_bytes(b"old")
    chmod = scan_module.os.chmod
    mkdir = scan_module.os.mkdir

    def fail_backup_chmod(path, *args, **kwargs):
        if ".backup-" in str(path) and kwargs.get("dir_fd") is not None:
            raise PermissionError("synthetic backup chmod failure")
        return chmod(path, *args, **kwargs)

    def fail_quarantine_creation(path, *args, **kwargs):
        if ".quarantine-" in str(path) and kwargs.get("dir_fd") is not None:
            raise PermissionError("synthetic quarantine failure")
        return mkdir(path, *args, **kwargs)

    monkeypatch.setattr(scan_module.os, "chmod", fail_backup_chmod)
    monkeypatch.setattr(scan_module.os, "mkdir", fail_quarantine_creation)
    monkeypatch.setattr(
        scan_module.os,
        "supports_dir_fd",
        {
            *scan_module.os.supports_dir_fd,
            fail_backup_chmod,
            fail_quarantine_creation,
        },
    )
    monkeypatch.setattr(
        scan_module.os,
        "supports_follow_symlinks",
        {*scan_module.os.supports_follow_symlinks, fail_backup_chmod},
    )

    exit_code = main(["scan", str(source), "--output", str(output), "--force"])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert captured.out == ""
    error = json.loads(captured.err)["error"]
    assert error["code"] == "scan-cleanup-failed"
    retained_name = error["details"]["retainedBackupBasename"]
    retained_staging_name = error["details"]["retainedPathBasename"]
    assert (tmp_path / retained_name).is_dir()
    assert (tmp_path / retained_staging_name).is_dir()
    assert tree_bytes(output) == {"keep": b"old"}


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
        if Path(source_path).name.startswith(".scan.scan-") and Path(
            destination_path
        ).name == output.name:
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
        if Path(source_path).name.startswith(".scan.scan-") and Path(
            destination_path
        ).name == output.name:
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


def test_force_cleanup_failure_after_parent_swap_reports_original_scope(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    parent = tmp_path / "parent"
    moved_parent = tmp_path / "moved-parent"
    parent.mkdir()
    source = parent / "book.txt"
    output = parent / "scan"
    source.write_text("At 13:15.", encoding="utf-8")
    output.mkdir()
    (output / "keep").write_bytes(b"old")

    def swap_parent_then_fail_cleanup(*args, **kwargs):
        parent.rename(moved_parent)
        parent.mkdir()
        (parent / "unrelated").write_bytes(b"replacement parent")
        raise OSError("synthetic cleanup failure")

    monkeypatch.setattr(
        scan_module, "_remove_owned_backup", swap_parent_then_fail_cleanup
    )

    exit_code = main(["scan", str(source), "--output", str(output), "--force"])
    captured = capsys.readouterr()

    assert exit_code == 2
    error = json.loads(captured.err)["error"]
    assert error["code"] == "scan-cleanup-failed"
    details = error["details"]
    assert details["parentPathStatus"] == "replaced"
    assert details["retentionScope"] == "original-parent"
    assert details["officialPathStatus"] == "present"
    assert (moved_parent / details["retainedBackupBasename"] / "entry").is_dir()
    assert {entry.name for entry in (moved_parent / "scan").iterdir()} == ARTIFACTS
    assert (parent / "unrelated").read_bytes() == b"replacement parent"


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
    monkeypatch.setattr(
        scan_module.os,
        "supports_dir_fd",
        {*scan_module.os.supports_dir_fd, replace_child_after_snapshot},
    )
    monkeypatch.setattr(
        scan_module.os,
        "supports_follow_symlinks",
        {*scan_module.os.supports_follow_symlinks, replace_child_after_snapshot},
    )

    exit_code = main(["scan", str(source), "--output", str(output), "--force"])
    captured = capsys.readouterr()

    assert exit_code == 2
    error = json.loads(captured.err)["error"]
    retained = tmp_path / error["details"]["retainedBackupBasename"]
    assert (retained / "entry" / "keep").read_bytes() == b"replacement child"
    assert moved_old_file.read_bytes() == b"old child"


def test_force_falls_back_when_descriptor_listing_is_unsupported(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    source = tmp_path / "book.txt"
    output = tmp_path / "scan"
    source.write_text("At 13:15.", encoding="utf-8")
    output.mkdir()
    (output / "keep").write_bytes(b"old")
    listdir = scan_module.os.listdir

    def reject_descriptor_listing(path):
        if isinstance(path, int):
            raise OSError(errno.ENOTSUP, "descriptor listing unavailable")
        return listdir(path)

    monkeypatch.setattr(scan_module.os, "listdir", reject_descriptor_listing)

    exit_code = main(["scan", str(source), "--output", str(output), "--force"])
    captured = capsys.readouterr()

    assert exit_code == 0, captured.err
    assert json.loads(captured.out)["status"] == "complete"
    assert {entry.name for entry in output.iterdir()} == ARTIFACTS
    assert sorted(entry.name for entry in tmp_path.iterdir()) == ["book.txt", "scan"]


def test_force_refuses_replacement_when_parent_descriptor_open_is_unsupported(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    source = tmp_path / "book.txt"
    output = tmp_path / "scan"
    source.write_text("At 13:15.", encoding="utf-8")
    output.mkdir()
    (output / "keep").write_bytes(b"old")
    open_function = scan_module.os.open

    def reject_parent_descriptor(path, *args, **kwargs):
        if Path(path) == tmp_path:
            raise OSError(errno.ENOTSUP, "parent descriptors unavailable")
        return open_function(path, *args, **kwargs)

    monkeypatch.setattr(scan_module.os, "open", reject_parent_descriptor)
    monkeypatch.setattr(
        scan_module.os,
        "supports_dir_fd",
        {*scan_module.os.supports_dir_fd, reject_parent_descriptor},
    )

    exit_code = main(["scan", str(source), "--output", str(output), "--force"])
    captured = capsys.readouterr()

    assert exit_code == 2
    error = json.loads(captured.err)["error"]
    assert error["code"] == "unsupported-safe-replacement"
    assert error["details"] == {"stage": "publication"}
    assert tree_bytes(output) == {"keep": b"old"}
    assert sorted(entry.name for entry in tmp_path.iterdir()) == ["book.txt", "scan"]


def test_new_output_remains_supported_without_parent_descriptor_anchor(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    source = tmp_path / "book.txt"
    output = tmp_path / "scan"
    source.write_text("At 13:15.", encoding="utf-8")
    open_function = scan_module.os.open

    def reject_parent_descriptor(path, *args, **kwargs):
        if Path(path) == tmp_path:
            raise OSError(errno.ENOTSUP, "parent descriptors unavailable")
        return open_function(path, *args, **kwargs)

    monkeypatch.setattr(scan_module.os, "open", reject_parent_descriptor)
    monkeypatch.setattr(
        scan_module.os,
        "supports_dir_fd",
        {*scan_module.os.supports_dir_fd, reject_parent_descriptor},
    )

    exit_code = main(["scan", str(source), "--output", str(output)])
    captured = capsys.readouterr()

    assert exit_code == 0, captured.err
    assert json.loads(captured.out)["status"] == "complete"
    assert {entry.name for entry in output.iterdir()} == ARTIFACTS


def test_force_refuses_replacement_without_anchored_exclusive_rename(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    source = tmp_path / "book.txt"
    output = tmp_path / "scan"
    source.write_text("At 13:15.", encoding="utf-8")
    output.mkdir()
    (output / "keep").write_bytes(b"old")
    monkeypatch.setattr(
        scan_module,
        "_supports_anchored_no_replace",
        lambda: False,
        raising=False,
    )

    exit_code = main(["scan", str(source), "--output", str(output), "--force"])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert json.loads(captured.err)["error"]["code"] == (
        "unsupported-safe-replacement"
    )
    assert tree_bytes(output) == {"keep": b"old"}
    assert sorted(entry.name for entry in tmp_path.iterdir()) == ["book.txt", "scan"]


def test_force_refuses_before_staging_when_anchored_rename_rejects_at_runtime(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    source = tmp_path / "book.txt"
    output = tmp_path / "scan"
    source.write_text("At 13:15.", encoding="utf-8")
    output.mkdir()
    (output / "keep").write_bytes(b"old")
    rename_function = scan_module._rename_no_replace

    def reject_probe_rename(source_path, destination_path, **kwargs):
        if ".probe-" in Path(source_path).name:
            raise OSError(errno.ENOTSUP, "exclusive rename unavailable")
        return rename_function(source_path, destination_path, **kwargs)

    monkeypatch.setattr(scan_module, "_rename_no_replace", reject_probe_rename)

    exit_code = main(["scan", str(source), "--output", str(output), "--force"])
    captured = capsys.readouterr()

    assert exit_code == 2
    error = json.loads(captured.err)["error"]
    assert error["code"] == "unsupported-safe-replacement"
    assert error["details"] == {"stage": "publication"}
    assert tree_bytes(output) == {"keep": b"old"}
    assert sorted(entry.name for entry in tmp_path.iterdir()) == ["book.txt", "scan"]


def test_force_ignores_runtime_unsupported_optional_chmod(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    source = tmp_path / "book.txt"
    output = tmp_path / "scan"
    source.write_text("At 13:15.", encoding="utf-8")
    output.mkdir()
    (output / "keep").write_bytes(b"old")
    chmod_function = scan_module.os.chmod

    def reject_anchored_chmod(path, mode, *args, **kwargs):
        if kwargs.get("dir_fd") is not None:
            raise NotImplementedError("chmod no-follow dir_fd unavailable")
        return chmod_function(path, mode, *args, **kwargs)

    monkeypatch.setattr(scan_module.os, "chmod", reject_anchored_chmod)
    monkeypatch.setattr(
        scan_module.os,
        "supports_dir_fd",
        {*scan_module.os.supports_dir_fd, reject_anchored_chmod},
    )
    monkeypatch.setattr(
        scan_module.os,
        "supports_follow_symlinks",
        {*scan_module.os.supports_follow_symlinks, reject_anchored_chmod},
    )

    exit_code = main(["scan", str(source), "--output", str(output), "--force"])
    captured = capsys.readouterr()

    assert exit_code == 0, captured.err
    assert {entry.name for entry in output.iterdir()} == ARTIFACTS
    assert sorted(entry.name for entry in tmp_path.iterdir()) == ["book.txt", "scan"]


def test_force_uses_path_cleanup_when_directory_open_is_unsupported(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    source = tmp_path / "book.txt"
    output = tmp_path / "scan"
    source.write_text("At 13:15.", encoding="utf-8")
    output.mkdir()
    (output / "keep").write_bytes(b"old")
    open_function = scan_module.os.open

    def reject_backup_directory_open(path, *args, **kwargs):
        if Path(path).name == "entry":
            raise NotImplementedError("directory open unavailable")
        return open_function(path, *args, **kwargs)

    monkeypatch.setattr(scan_module.os, "open", reject_backup_directory_open)
    monkeypatch.setattr(
        scan_module.os,
        "supports_dir_fd",
        {*scan_module.os.supports_dir_fd, reject_backup_directory_open},
    )

    exit_code = main(["scan", str(source), "--output", str(output), "--force"])
    captured = capsys.readouterr()

    assert exit_code == 0, captured.err
    assert {entry.name for entry in output.iterdir()} == ARTIFACTS


def test_force_selects_path_cleanup_for_windows_directory_open_semantics(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    source = tmp_path / "book.txt"
    output = tmp_path / "scan"
    source.write_text("At 13:15.", encoding="utf-8")
    output.mkdir()
    (output / "keep").write_bytes(b"old")
    open_function = scan_module.os.open

    def reject_windows_directory_open(path, *args, **kwargs):
        if Path(path).name == "entry":
            raise PermissionError(errno.EACCES, "Windows directory open semantics")
        return open_function(path, *args, **kwargs)

    monkeypatch.setattr(
        scan_module, "_requires_path_cleanup", lambda: True, raising=False
    )
    monkeypatch.setattr(scan_module.os, "open", reject_windows_directory_open)
    monkeypatch.setattr(
        scan_module.os,
        "supports_dir_fd",
        {*scan_module.os.supports_dir_fd, reject_windows_directory_open},
    )

    exit_code = main(["scan", str(source), "--output", str(output), "--force"])
    captured = capsys.readouterr()

    assert exit_code == 0, captured.err
    assert {entry.name for entry in output.iterdir()} == ARTIFACTS


def test_force_refuses_replacement_when_anchored_container_creation_is_unsupported(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    source = tmp_path / "book.txt"
    output = tmp_path / "scan"
    source.write_text("At 13:15.", encoding="utf-8")
    output.mkdir()
    (output / "keep").write_bytes(b"old")
    monkeypatch.setattr(
        scan_module.os,
        "supports_dir_fd",
        {
            function
            for function in scan_module.os.supports_dir_fd
            if function is not scan_module.os.mkdir
        },
    )

    exit_code = main(["scan", str(source), "--output", str(output), "--force"])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert json.loads(captured.err)["error"]["code"] == (
        "unsupported-safe-replacement"
    )
    assert tree_bytes(output) == {"keep": b"old"}
    assert sorted(entry.name for entry in tmp_path.iterdir()) == ["book.txt", "scan"]


def test_force_reports_retained_staging_when_anchored_mkdir_rejects_at_runtime(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    source = tmp_path / "book.txt"
    output = tmp_path / "scan"
    source.write_text("At 13:15.", encoding="utf-8")
    output.mkdir()
    (output / "keep").write_bytes(b"old")
    mkdir_function = scan_module.os.mkdir

    def reject_anchored_mkdir(path, *args, **kwargs):
        if kwargs.get("dir_fd") is not None:
            raise NotImplementedError("mkdir dir_fd unavailable at runtime")
        return mkdir_function(path, *args, **kwargs)

    monkeypatch.setattr(scan_module.os, "mkdir", reject_anchored_mkdir)
    monkeypatch.setattr(
        scan_module.os,
        "supports_dir_fd",
        {*scan_module.os.supports_dir_fd, reject_anchored_mkdir},
    )

    exit_code = main(["scan", str(source), "--output", str(output), "--force"])
    captured = capsys.readouterr()

    assert exit_code == 2
    error = json.loads(captured.err)["error"]
    assert error["code"] == "unsupported-safe-replacement"
    assert error["details"] == {"stage": "publication"}
    assert tree_bytes(output) == {"keep": b"old"}
    assert sorted(entry.name for entry in tmp_path.iterdir()) == ["book.txt", "scan"]


def test_force_keeps_parent_anchor_without_chmod_follow_symlinks_support(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    source = tmp_path / "book.txt"
    parent = tmp_path / "parent"
    moved_parent = tmp_path / "moved-parent"
    parent.mkdir()
    output = parent / "scan"
    source.write_text("At 13:15.", encoding="utf-8")
    output.mkdir()
    (output / "keep").write_bytes(b"old")
    original_mkdir = scan_module.os.mkdir
    swapped = False

    def swap_during_anchored_backup(path, *args, **kwargs):
        nonlocal swapped
        result = original_mkdir(path, *args, **kwargs)
        if (
            kwargs.get("dir_fd") is not None
            and ".backup-" in str(path)
            and not swapped
        ):
            swapped = True
            parent.rename(moved_parent)
            parent.mkdir()
        return result

    monkeypatch.setattr(scan_module.os, "mkdir", swap_during_anchored_backup)
    monkeypatch.setattr(
        scan_module.os,
        "supports_dir_fd",
        {*scan_module.os.supports_dir_fd, swap_during_anchored_backup},
    )
    monkeypatch.setattr(
        scan_module.os,
        "supports_follow_symlinks",
        {
            function
            for function in scan_module.os.supports_follow_symlinks
            if function is not scan_module.os.chmod
        },
    )

    exit_code = main(["scan", str(source), "--output", str(output), "--force"])
    captured = capsys.readouterr()

    assert exit_code == 2
    error = json.loads(captured.err)["error"]
    assert error["details"]["parentPathStatus"] == "replaced"
    assert error["details"]["retentionScope"] == "original-parent"
    assert tree_bytes(moved_parent / "scan") == {"keep": b"old"}
    assert not output.exists()


def test_force_anchor_does_not_require_descriptor_relative_child_open(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    source = tmp_path / "book.txt"
    output = tmp_path / "scan"
    source.write_text("At 13:15.", encoding="utf-8")
    output.mkdir()
    (output / "keep").write_bytes(b"old")
    monkeypatch.setattr(
        scan_module.os,
        "supports_dir_fd",
        {
            function
            for function in scan_module.os.supports_dir_fd
            if function is not scan_module.os.open
        },
    )

    exit_code = main(["scan", str(source), "--output", str(output), "--force"])
    captured = capsys.readouterr()

    assert exit_code == 0, captured.err
    assert {entry.name for entry in output.iterdir()} == ARTIFACTS

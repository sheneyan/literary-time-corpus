from __future__ import annotations

import errno
import hashlib
import ipaddress
import json
import os
import re
import secrets
import shutil
import stat
import tempfile
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from literary_time_corpus.candidate import (
    CANDIDATE_SCHEMA_VERSION,
    EXTRACTION_VERSION,
    WORK_METADATA_SCHEMA_VERSION,
    candidate_record_violations,
    work_metadata_violations,
)
from literary_time_corpus.extract import ExtractionError, extract_candidates
from literary_time_corpus.io import (
    OutputPathError,
    canonical_json_bytes,
    write_json_atomic,
    write_jsonl_atomic,
)
from literary_time_corpus.normalize import NormalizationError, normalize_bytes
from literary_time_corpus.normalized import (
    NORMALIZATION_VERSION,
    NORMALIZED_SCHEMA_VERSION,
    normalized_record_violations,
)
from literary_time_corpus.report import (
    REPORT_SCHEMA_VERSION,
    REPORT_VERSION,
    ReportError,
    build_report,
)
from literary_time_corpus.review import ReviewRenderError, render_review_markdown


SCAN_SCHEMA_VERSION = "scan-run-v1"
SCAN_VERSION = "scan-v1"
ARTIFACT_NAMES = (
    "normalized.json",
    "candidates.jsonl",
    "report.json",
    "review.md",
    "run.json",
)
DIGESTED_ARTIFACT_NAMES = ARTIFACT_NAMES[:-1]
ArtifactIdentity = tuple[int, int, int]
DirectoryIdentity = tuple[int, int]
INVALID_PERCENT_ESCAPE = re.compile(r"%(?![0-9A-Fa-f]{2})")
HOST_LABEL = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?")
HAZARDOUS_DIRECTIONAL_CONTROLS = frozenset(
    {
        "\u061c",
        "\u200e",
        "\u200f",
        *(chr(codepoint) for codepoint in range(0x202A, 0x202F)),
        *(chr(codepoint) for codepoint in range(0x2066, 0x206A)),
    }
)


class ScanError(ValueError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        stage: str,
        exit_code: int = 2,
    ):
        super().__init__(message)
        self.code = code
        self.details = {"stage": stage}
        self.exit_code = exit_code


@dataclass(frozen=True)
class ExistingTarget:
    device: int
    inode: int

    @property
    def identity(self) -> DirectoryIdentity:
        return self.device, self.inode


def _invalid_metadata() -> ScanError:
    return ScanError(
        "invalid-scan-metadata",
        "scan metadata is invalid",
        stage="metadata",
    )


def _valid_hostname(hostname: str) -> bool:
    if "%" in hostname:
        return False
    unqualified = hostname[:-1] if hostname.endswith(".") else hostname
    if not unqualified:
        return False
    try:
        ipaddress.ip_address(unqualified)
        return True
    except ValueError:
        pass
    try:
        ascii_hostname = unqualified.encode("idna").decode("ascii")
    except UnicodeError:
        return False
    if len(ascii_hostname) > 253:
        return False
    if all(character.isdigit() or character == "." for character in ascii_hostname):
        return False
    return all(
        HOST_LABEL.fullmatch(label) is not None
        for label in ascii_hostname.split(".")
    )


def _valid_source_url(source_url: str) -> bool:
    if (
        source_url != source_url.strip()
        or any(
            character.isspace()
            or unicodedata.category(character).startswith("C")
            for character in source_url
        )
        or INVALID_PERCENT_ESCAPE.search(source_url) is not None
    ):
        return False
    try:
        parsed = urlsplit(source_url)
        hostname = parsed.hostname
        parsed.port
    except (UnicodeError, ValueError):
        return False
    return (
        parsed.scheme.lower() in {"http", "https"}
        and hostname is not None
        and parsed.username is None
        and parsed.password is None
        and _valid_hostname(hostname)
    )


def build_work_metadata(
    input_path: Path,
    *,
    title: str | None,
    author: str | None,
    source_url: str | None,
) -> dict[str, object]:
    effective_title = title if title is not None else input_path.stem
    effective_author = author if author is not None else "unknown"
    if not effective_title.strip() or any(
        unicodedata.category(character) == "Cc"
        or character in HAZARDOUS_DIRECTIONAL_CONTROLS
        for character in effective_title
    ):
        raise _invalid_metadata()
    if not effective_author.strip() or any(
        unicodedata.category(character) == "Cc"
        or character in HAZARDOUS_DIRECTIONAL_CONTROLS
        for character in effective_author
    ):
        raise _invalid_metadata()

    if source_url is not None and not _valid_source_url(source_url):
        raise _invalid_metadata()

    metadata: dict[str, object] = {
        "author": effective_author,
        "metadataComplete": title is not None and author is not None,
        "schemaVersion": WORK_METADATA_SCHEMA_VERSION,
        "sourceUrl": source_url,
        "title": effective_title,
    }
    if work_metadata_violations(metadata):
        raise _invalid_metadata()
    return metadata


def _read_regular_file(input_path: Path) -> bytes:
    try:
        descriptor = os.open(input_path, os.O_RDONLY | os.O_NONBLOCK)
    except OSError as error:
        raise ScanError(
            "input-error", "could not read source", stage="normalization"
        ) from error
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ScanError(
                "input-error",
                "source must be a regular file",
                stage="normalization",
            )
        with os.fdopen(descriptor, "rb", closefd=False) as source_file:
            return source_file.read()
    except ScanError:
        raise
    except OSError as error:
        raise ScanError(
            "input-error", "could not read source", stage="normalization"
        ) from error
    finally:
        os.close(descriptor)


def _verification_failed() -> ScanError:
    return ScanError(
        "scan-verification-failed",
        "generated scan artifacts failed verification",
        stage="verification",
    )


def artifact_digest(path: Path) -> dict[str, object]:
    content = path.read_bytes()
    return {
        "byteSize": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
    }


def _bytes_digest(content: bytes) -> dict[str, object]:
    return {
        "byteSize": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
    }


def _read_regular_artifact(path: Path) -> tuple[bytes, ArtifactIdentity]:
    descriptor: int | None = None
    try:
        path_status = path.lstat()
        if not stat.S_ISREG(path_status.st_mode):
            raise _verification_failed()
        descriptor = os.open(
            path,
            os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0),
        )
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or (path_status.st_dev, path_status.st_ino)
            != (before.st_dev, before.st_ino)
        ):
            raise _verification_failed()
        with os.fdopen(descriptor, "rb", closefd=False) as artifact:
            content = artifact.read()
        after = os.fstat(descriptor)
        identity = (before.st_dev, before.st_ino, before.st_size)
        if (
            identity != (after.st_dev, after.st_ino, after.st_size)
            or len(content) != before.st_size
        ):
            raise _verification_failed()
        return content, identity
    except ScanError:
        raise
    except OSError:
        raise _verification_failed() from None
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _directory_identity(path: Path) -> DirectoryIdentity:
    try:
        status = path.lstat()
    except OSError:
        raise _verification_failed() from None
    if not stat.S_ISDIR(status.st_mode):
        raise _verification_failed()
    return status.st_dev, status.st_ino


def _unsafe_output_path(message: str = "output path is unsafe") -> ScanError:
    return ScanError("unsafe-output-path", message, stage="output")


def _invalid_output_path(message: str = "output path is invalid") -> ScanError:
    return ScanError("invalid-output-path", message, stage="output")


def _snapshot_scan_target(
    input_path: Path,
    output_path: Path,
    *,
    force: bool,
) -> tuple[ExistingTarget | None, DirectoryIdentity]:
    try:
        absolute_output = output_path.absolute()
        absolute_parent = absolute_output.parent
        resolved_output = absolute_output.resolve(strict=False)
        resolved_input = input_path.absolute().resolve(strict=False)
        resolved_cwd = Path.cwd().resolve(strict=True)
    except (OSError, RuntimeError):
        raise _invalid_output_path() from None

    if (
        resolved_output.parent == resolved_output
        or resolved_output == resolved_cwd
        or resolved_input == resolved_output
        or resolved_input.is_relative_to(resolved_output)
    ):
        raise _unsafe_output_path()

    try:
        parent_status = absolute_parent.lstat()
    except FileNotFoundError:
        raise _invalid_output_path("output parent does not exist") from None
    except OSError:
        raise _invalid_output_path() from None
    if not stat.S_ISDIR(parent_status.st_mode):
        raise _invalid_output_path("output parent must be a directory")
    parent_identity = parent_status.st_dev, parent_status.st_ino

    try:
        target_status = absolute_output.lstat()
    except FileNotFoundError:
        return None, parent_identity
    except OSError:
        raise _invalid_output_path() from None
    if not stat.S_ISDIR(target_status.st_mode) or stat.S_ISLNK(target_status.st_mode):
        raise _unsafe_output_path("output must be a real directory")
    target = ExistingTarget(target_status.st_dev, target_status.st_ino)
    if not force:
        raise ScanError(
            "output-exists",
            "output directory already exists",
            stage="publication",
        )
    return target, parent_identity


def _target_still_matches(path: Path, target: ExistingTarget) -> bool:
    try:
        status = path.lstat()
    except OSError:
        return False
    return (
        stat.S_ISDIR(status.st_mode)
        and not stat.S_ISLNK(status.st_mode)
        and (status.st_dev, status.st_ino) == target.identity
    )


def _directory_matches_identity(path: Path, expected: DirectoryIdentity) -> bool:
    try:
        status = path.lstat()
    except OSError:
        return False
    return stat.S_ISDIR(status.st_mode) and (
        status.st_dev,
        status.st_ino,
    ) == expected


def _path_entry_status(path: Path) -> str:
    try:
        path.lstat()
    except FileNotFoundError:
        return "absent"
    except OSError:
        return "unknown"
    return "present"


def _cleanup_failed(
    path: Path,
    *,
    retained_path_basename: str | None = None,
) -> ScanError:
    error = ScanError(
        "scan-cleanup-failed",
        "could not safely retain failed scan artifacts",
        stage="cleanup",
    )
    error.details["officialPathStatus"] = _path_entry_status(path)
    if retained_path_basename is not None:
        error.details["retainedPathBasename"] = retained_path_basename
    return error


def _retain_path_entry_in_quarantine(
    path: Path,
    expected_identity: DirectoryIdentity | None,
    *,
    parent_fd: int | None = None,
    parent_identity: DirectoryIdentity | None = None,
) -> dict[str, object] | None:
    parent_status = (
        _anchored_parent_status(path.parent, parent_identity)
        if parent_identity is not None
        else "current"
    )
    if parent_fd is not None:
        for _ in range(100):
            quarantine_name = f".{path.name}.quarantine-{secrets.token_hex(8)}"
            try:
                os.mkdir(quarantine_name, mode=0o700, dir_fd=parent_fd)
                break
            except FileExistsError:
                continue
            except OSError:
                error = _cleanup_failed(path)
                error.details["parentPathStatus"] = parent_status
                error.details["retentionScope"] = "original-parent"
                raise error from None
        else:
            error = _cleanup_failed(path)
            error.details["parentPathStatus"] = parent_status
            error.details["retentionScope"] = "original-parent"
            raise error
        quarantine = path.parent / quarantine_name
    else:
        try:
            quarantine = Path(
                tempfile.mkdtemp(
                    prefix=f".{path.name}.quarantine-",
                    dir=path.parent,
                )
            )
        except OSError:
            raise _cleanup_failed(path) from None
        try:
            quarantine.chmod(0o700)
        except OSError:
            raise _cleanup_failed(
                path,
                retained_path_basename=quarantine.name,
            ) from None
    moved_entry = quarantine / "entry"
    try:
        if parent_fd is None:
            os.rename(path, moved_entry)
        else:
            os.rename(
                _relative_to_parent(path, path.parent),
                _relative_to_parent(moved_entry, path.parent),
                src_dir_fd=parent_fd,
                dst_dir_fd=parent_fd,
            )
    except OSError:
        try:
            if parent_fd is None:
                quarantine.rmdir()
            else:
                os.rmdir(quarantine.name, dir_fd=parent_fd)
        except OSError:
            raise _cleanup_failed(
                path,
                retained_path_basename=quarantine.name,
            ) from None
        raise _cleanup_failed(path) from None

    try:
        moved_status = (
            moved_entry.lstat()
            if parent_fd is None
            else os.stat(
                _relative_to_parent(moved_entry, path.parent),
                dir_fd=parent_fd,
                follow_symlinks=False,
            )
        )
    except OSError:
        raise _cleanup_failed(
            path,
            retained_path_basename=quarantine.name,
        ) from None
    moved_identity = (moved_status.st_dev, moved_status.st_ino)
    result: dict[str, object] = {
        "identityMatched": (
            expected_identity is not None
            and stat.S_ISDIR(moved_status.st_mode)
            and moved_identity == expected_identity
        ),
        "officialPathStatus": (
            _path_entry_status(path)
            if parent_fd is None
            else _entry_status_at_anchor(path, path.parent, parent_fd)
        ),
        "retainedPathBasename": quarantine.name,
    }
    if parent_status != "current":
        result["parentPathStatus"] = parent_status
        result["retentionScope"] = (
            "original-parent" if parent_fd is not None else "replacement-parent"
        )
    return result


def _make_private_container(
    path: Path,
    purpose: str,
    *,
    parent_fd: int | None = None,
) -> Path:
    if parent_fd is not None:
        for _ in range(100):
            container_name = f".{path.name}.{purpose}-{secrets.token_hex(8)}"
            try:
                os.mkdir(container_name, mode=0o700, dir_fd=parent_fd)
                break
            except FileExistsError:
                continue
            except OSError as error:
                raise ScanError(
                    "invalid-output-path",
                    "could not create private transaction directory",
                    stage="publication",
                ) from error
        else:
            raise ScanError(
                "invalid-output-path",
                "could not create private transaction directory",
                stage="publication",
            )
        container = path.parent / container_name
        try:
            os.chmod(
                container_name,
                0o700,
                dir_fd=parent_fd,
                follow_symlinks=False,
            )
        except OSError as error:
            setup_error = ScanError(
                "invalid-output-path",
                "could not secure private transaction directory",
                stage="publication",
            )
            setup_error.details["retainedBackupBasename"] = container.name
            setup_error.details["retentionScope"] = "original-parent"
            raise setup_error from error
        return container
    try:
        container = Path(
            tempfile.mkdtemp(
                prefix=f".{path.name}.{purpose}-",
                dir=path.parent,
            )
        )
    except OSError as error:
        raise ScanError(
            "invalid-output-path",
            "could not create private transaction directory",
            stage="publication",
        ) from error
    try:
        container.chmod(0o700)
    except OSError as error:
        setup_error = ScanError(
            "invalid-output-path",
            "could not secure private transaction directory",
            stage="publication",
        )
        setup_error.details["retainedBackupBasename"] = container.name
        raise setup_error from error
    return container


def _rename_no_replace(
    source: Path,
    destination: Path,
    *,
    src_dir_fd: int | None = None,
    dst_dir_fd: int | None = None,
) -> None:
    """Rename without ever replacing the destination path entry."""
    import ctypes
    import errno
    import sys

    libc = ctypes.CDLL(None, use_errno=True)
    source_bytes = os.fsencode(source)
    destination_bytes = os.fsencode(destination)
    if sys.platform == "darwin" and hasattr(libc, "renameatx_np"):
        result = libc.renameatx_np(
            -2 if src_dir_fd is None else src_dir_fd,
            ctypes.c_char_p(source_bytes),
            -2 if dst_dir_fd is None else dst_dir_fd,
            ctypes.c_char_p(destination_bytes),
            0x00000004,
        )
    elif hasattr(libc, "renameat2"):
        result = libc.renameat2(
            -100 if src_dir_fd is None else src_dir_fd,
            ctypes.c_char_p(source_bytes),
            -100 if dst_dir_fd is None else dst_dir_fd,
            ctypes.c_char_p(destination_bytes),
            1,
        )
    elif os.name == "nt":
        # This is a guarded fallback, not a claim of atomic no-replace on every
        # Windows filesystem/API combination.
        if src_dir_fd is not None or dst_dir_fd is not None:
            raise OSError(errno.ENOTSUP, "directory descriptors are unavailable")
        if destination.exists() or destination.is_symlink():
            raise FileExistsError(errno.EEXIST, "destination exists")
        os.rename(source, destination)
        return
    else:
        raise OSError(errno.ENOTSUP, "exclusive rename is unavailable")
    if result != 0:
        error_number = ctypes.get_errno()
        raise OSError(error_number, os.strerror(error_number))


def _open_parent_descriptor(
    parent: Path,
    expected_identity: DirectoryIdentity,
) -> int | None:
    required = (
        os.open,
        os.rename,
        os.stat,
        os.unlink,
        os.rmdir,
        os.mkdir,
        os.chmod,
    )
    if not all(
        function in os.supports_dir_fd for function in required
    ) or os.chmod not in os.supports_follow_symlinks:
        return None
    try:
        descriptor = os.open(
            parent,
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0),
        )
    except (NotImplementedError, TypeError):
        return None
    except OSError as error:
        if error.errno in {errno.ENOSYS, errno.ENOTSUP, errno.EINVAL}:
            return None
        raise ScanError(
            "invalid-output-path",
            "could not anchor output parent",
            stage="publication",
        ) from error
    status = os.fstat(descriptor)
    if (
        not stat.S_ISDIR(status.st_mode)
        or (status.st_dev, status.st_ino) != expected_identity
    ):
        os.close(descriptor)
        raise ScanError(
            "unsafe-output-path",
            "output parent changed before transaction",
            stage="publication",
        )
    return descriptor


def _relative_to_parent(path: Path, parent: Path) -> Path:
    relative = Path(os.path.relpath(path.absolute(), parent.absolute()))
    if relative == Path(".") or relative.is_absolute() or ".." in relative.parts:
        raise OSError("transaction path escaped parent")
    return relative


def _transaction_rename_no_replace(
    source: Path,
    destination: Path,
    parent: Path,
    parent_fd: int | None,
) -> None:
    if parent_fd is None:
        _rename_no_replace(source, destination)
        return
    _rename_no_replace(
        _relative_to_parent(source, parent),
        _relative_to_parent(destination, parent),
        src_dir_fd=parent_fd,
        dst_dir_fd=parent_fd,
    )


def _anchored_parent_status(
    parent: Path,
    expected_identity: DirectoryIdentity,
) -> str:
    try:
        status = parent.lstat()
    except FileNotFoundError:
        return "absent"
    except OSError:
        return "unknown"
    if stat.S_ISDIR(status.st_mode) and (
        status.st_dev,
        status.st_ino,
    ) == expected_identity:
        return "current"
    return "replaced"


def _entry_status_at_anchor(
    path: Path,
    parent: Path,
    parent_fd: int,
) -> str:
    try:
        os.stat(
            _relative_to_parent(path, parent),
            dir_fd=parent_fd,
            follow_symlinks=False,
        )
    except FileNotFoundError:
        return "absent"
    except OSError:
        return "unknown"
    return "present"


def _remove_directory_contents(directory_fd: int) -> None:
    # The old output tree is explicitly authorized for cleanup. Rechecks catch
    # observed replacement, but portable unlink/rmdir APIs cannot condition
    # deletion on an inode against a malicious same-UID final-syscall race.
    for name in os.listdir(directory_fd):
        status = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        expected_identity = (status.st_dev, status.st_ino)
        if stat.S_ISDIR(status.st_mode):
            child_fd = os.open(
                name,
                os.O_RDONLY
                | getattr(os, "O_DIRECTORY", 0)
                | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=directory_fd,
            )
            try:
                child_status = os.fstat(child_fd)
                if (child_status.st_dev, child_status.st_ino) != expected_identity:
                    raise OSError("directory changed during cleanup")
                _remove_directory_contents(child_fd)
                current = os.stat(
                    name,
                    dir_fd=directory_fd,
                    follow_symlinks=False,
                )
                if (current.st_dev, current.st_ino) != expected_identity:
                    raise OSError("directory changed during cleanup")
            finally:
                os.close(child_fd)
            os.rmdir(name, dir_fd=directory_fd)
        else:
            current = os.stat(
                name,
                dir_fd=directory_fd,
                follow_symlinks=False,
            )
            if (current.st_dev, current.st_ino) != expected_identity:
                raise OSError("entry changed during cleanup")
            os.unlink(name, dir_fd=directory_fd)


def _remove_owned_backup_by_path(
    container: Path,
    entry: Path,
    expected_identity: DirectoryIdentity,
) -> None:
    if _directory_identity(entry) != expected_identity:
        raise OSError("backup identity changed")
    # Portable fallback for platforms without fd traversal. The old tree is
    # explicitly authorized and rechecked immediately before deletion;
    # pathname APIs retain the documented same-UID final syscall limitation.
    use_fd_functions = getattr(shutil, "_use_fd_functions", None)
    try:
        if use_fd_functions is not None:
            shutil._use_fd_functions = False
        shutil.rmtree(entry)
    finally:
        if use_fd_functions is not None:
            shutil._use_fd_functions = use_fd_functions
    container.rmdir()


def _requires_path_cleanup() -> bool:
    return os.name == "nt"


def _remove_owned_backup(
    container: Path,
    entry: Path,
    expected_identity: DirectoryIdentity,
) -> None:
    descriptor: int | None = None
    try:
        if _directory_identity(entry) != expected_identity:
            raise OSError("backup identity changed")
        if _requires_path_cleanup():
            _remove_owned_backup_by_path(container, entry, expected_identity)
            return
        try:
            descriptor = os.open(
                entry,
                os.O_RDONLY
                | getattr(os, "O_DIRECTORY", 0)
                | getattr(os, "O_NOFOLLOW", 0),
            )
        except (NotImplementedError, TypeError):
            _remove_owned_backup_by_path(container, entry, expected_identity)
            return
        except OSError as error:
            if error.errno not in {errno.ENOSYS, errno.ENOTSUP, errno.EINVAL}:
                raise
            _remove_owned_backup_by_path(container, entry, expected_identity)
            return
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) != expected_identity:
            raise OSError("backup identity changed")
        use_path_fallback = False
        try:
            _remove_directory_contents(descriptor)
        except (NotImplementedError, TypeError):
            use_path_fallback = True
        except OSError as error:
            if error.errno not in {errno.ENOSYS, errno.ENOTSUP, errno.EINVAL}:
                raise
            use_path_fallback = True
        if use_path_fallback:
            os.close(descriptor)
            descriptor = None
            _remove_owned_backup_by_path(container, entry, expected_identity)
            return
        if _directory_identity(entry) != expected_identity:
            raise OSError("backup identity changed")
        os.rmdir(entry)
        container.rmdir()
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _attach_retention(error: ScanError, retention: dict[str, object]) -> None:
    for key, value in retention.items():
        if key != "identityMatched":
            error.details[key] = value


def _staging_failure(error: Exception) -> ScanError:
    if isinstance(error, ScanError):
        return error
    if isinstance(error, OutputPathError):
        return ScanError(
            error.code,
            str(error),
            stage="staging",
        )
    return ScanError(
        "internal-generation-failed",
        "scan generation failed",
        stage="staging",
        exit_code=1,
    )


def build_run_manifest(
    *,
    source: bytes,
    input_basename: str,
    work_metadata: dict[str, object],
    start_marker: str | None,
    end_marker: str | None,
    candidates: list[dict[str, object]],
    report: dict[str, object],
    staging: Path,
) -> dict[str, object]:
    resolved_minutes = {
        candidate["normalizedTimes"][0]
        for candidate in candidates
        if candidate["precision"] == "exact-minute-resolved"
    }
    if (
        report.get("candidateCount") != len(candidates)
        or report.get("resolvedMinuteCount") != len(resolved_minutes)
    ):
        raise _verification_failed()

    body_selection: dict[str, object] = {"mode": "full-file"}
    if start_marker is not None and end_marker is not None:
        body_selection = {
            "endMarker": end_marker,
            "mode": "literal-markers",
            "startMarker": start_marker,
        }

    return {
        "artifactDigests": {
            name: artifact_digest(staging / name)
            for name in DIGESTED_ARTIFACT_NAMES
        },
        "bodySelection": body_selection,
        "candidateCount": len(candidates),
        "input": {
            "basename": input_basename,
            "byteSize": len(source),
            "sha256": hashlib.sha256(source).hexdigest(),
        },
        "metadata": work_metadata,
        "resolvedMinuteCount": len(resolved_minutes),
        "schemaVersion": SCAN_SCHEMA_VERSION,
        "status": "complete",
        "toolVersions": {
            "candidateSchemaVersion": CANDIDATE_SCHEMA_VERSION,
            "extractionVersion": EXTRACTION_VERSION,
            "normalizationVersion": NORMALIZATION_VERSION,
            "normalizedSchemaVersion": NORMALIZED_SCHEMA_VERSION,
            "reportSchemaVersion": REPORT_SCHEMA_VERSION,
            "reportVersion": REPORT_VERSION,
            "scanVersion": SCAN_VERSION,
            "workMetadataSchemaVersion": WORK_METADATA_SCHEMA_VERSION,
        },
    }


def _verify_staging(
    staging_path: Path,
    expected_run: dict[str, object],
    *,
    source: bytes,
    work_metadata: dict[str, object],
    start_marker: str | None,
    end_marker: str | None,
    expected_identities: dict[str, ArtifactIdentity] | None = None,
) -> dict[str, ArtifactIdentity]:
    try:
        if {path.name for path in staging_path.iterdir()} != set(ARTIFACT_NAMES):
            raise _verification_failed()
        artifact_reads = {
            name: _read_regular_artifact(staging_path / name)
            for name in ARTIFACT_NAMES
        }
        artifact_bytes = {
            name: content for name, (content, _) in artifact_reads.items()
        }
        identities = {
            name: identity for name, (_, identity) in artifact_reads.items()
        }
        normalized = json.loads(artifact_bytes["normalized.json"])
        candidate_bytes = artifact_bytes["candidates.jsonl"]
        candidates = [json.loads(line) for line in candidate_bytes.splitlines()]
        report = json.loads(artifact_bytes["report.json"])
        run = json.loads(artifact_bytes["run.json"])
        regenerated_normalized = normalize_bytes(
            source,
            start_marker=start_marker,
            end_marker=end_marker,
        )
        regenerated_candidates = extract_candidates(
            regenerated_normalized,
            work_metadata,
        )
        regenerated_report = build_report(staging_path / "candidates.jsonl")
        digests = {
            name: _bytes_digest(artifact_bytes[name])
            for name in DIGESTED_ARTIFACT_NAMES
        }
        report_candidate_identity = _read_regular_artifact(
            staging_path / "candidates.jsonl"
        )[1]
    except (
        ExtractionError,
        NormalizationError,
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        ReportError,
        TypeError,
    ):
        raise _verification_failed() from None

    if (
        (expected_identities is not None and identities != expected_identities)
        or report_candidate_identity != identities["candidates.jsonl"]
        or artifact_bytes["run.json"] != canonical_json_bytes(expected_run)
        or run != expected_run
        or normalized_record_violations(normalized)
        or any(candidate_record_violations(candidate) for candidate in candidates)
        or normalized_record_violations(regenerated_normalized)
        or any(
            candidate_record_violations(candidate)
            for candidate in regenerated_candidates
        )
        or artifact_bytes["normalized.json"]
        != canonical_json_bytes(regenerated_normalized)
        or candidate_bytes
        != b"".join(
            canonical_json_bytes(candidate) for candidate in regenerated_candidates
        )
        or artifact_bytes["report.json"] != canonical_json_bytes(regenerated_report)
        or report != regenerated_report
        or run.get("artifactDigests") != digests
    ):
        raise _verification_failed()

    input_record = run.get("input")
    metadata = run.get("metadata")
    if (
        not isinstance(input_record, dict)
        or normalized.get("sourceSha256") != input_record.get("sha256")
        or work_metadata_violations(metadata)
        or any(candidate.get("workMetadata") != metadata for candidate in candidates)
        or any(
            candidate.get("sourceId") != normalized.get("sourceId")
            or candidate.get("sourceSha256") != normalized.get("sourceSha256")
            or candidate.get("analysisTextSha256")
            != normalized.get("analysisTextSha256")
            for candidate in candidates
        )
    ):
        raise _verification_failed()

    resolved_minutes = {
        candidate["normalizedTimes"][0]
        for candidate in candidates
        if candidate["precision"] == "exact-minute-resolved"
    }
    try:
        expected_review = render_review_markdown(regenerated_candidates, metadata)
    except (TypeError, ValueError):
        raise _verification_failed() from None
    if (
        report.get("inputSha256")
        != hashlib.sha256(candidate_bytes).hexdigest()
        or report.get("candidateCount") != len(candidates)
        or report.get("resolvedMinuteCount") != len(resolved_minutes)
        or run.get("candidateCount") != len(candidates)
        or run.get("resolvedMinuteCount") != len(resolved_minutes)
        or artifact_bytes["review.md"] != expected_review
    ):
        raise _verification_failed()
    return identities


def scan_to_staging(
    input_path: Path,
    staging_path: Path,
    *,
    work_metadata: dict[str, object],
    start_marker: str | None,
    end_marker: str | None,
) -> tuple[dict[str, object], bytes, dict[str, object]]:
    source = _read_regular_file(input_path)
    try:
        document = normalize_bytes(
            source,
            start_marker=start_marker,
            end_marker=end_marker,
        )
    except NormalizationError as error:
        raise ScanError(error.code, str(error), stage="normalization") from error
    if normalized_record_violations(document):
        raise ScanError(
            "normalization-failed",
            "generated normalized record failed validation",
            stage="normalization",
        )

    try:
        candidates = extract_candidates(document, work_metadata)
    except ExtractionError as error:
        raise ScanError(error.code, str(error), stage="extraction") from error
    if any(candidate_record_violations(candidate) for candidate in candidates):
        raise ScanError(
            "candidate-generation-failed",
            "generated candidate failed validation",
            stage="extraction",
        )

    normalized_path = staging_path / "normalized.json"
    candidates_path = staging_path / "candidates.jsonl"
    report_path = staging_path / "report.json"
    write_json_atomic(normalized_path, document)
    write_jsonl_atomic(candidates_path, candidates)
    try:
        report = build_report(candidates_path)
    except ReportError as error:
        raise ScanError(error.code, str(error), stage="reporting") from error
    write_json_atomic(report_path, report)
    try:
        review = render_review_markdown(candidates, work_metadata)
    except ReviewRenderError as error:
        raise ScanError(error.code, str(error), stage="review-render") from error
    (staging_path / "review.md").write_bytes(review)
    try:
        run = build_run_manifest(
            source=source,
            input_basename=input_path.name,
            work_metadata=work_metadata,
            start_marker=start_marker,
            end_marker=end_marker,
            candidates=candidates,
            report=report,
            staging=staging_path,
        )
    except OSError:
        raise _verification_failed() from None
    write_json_atomic(staging_path / "run.json", run)
    return (
        {
            "candidateCount": report["candidateCount"],
            "resolvedMinuteCount": report["resolvedMinuteCount"],
        },
        source,
        run,
    )


def scan_file(
    input_path: Path,
    output_path: Path,
    *,
    title: str | None = None,
    author: str | None = None,
    source_url: str | None = None,
    start_marker: str | None = None,
    end_marker: str | None = None,
    force: bool = False,
) -> dict[str, object]:
    metadata = build_work_metadata(
        input_path,
        title=title,
        author=author,
        source_url=source_url,
    )
    existing_target, output_parent_identity = _snapshot_scan_target(
        input_path,
        output_path,
        force=force,
    )
    if not _directory_matches_identity(output_path.parent, output_parent_identity):
        raise ScanError(
            "unsafe-output-path",
            "output parent changed before staging",
            stage="publication",
        )
    try:
        staging_path = Path(
            tempfile.mkdtemp(
                prefix=f".{output_path.name}.scan-", dir=output_path.parent
            )
        )
    except OSError as error:
        raise ScanError(
            "invalid-output-path",
            "could not create output directory",
            stage="publication",
        ) from error
    created_directory_identity: DirectoryIdentity | None = None
    backup_container: Path | None = None
    backup_entry: Path | None = None
    old_target_moved = False
    new_target_published = False
    backup_finalized = False
    parent_fd: int | None = None
    try:
        created_directory_identity = _directory_identity(staging_path)
        if not _directory_matches_identity(
            output_path.parent, output_parent_identity
        ):
            raise ScanError(
                "unsafe-output-path",
                "output parent changed during staging",
                stage="publication",
            )
        counts, source, run = scan_to_staging(
            input_path,
            staging_path,
            work_metadata=metadata,
            start_marker=start_marker,
            end_marker=end_marker,
        )
        artifact_identities = _verify_staging(
            staging_path,
            run,
            source=source,
            work_metadata=metadata,
            start_marker=start_marker,
            end_marker=end_marker,
        )
        if _directory_identity(staging_path) != created_directory_identity:
            raise _verification_failed()
        if not _directory_matches_identity(
            output_path.parent, output_parent_identity
        ):
            raise ScanError(
                "unsafe-output-path",
                "output parent changed before publication",
                stage="publication",
            )

        parent_fd = _open_parent_descriptor(
            output_path.parent,
            output_parent_identity,
        )

        if existing_target is not None:
            if not _target_still_matches(output_path, existing_target):
                raise ScanError(
                    "unsafe-output-path",
                    "output directory changed before publication",
                    stage="publication",
                )
            backup_container = _make_private_container(
                output_path,
                "backup",
                parent_fd=parent_fd,
            )
            backup_entry = backup_container / "entry"
            try:
                _transaction_rename_no_replace(
                    output_path,
                    backup_entry,
                    output_path.parent,
                    parent_fd,
                )
            except OSError as error:
                raise ScanError(
                    "invalid-output-path",
                    "could not preserve existing output directory",
                    stage="publication",
                ) from error
            old_target_moved = True
            parent_path_status = _anchored_parent_status(
                output_path.parent,
                output_parent_identity,
            )
            if parent_path_status != "current":
                parent_error = ScanError(
                    "unsafe-output-path",
                    "output parent changed during publication",
                    stage="publication",
                )
                parent_error.details["parentPathStatus"] = parent_path_status
                parent_error.details["retentionScope"] = "original-parent"
                raise parent_error
            if _directory_identity(backup_entry) != existing_target.identity:
                raise ScanError(
                    "unsafe-output-path",
                    "output directory changed during publication",
                    stage="publication",
                )
        try:
            _transaction_rename_no_replace(
                staging_path,
                output_path,
                output_path.parent,
                parent_fd,
            )
        except OSError as error:
            raise ScanError(
                "invalid-output-path",
                "could not publish output directory",
                stage="publication",
            ) from error
        new_target_published = True
        parent_path_status = _anchored_parent_status(
            output_path.parent,
            output_parent_identity,
        )
        if parent_path_status != "current":
            parent_error = ScanError(
                "unsafe-output-path",
                "output parent changed during publication",
                stage="publication",
            )
            parent_error.details["parentPathStatus"] = parent_path_status
            parent_error.details["retentionScope"] = "original-parent"
            raise parent_error
        if _directory_identity(output_path) != created_directory_identity:
            raise _verification_failed()
        _verify_staging(
            output_path,
            run,
            source=source,
            work_metadata=metadata,
            start_marker=start_marker,
            end_marker=end_marker,
            expected_identities=artifact_identities,
        )
        parent_path_status = _anchored_parent_status(
            output_path.parent,
            output_parent_identity,
        )
        if parent_path_status != "current":
            parent_error = _verification_failed()
            parent_error.details["parentPathStatus"] = parent_path_status
            parent_error.details["retentionScope"] = "original-parent"
            raise parent_error

        if backup_container is not None and backup_entry is not None:
            try:
                _remove_owned_backup(
                    backup_container,
                    backup_entry,
                    existing_target.identity,
                )
            except (OSError, ScanError):
                cleanup_error = _cleanup_failed(
                    output_path,
                    retained_path_basename=backup_container.name,
                )
                cleanup_error.details["retainedBackupBasename"] = (
                    backup_container.name
                )
                parent_path_status = _anchored_parent_status(
                    output_path.parent,
                    output_parent_identity,
                )
                if parent_path_status != "current":
                    cleanup_error.details["parentPathStatus"] = (
                        parent_path_status
                    )
                    cleanup_error.details["retentionScope"] = "original-parent"
                    if parent_fd is not None:
                        cleanup_error.details["officialPathStatus"] = (
                            _entry_status_at_anchor(
                                output_path,
                                output_path.parent,
                                parent_fd,
                            )
                        )
                raise cleanup_error from None
            backup_finalized = True
            if _directory_identity(output_path) != created_directory_identity:
                raise _verification_failed()
            # _verify_staging begins with the exact five-entry inventory check.
            _verify_staging(
                output_path,
                run,
                source=source,
                work_metadata=metadata,
                start_marker=start_marker,
                end_marker=end_marker,
                expected_identities=artifact_identities,
            )
            if not _directory_matches_identity(
                output_path, created_directory_identity
            ):
                raise _verification_failed()
        parent_path_status = _anchored_parent_status(
            output_path.parent,
            output_parent_identity,
        )
        if parent_path_status != "current":
            parent_error = _verification_failed()
            parent_error.details["parentPathStatus"] = parent_path_status
            parent_error.details["retentionScope"] = "original-parent"
            raise parent_error
        return {
            "candidateCount": counts["candidateCount"],
            "outputName": output_path.name,
            "resolvedMinuteCount": counts["resolvedMinuteCount"],
            "status": "complete",
        }
    except Exception as caught_error:
        if backup_finalized and new_target_published:
            parent_path_status = _anchored_parent_status(
                output_path.parent,
                output_parent_identity,
            )
            if parent_path_status != "current":
                parent_error = (
                    caught_error
                    if isinstance(caught_error, ScanError)
                    else _verification_failed()
                )
                parent_error.details["parentPathStatus"] = parent_path_status
                parent_error.details["retentionScope"] = "original-parent"
                parent_error.details["officialPathStatus"] = (
                    _entry_status_at_anchor(
                        output_path,
                        output_path.parent,
                        parent_fd,
                    )
                    if parent_fd is not None
                    else _path_entry_status(output_path)
                )
                raise parent_error from caught_error
            if not _directory_matches_identity(
                output_path, created_directory_identity
            ):
                replacement_error = _verification_failed()
                replacement_error.details["officialPathStatus"] = (
                    _path_entry_status(output_path)
                )
                raise replacement_error from caught_error
            error = _staging_failure(caught_error)
            try:
                retention = _retain_path_entry_in_quarantine(
                    output_path,
                    created_directory_identity,
                    parent_fd=parent_fd,
                    parent_identity=output_parent_identity,
                )
            except ScanError as cleanup_error:
                raise cleanup_error from caught_error
            _attach_retention(error, retention)
            if error is caught_error:
                raise
            raise error from caught_error
        if (
            isinstance(caught_error, ScanError)
            and caught_error.code == "scan-cleanup-failed"
            and new_target_published
        ):
            raise
        error = _staging_failure(caught_error)

        if new_target_published:
            try:
                retention = _retain_path_entry_in_quarantine(
                    output_path,
                    created_directory_identity,
                    parent_fd=parent_fd,
                    parent_identity=output_parent_identity,
                )
            except ScanError as cleanup_error:
                if backup_container is not None:
                    cleanup_error.details["retainedBackupBasename"] = (
                        backup_container.name
                    )
                raise
            _attach_retention(error, retention)

        if old_target_moved and backup_entry is not None:
            try:
                _transaction_rename_no_replace(
                    backup_entry,
                    output_path,
                    output_path.parent,
                    parent_fd,
                )
                old_target_moved = False
                if backup_container is not None:
                    if parent_fd is None:
                        backup_container.rmdir()
                    else:
                        os.rmdir(backup_container.name, dir_fd=parent_fd)
            except OSError:
                if backup_container is not None:
                    error.details["retainedBackupBasename"] = backup_container.name

        if not new_target_published:
            try:
                retention = _retain_path_entry_in_quarantine(
                    staging_path,
                    created_directory_identity,
                    parent_fd=parent_fd,
                    parent_identity=output_parent_identity,
                )
            except ScanError as cleanup_error:
                cleanup_error.details["retainedPathBasename"] = staging_path.name
                if backup_container is not None and old_target_moved:
                    cleanup_error.details["retainedBackupBasename"] = (
                        backup_container.name
                    )
                elif "retainedBackupBasename" in error.details:
                    cleanup_error.details["retainedBackupBasename"] = (
                        error.details["retainedBackupBasename"]
                    )
                raise
            _attach_retention(error, retention)

        if backup_container is not None and not old_target_moved:
            try:
                if parent_fd is None:
                    backup_container.rmdir()
                else:
                    os.rmdir(backup_container.name, dir_fd=parent_fd)
            except FileNotFoundError:
                pass
            except OSError:
                error.details["retainedBackupBasename"] = backup_container.name
        parent_path_status = _anchored_parent_status(
            output_path.parent,
            output_parent_identity,
        )
        if parent_fd is not None:
            error.details["officialPathStatus"] = _entry_status_at_anchor(
                output_path,
                output_path.parent,
                parent_fd,
            )
        else:
            error.details["officialPathStatus"] = _path_entry_status(output_path)
        if parent_path_status != "current":
            error.details["parentPathStatus"] = parent_path_status
            error.details.setdefault(
                "retentionScope",
                "original-parent" if parent_fd is not None else "path-based-parent",
            )
        if error is caught_error:
            raise
        raise error from caught_error
    finally:
        if parent_fd is not None:
            os.close(parent_fd)

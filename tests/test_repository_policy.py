from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path, PurePosixPath
from typing import Mapping


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
EBOOK_OR_ARCHIVE_SUFFIXES = {
    ".7z",
    ".azw",
    ".azw3",
    ".bz2",
    ".djvu",
    ".doc",
    ".docx",
    ".epub",
    ".fb2",
    ".gz",
    ".htm",
    ".html",
    ".mobi",
    ".odt",
    ".pdf",
    ".rar",
    ".rtf",
    ".tar",
    ".xz",
    ".zip",
}
RAW_TEXT_SUFFIXES = {".text", ".txt", ".utf-8", ".utf8"}
ALLOWED_DATA_ROOT_PLACEHOLDER_BYTES = {
    PurePosixPath("manifests/.gitkeep"): b"",
    PurePosixPath("manifests/README.md"): (
        b"# Manifests\n\nNo Gate 3 manifest schema is approved.\n"
    ),
    PurePosixPath("artifacts/.gitkeep"): b"",
    PurePosixPath("artifacts/README.md"): (
        b"# Artifacts\n\nNo Gate 3 artifact schema is approved.\n"
    ),
    PurePosixPath("releases/.gitkeep"): b"",
    PurePosixPath("releases/README.md"): (
        b"# Releases\n\nNo public corpus release is approved.\n"
    ),
}
APPROVED_SYNTHETIC_FIXTURE_SHA256 = {
    PurePosixPath("tests/fixtures/extract/times.txt"): (
        "dc5cd733c1d408a52912d1bae3a8dc6ba03d555a30f283b930613955deb4b806"
    ),
    PurePosixPath("tests/fixtures/normalize/missing-start.txt"): (
        "8351d668433abbf4591961d7ca9d6b052a814370788b415116630540613f9ae8"
    ),
    PurePosixPath("tests/fixtures/normalize/valid.txt"): (
        "5e4fb58e2bad12b054d129295152fba067b6147b7f11e2fcc83799ab511ccfb1"
    ),
}


def tracked_paths() -> list[PurePosixPath]:
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


def tracked_index_files() -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    for path in tracked_paths():
        result = subprocess.run(
            ["git", "show", f":{path}"],
            cwd=REPOSITORY_ROOT,
            check=True,
            capture_output=True,
        )
        files[str(path)] = result.stdout
    return files


def is_synthetic_text_fixture(path: PurePosixPath, content: bytes) -> bool:
    expected_hash = APPROVED_SYNTHETIC_FIXTURE_SHA256.get(path)
    return (
        expected_hash is not None
        and hashlib.sha256(content).hexdigest() == expected_hash
    )


def policy_violations(files: Mapping[str, bytes]) -> list[str]:
    violations: list[str] = []
    for raw_path, content in files.items():
        path = PurePosixPath(raw_path)
        if path.parts[:1] in {("manifests",), ("artifacts",), ("releases",)}:
            expected_placeholder = ALLOWED_DATA_ROOT_PLACEHOLDER_BYTES.get(path)
            if expected_placeholder is None or content != expected_placeholder:
                violations.append(raw_path)
            continue
        if path.suffix.lower() in EBOOK_OR_ARCHIVE_SUFFIXES:
            violations.append(raw_path)
            continue
        if path.suffix.lower() in RAW_TEXT_SUFFIXES and not is_synthetic_text_fixture(
            path, content
        ):
            violations.append(raw_path)
    return sorted(violations)


def test_local_workspace_is_ignored_and_never_tracked() -> None:
    probe = ".local/source/repository-policy-probe.txt"
    ignored = subprocess.run(
        ["git", "check-ignore", "--quiet", probe],
        cwd=REPOSITORY_ROOT,
        check=False,
    )

    assert ignored.returncode == 0, ".local/ must be ignored by repository policy"
    assert not [path for path in tracked_paths() if path.parts[0] == ".local"]


def test_tracked_repository_content_satisfies_boundary_policy() -> None:
    violations = policy_violations(tracked_index_files())

    assert violations == [], f"disallowed tracked source or release files: {violations}"


def test_closed_gate_4_rejects_release_artifacts_regardless_of_format() -> None:
    files = {
        "releases/excerpts.csv": b"minute,excerpt\n01:17,synthetic text\n",
        "releases/corpus.ndjson": b'{"minute":"01:17"}\n',
        "releases/package.bin": b"opaque bytes",
        "releases/nested/README.md": b"not an approved root placeholder\n",
    }

    assert policy_violations(files) == sorted(files)


def test_closed_gate_4_allows_only_explicit_root_placeholders() -> None:
    files = {
        "releases/README.md": (
            b"# Releases\n\nNo public corpus release is approved.\n"
        ),
        "releases/.gitkeep": b"",
    }

    assert policy_violations(files) == []


def test_release_placeholders_must_match_the_approved_bytes() -> None:
    files = {
        "releases/README.md": b"Synthetic excerpt: at 1:17 a.m.\n",
        "releases/.gitkeep": b"hidden release data\n",
    }

    assert policy_violations(files) == sorted(files)


def test_ebook_and_raw_text_rules_cannot_be_bypassed_by_directory() -> None:
    files = {
        "book.epub": b"binary",
        "data/raw-book.txt": b"plain ebook text",
        "sources/book.zip": b"archive",
        "sources/book.utf8": b"plain ebook text",
        "assets/book.html": b"<p>ebook text</p>",
    }

    assert policy_violations(files) == sorted(files)


def test_text_fixture_exemption_requires_verified_synthetic_content() -> None:
    files = {
        "tests/fixtures/example.txt": b"an unlabeled literary passage",
        "other/synthetic.txt": b"synthetic fixture\n",
    }

    assert policy_violations(files) == sorted(files)


def test_synthetic_label_cannot_self_approve_copied_fixture_prose() -> None:
    files = {
        "tests/fixtures/normalize/valid.txt": (
            b"Synthetic metadata only.\nCopied literary prose follows.\n"
        ),
        "tests/fixtures/new.txt": b"synthetic fixture\n",
    }

    assert policy_violations(files) == sorted(files)


def test_closed_gate_3_rejects_payloads_in_all_reserved_data_roots() -> None:
    files = {
        "manifests/book.json": b'{"excerpt":"hidden payload"}\n',
        "artifacts/corpus.jsonl": b'{"excerpt":"hidden payload"}\n',
        "artifacts/book": b"extensionless hidden payload\n",
        "releases/book.json": b'{"excerpt":"hidden payload"}\n',
    }

    assert policy_violations(files) == sorted(files)


def test_closed_gate_3_allows_only_exact_root_placeholders() -> None:
    files = {
        "manifests/.gitkeep": b"",
        "manifests/README.md": b"# Manifests\n\nNo Gate 3 manifest schema is approved.\n",
        "artifacts/.gitkeep": b"",
        "artifacts/README.md": b"# Artifacts\n\nNo Gate 3 artifact schema is approved.\n",
    }

    assert policy_violations(files) == []


def test_gate_3_placeholders_cannot_hide_payloads_or_move_into_nested_paths() -> None:
    files = {
        "manifests/.gitkeep": b"hidden payload\n",
        "artifacts/README.md": b"# Artifacts\n\nhidden payload\n",
        "manifests/nested/README.md": b"# Manifests\n\nNo Gate 3 manifest schema is approved.\n",
    }

    assert policy_violations(files) == sorted(files)

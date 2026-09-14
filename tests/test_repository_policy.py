from __future__ import annotations

import re
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
ALLOWED_RELEASE_PLACEHOLDERS = {
    PurePosixPath("releases/.gitkeep"),
    PurePosixPath("releases/README.md"),
}
ALLOWED_MANIFEST_PLACEHOLDERS = {
    PurePosixPath("manifests/.gitkeep"),
    PurePosixPath("manifests/README.md"),
}
ALLOWED_MANIFEST_SUFFIXES = {".json", ".jsonl", ".rdf"}
PATH_LIST_NAME = re.compile(r"[a-z0-9][a-z0-9._-]*-paths\.txt")
PATH_LIST_LINE = re.compile(r"[A-Za-z0-9._/-]+\.txt")


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
    if path.parts[:2] != ("tests", "fixtures") or len(content) > 64 * 1024:
        return False
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        return False
    lowered = text.lower()
    return (
        "synthetic" in lowered
        and "project gutenberg license" not in lowered
        and any(
            marker in lowered
            for marker in ("synthetic metadata", "ebook synthetic", "synthetic fixture")
        )
    )


def is_approved_path_list(path: PurePosixPath, content: bytes) -> bool:
    if (
        path.parts[:1] != ("manifests",)
        or PATH_LIST_NAME.fullmatch(path.name) is None
    ):
        return False
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        return False
    lines = text.splitlines()
    return bool(lines) and len(lines) == len(set(lines)) and all(
        line == line.strip()
        and PATH_LIST_LINE.fullmatch(line) is not None
        and ".." not in PurePosixPath(line).parts
        and not PurePosixPath(line).is_absolute()
        for line in lines
    )


def policy_violations(files: Mapping[str, bytes]) -> list[str]:
    violations: list[str] = []
    for raw_path, content in files.items():
        path = PurePosixPath(raw_path)
        if path.parts[:1] == ("releases",):
            if path not in ALLOWED_RELEASE_PLACEHOLDERS:
                violations.append(raw_path)
            continue
        if path.parts[:1] == ("manifests",):
            if (
                path in ALLOWED_MANIFEST_PLACEHOLDERS
                or path.suffix.lower() in ALLOWED_MANIFEST_SUFFIXES
                or is_approved_path_list(path, content)
            ):
                continue
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
        "releases/README.md": b"No release is approved.\n",
        "releases/.gitkeep": b"",
    }

    assert policy_violations(files) == []


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


def test_planned_manifest_metadata_and_named_path_lists_are_allowed() -> None:
    files = {
        "manifests/pilot.json": b'{"sourceId":"synthetic_123"}\n',
        "manifests/pilot.jsonl": b'{"sourceId":"synthetic_123"}\n',
        "manifests/catalog.rdf": b"<rdf:RDF></rdf:RDF>\n",
        "manifests/pilot-approved-paths.txt": (
            b"1/2/3/123/123-0.txt\n4/5/6/456/456.txt\n"
        ),
    }

    assert policy_violations(files) == []


def test_named_manifest_path_list_rejects_prose_or_unsafe_paths() -> None:
    files = {
        "manifests/pilot-approved-paths.txt": (
            b"../private/book.txt\nThis is copied literary prose.\n"
        )
    }

    assert policy_violations(files) == ["manifests/pilot-approved-paths.txt"]


def test_manifest_directory_rejects_unplanned_metadata_formats() -> None:
    files = {"manifests/pilot.csv": b"sourceId,path\nsynthetic_123,book.txt\n"}

    assert policy_violations(files) == ["manifests/pilot.csv"]

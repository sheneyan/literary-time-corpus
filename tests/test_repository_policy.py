from __future__ import annotations

import json
import subprocess
from pathlib import Path, PurePosixPath
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
GENERATED_ZONES = {"manifests", "artifacts", "releases"}
LIKELY_EBOOK_SUFFIXES = {
    ".azw",
    ".azw3",
    ".epub",
    ".htm",
    ".html",
    ".mobi",
    ".pdf",
    ".rtf",
    ".txt",
    ".zip",
}
EXCERPT_FIELDS = {"excerpt", "quoteBefore", "quoteTime", "quoteAfter", "matchedText"}


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


def contains_excerpt_field(value: Any) -> bool:
    if isinstance(value, dict):
        return bool(EXCERPT_FIELDS.intersection(value)) or any(
            contains_excerpt_field(item) for item in value.values()
        )
    if isinstance(value, list):
        return any(contains_excerpt_field(item) for item in value)
    return False


def test_local_workspace_is_ignored_and_never_tracked() -> None:
    probe = ".local/source/repository-policy-probe.txt"
    ignored = subprocess.run(
        ["git", "check-ignore", "--quiet", probe],
        cwd=REPOSITORY_ROOT,
        check=False,
    )

    assert ignored.returncode == 0, ".local/ must be ignored by repository policy"
    assert not [path for path in tracked_paths() if path.parts[0] == ".local"]


def test_generated_zones_do_not_track_likely_source_ebooks() -> None:
    violations = [
        str(path)
        for path in tracked_paths()
        if path.parts[0] in GENERATED_ZONES
        and path.suffix.lower() in LIKELY_EBOOK_SUFFIXES
    ]

    assert violations == [], f"likely source ebooks are tracked: {violations}"


def test_releases_do_not_contain_unapproved_excerpt_artifacts() -> None:
    violations: list[str] = []
    for path in tracked_paths():
        if path.parts[0] != "releases" or path.suffix.lower() not in {".json", ".jsonl"}:
            continue
        full_path = REPOSITORY_ROOT / path
        text = full_path.read_text(encoding="utf-8")
        if path.suffix.lower() == ".json":
            documents = [json.loads(text)]
        else:
            documents = [
                json.loads(line) for line in text.splitlines() if line.strip()
            ]
        if any(contains_excerpt_field(document) for document in documents):
            violations.append(str(path))

    assert violations == [], (
        "Gate 4 has approved no public excerpt artifacts; tracked release data found: "
        f"{violations}"
    )

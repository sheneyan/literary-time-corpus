from __future__ import annotations

import ipaddress
import os
import re
import shutil
import stat
import tempfile
import unicodedata
from pathlib import Path
from urllib.parse import urlsplit

from literary_time_corpus.candidate import (
    WORK_METADATA_SCHEMA_VERSION,
    candidate_record_violations,
    work_metadata_violations,
)
from literary_time_corpus.extract import ExtractionError, extract_candidates
from literary_time_corpus.io import write_json_atomic, write_jsonl_atomic
from literary_time_corpus.normalize import NormalizationError, normalize_bytes
from literary_time_corpus.normalized import normalized_record_violations
from literary_time_corpus.report import ReportError, build_report
from literary_time_corpus.review import render_review_markdown


SCAN_SCHEMA_VERSION = "scan-run-v1"
SCAN_VERSION = "scan-v1"
ARTIFACT_NAMES = (
    "normalized.json",
    "candidates.jsonl",
    "report.json",
    "review.md",
    "run.json",
)
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
    def __init__(self, code: str, message: str, *, stage: str):
        super().__init__(message)
        self.code = code
        self.details = {"stage": stage}


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


def scan_to_staging(
    input_path: Path,
    staging_path: Path,
    *,
    work_metadata: dict[str, object],
    start_marker: str | None,
    end_marker: str | None,
) -> dict[str, object]:
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
    (staging_path / "review.md").write_bytes(
        render_review_markdown(candidates, work_metadata)
    )
    run = {
        "bodyBoundary": {
            "endMarker": end_marker,
            "mode": "markers" if start_marker is not None else "full-file",
            "startMarker": start_marker,
        },
        "candidateCount": report["candidateCount"],
        "inputName": input_path.name,
        "resolvedMinuteCount": report["resolvedMinuteCount"],
        "scanVersion": SCAN_VERSION,
        "schemaVersion": SCAN_SCHEMA_VERSION,
        "status": "complete",
        "workMetadata": work_metadata,
    }
    write_json_atomic(staging_path / "run.json", run)
    return {
        "candidateCount": report["candidateCount"],
        "resolvedMinuteCount": report["resolvedMinuteCount"],
    }


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
    del force  # Task 4 completes guarded replacement of existing directories.
    metadata = build_work_metadata(
        input_path,
        title=title,
        author=author,
        source_url=source_url,
    )
    if output_path.exists() or output_path.is_symlink():
        raise ScanError(
            "output-exists",
            "output directory already exists",
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

    try:
        counts = scan_to_staging(
            input_path,
            staging_path,
            work_metadata=metadata,
            start_marker=start_marker,
            end_marker=end_marker,
        )
        if {path.name for path in staging_path.iterdir()} != set(ARTIFACT_NAMES):
            raise ScanError(
                "scan-verification-failed",
                "scan artifact inventory is incomplete",
                stage="verification",
            )
        try:
            staging_path.rename(output_path)
        except OSError as error:
            raise ScanError(
                "invalid-output-path",
                "could not publish output directory",
                stage="publication",
            ) from error
        return {
            "candidateCount": counts["candidateCount"],
            "outputName": output_path.name,
            "resolvedMinuteCount": counts["resolvedMinuteCount"],
            "status": "complete",
        }
    finally:
        if staging_path.exists():
            shutil.rmtree(staging_path)

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest


ARTIFACTS = {
    "normalized.json",
    "candidates.jsonl",
    "report.json",
    "review.md",
    "run.json",
}


def read_rows(destination: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in (destination / "candidates.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]


def test_scan_help_exposes_the_public_txt_interface(run_ltc) -> None:
    result = run_ltc("scan", "--help")

    assert result.returncode == 0
    assert result.stderr == ""
    for option in (
        "--output",
        "--title",
        "--author",
        "--source-url",
        "--start-marker",
        "--end-marker",
        "--force",
    ):
        assert option in result.stdout


def test_scan_creates_the_public_artifact_inventory(run_ltc, tmp_path: Path) -> None:
    source = tmp_path / "my-novel.txt"
    destination = tmp_path / "scan"
    source.write_text("At 13:15 the café bell rang.\n", encoding="utf-8")

    result = run_ltc("scan", source, "--output", destination)

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert {path.name for path in destination.iterdir()} == ARTIFACTS
    assert result.stdout == (
        '{"candidateCount":1,"outputName":"scan",'
        '"resolvedMinuteCount":1,"status":"complete"}\n'
    )
    report = json.loads((destination / "report.json").read_text(encoding="utf-8"))
    assert report["candidateCount"] == 1
    assert report["resolvedMinuteCount"] == 1


def test_scan_uses_documented_metadata_fallbacks(run_ltc, tmp_path: Path) -> None:
    source = tmp_path / "unfinished-title.txt"
    destination = tmp_path / "scan"
    source.write_text("At 13:15 the bell rang.\n", encoding="utf-8")

    result = run_ltc("scan", source, "--output", destination)

    assert result.returncode == 0, result.stderr
    expected = {
        "author": "unknown",
        "metadataComplete": False,
        "schemaVersion": "scan-work-metadata-v1",
        "sourceUrl": None,
        "title": "unfinished-title",
    }
    assert read_rows(destination)[0]["workMetadata"] == expected
    assert json.loads((destination / "run.json").read_text())["workMetadata"] == expected


def test_scan_records_explicit_metadata_without_changing_candidate_identity(
    run_ltc, tmp_path: Path
) -> None:
    source = tmp_path / "novel.txt"
    destination = tmp_path / "scan"
    normalized = tmp_path / "normalized-low-level.json"
    candidates = tmp_path / "candidates-low-level.jsonl"
    source.write_text("At 13:15 the bell rang.\n", encoding="utf-8")

    result = run_ltc(
        "scan",
        source,
        "--output",
        destination,
        "--title",
        "Example Book",
        "--author",
        "Example Author",
        "--source-url",
        "https://example.org/book",
    )
    assert run_ltc("normalize", "--input", source, "--output", normalized).returncode == 0
    assert run_ltc("extract", "--input", normalized, "--output", candidates).returncode == 0

    assert result.returncode == 0, result.stderr
    row = read_rows(destination)[0]
    assert row["workMetadata"] == {
        "author": "Example Author",
        "metadataComplete": True,
        "schemaVersion": "scan-work-metadata-v1",
        "sourceUrl": "https://example.org/book",
        "title": "Example Book",
    }
    lower_level = json.loads(candidates.read_text().splitlines()[0])
    assert row["candidateId"] == lower_level["candidateId"]


def test_scan_passes_literal_markers_to_normalization(run_ltc, tmp_path: Path) -> None:
    source = tmp_path / "marked.txt"
    destination = tmp_path / "scan"
    source.write_text(
        "Header 11:11\nBEGIN\nPréface 😀 at 13:15.\nEND\nFooter 22:22\n",
        encoding="utf-8",
    )

    result = run_ltc(
        "scan",
        source,
        "--output",
        destination,
        "--start-marker",
        "BEGIN",
        "--end-marker",
        "END",
    )

    assert result.returncode == 0, result.stderr
    normalized = json.loads((destination / "normalized.json").read_text())
    assert normalized["analysisText"] == "Préface 😀 at 13:15."
    assert [row["matchedText"] for row in read_rows(destination)] == ["13:15"]


def test_scan_no_time_input_succeeds_with_empty_candidates(
    run_ltc, tmp_path: Path
) -> None:
    source = tmp_path / "quiet.txt"
    destination = tmp_path / "scan"
    source.write_text("The synthetic room stayed quiet.\n", encoding="utf-8")

    result = run_ltc("scan", source, "--output", destination)

    assert result.returncode == 0, result.stderr
    assert (destination / "candidates.jsonl").read_bytes() == b""
    report = json.loads((destination / "report.json").read_text())
    assert report["candidateCount"] == report["resolvedMinuteCount"] == 0
    assert json.loads(result.stdout)["candidateCount"] == 0


def test_scan_preserves_multibyte_utf8_offsets(run_ltc, tmp_path: Path) -> None:
    source = tmp_path / "multibyte.txt"
    destination = tmp_path / "scan"
    text = "序章 café 😀 — at 13:15 the bell rang.\n"
    source.write_text(text, encoding="utf-8")

    result = run_ltc("scan", source, "--output", destination)

    assert result.returncode == 0, result.stderr
    row = read_rows(destination)[0]
    start = len(text[: text.index("13:15")].encode("utf-8"))
    assert row["matchStartByte"] == start
    assert row["matchEndByte"] == start + len(b"13:15")
    assert text.encode("utf-8")[row["matchStartByte"] : row["matchEndByte"]] == b"13:15"


def test_scan_basic_outputs_are_byte_deterministic(run_ltc, tmp_path: Path) -> None:
    first_source = tmp_path / "first" / "novel.txt"
    second_source = tmp_path / "second" / "novel.txt"
    first_source.parent.mkdir()
    second_source.parent.mkdir()
    raw = "At 13:15 the café bell rang.\n".encode()
    first_source.write_bytes(raw)
    second_source.write_bytes(raw)
    first = tmp_path / "first-scan"
    second = tmp_path / "second-scan"

    first_result = run_ltc("scan", first_source, "--output", first)
    second_result = run_ltc("scan", second_source, "--output", second)

    assert first_result.returncode == second_result.returncode == 0
    assert {
        name: hashlib.sha256((first / name).read_bytes()).hexdigest()
        for name in ARTIFACTS
    } == {
        name: hashlib.sha256((second / name).read_bytes()).hexdigest()
        for name in ARTIFACTS
    }


@pytest.mark.parametrize(
    ("arguments", "secret"),
    [
        (("--title", "   "), None),
        (("--author", "\t"), None),
        (("--source-url", "relative/book"), None),
        (("--source-url", "ftp://example.org/book"), None),
        (("--source-url", "https:///book"), None),
        (("--source-url", "https://alice@example.org/book"), "alice"),
        (("--source-url", "https://alice:hunter2@example.org/book"), "hunter2"),
        (("--source-url", " https://example.org/book"), None),
        (("--source-url", "https://example.org/book "), None),
        (("--source-url", "https://exa mple.org/book"), None),
        (("--source-url", "https://example.org/book\nprivate"), "private"),
        (("--source-url", "https://example.org/%zz"), None),
        (("--source-url", "https://exa%6dple.org/book"), None),
        (("--source-url", "https://[example.org/book"), None),
        (("--source-url", "https://-bad.example/book"), None),
        (("--source-url", "https://bad..example/book"), None),
    ],
)
def test_scan_rejects_invalid_metadata_without_output_or_credential_echo(
    run_ltc, tmp_path: Path, arguments: tuple[str, str], secret: str | None
) -> None:
    source = tmp_path / "novel.txt"
    destination = tmp_path / "scan"
    source.write_text("At 13:15 the bell rang.\n", encoding="utf-8")

    result = run_ltc("scan", source, "--output", destination, *arguments)

    assert result.returncode == 2
    assert result.stdout == ""
    error = json.loads(result.stderr)["error"]
    assert error["code"] == "invalid-scan-metadata"
    assert error["details"] == {"stage": "metadata"}
    assert not destination.exists()
    supplied_value = arguments[1]
    if supplied_value.strip():
        assert supplied_value not in result.stderr
    if secret is not None:
        assert secret not in result.stderr


def test_scan_existing_destination_is_a_controlled_error(
    run_ltc, tmp_path: Path
) -> None:
    source = tmp_path / "novel.txt"
    destination = tmp_path / "scan"
    source.write_text("At 13:15 the bell rang.\n", encoding="utf-8")
    destination.mkdir()
    sentinel = destination / "keep.txt"
    sentinel.write_text("keep", encoding="utf-8")

    result = run_ltc("scan", source, "--output", destination)

    assert result.returncode == 2
    error = json.loads(result.stderr)["error"]
    assert error["details"]["stage"] == "publication"
    assert sentinel.read_text() == "keep"


def test_scan_success_stdout_does_not_disclose_paths_or_source_text(
    run_ltc, tmp_path: Path
) -> None:
    source = tmp_path / "private-input-name.txt"
    destination = tmp_path / "public-output-name"
    excerpt = "Private synthetic excerpt at 13:15."
    source.write_text(excerpt, encoding="utf-8")

    result = run_ltc("scan", source, "--output", destination)

    assert result.returncode == 0, result.stderr
    assert str(source) not in result.stdout
    assert str(destination) not in result.stdout
    assert excerpt not in result.stdout
    assert "public-output-name" in result.stdout

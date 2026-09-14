from __future__ import annotations

import getpass
import hashlib
import json
import re
import socket
from pathlib import Path

import pytest

import literary_time_corpus.scan as scan_module
from literary_time_corpus.cli import main
from literary_time_corpus.review import render_review_markdown


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


def candidate_with_context(
    candidate: dict[str, object], context_before: str, context_after: str = ""
) -> dict[str, object]:
    updated = dict(candidate)
    matched_text = updated["matchedText"]
    assert isinstance(matched_text, str)
    context = context_before + matched_text + context_after
    match_start = len(context_before.encode("utf-8"))
    match_end = len((context_before + matched_text).encode("utf-8"))
    updated.update(
        {
            "context": context,
            "excerpt": context,
            "excerptStartByte": 0,
            "excerptEndByte": len(context.encode("utf-8")),
            "matchStartByte": match_start,
            "matchEndByte": match_end,
            "quoteBefore": context_before,
            "quoteTime": matched_text,
            "quoteAfter": context_after,
        }
    )
    resolution = updated["contextualResolution"]
    assert isinstance(resolution, dict)
    updated["contextualResolution"] = {
        **resolution,
        "evidenceStartByte": match_start,
        "evidenceEndByte": match_end,
        "evidenceText": matched_text,
    }
    identity = "\0".join(
        (
            str(updated["sourceId"]),
            str(updated["analysisTextSha256"]),
            str(match_start),
            str(match_end),
        )
    )
    updated["candidateId"] = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    return updated


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


def test_scan_review_groups_candidates_and_renders_complete_safe_details(
    run_ltc, tmp_path: Path
) -> None:
    source = tmp_path / "private-input.txt"
    destination = tmp_path / "scan"
    source_url = "https://example.org/books/public.txt"
    source.write_text(
        "序章 café 😀 ```notes``` at 13:15; then 7:05; "
        "finally about three o'clock.\n",
        encoding="utf-8",
    )

    result = run_ltc(
        "scan",
        source,
        "--output",
        destination,
        "--title",
        "A #Title [draft] *one* `tick`",
        "--author",
        "A_B | Co.",
        "--source-url",
        source_url,
    )

    assert result.returncode == 0, result.stderr
    candidates = read_rows(destination)
    review_bytes = (destination / "review.md").read_bytes()
    review = review_bytes.decode("utf-8")
    expected_ids = [
        candidate["candidateId"]
        for precision in (
            "exact-minute-resolved",
            "exact-minute-ambiguous",
            "approximate",
        )
        for candidate in candidates
        if candidate["precision"] == precision
    ]

    assert review.startswith("# Literary time candidate review\n")
    assert "Title: A \\#Title \\[draft\\] \\*one\\* \\`tick\\`" in review
    assert "Author: A\\_B \\| Co\\." in review
    assert "Metadata complete: yes" in review
    assert "Candidate count: 3" in review
    assert "This file is a review view, not a review record." in review
    assert "Candidates are not approved for publication." in review
    assert "The user is responsible for permission to process the input text." in review
    assert review.index("## Exact-minute resolved") < review.index(
        "## Exact-minute ambiguous"
    )
    assert review.index("## Exact-minute ambiguous") < review.index(
        "## Approximate or excluded"
    )
    assert expected_ids == re.findall(r"Candidate ID: `([0-9a-f]{64})`", review)
    for candidate in candidates:
        assert review.count(f"Candidate ID: `{candidate['candidateId']}`") == 1
        assert candidate["context"] in review
        assert candidate["matchedText"] in review
        assert all(value in review for value in candidate["normalizedTimes"])
        assert candidate["ruleId"].replace("-", "\\-") in review
        assert all(
            value.replace("-", "\\-") in review
            for value in candidate["warningReasonCodes"]
        )
        assert all(
            value.replace("-", "\\-") in review
            for value in candidate["exclusionReasonCodes"]
        )
    assert "````text\n" in review
    assert "- [ ]" not in review
    assert "- [x]" not in review.lower()
    assert str(source) not in review
    assert str(destination) not in review
    assert getpass.getuser() not in review
    assert socket.gethostname() not in review
    assert source_url not in review
    assert review_bytes.endswith(b"\n")
    assert not review_bytes.endswith(b"\n\n")
    assert b"\r" not in review_bytes


def test_scan_review_renders_all_empty_sections(run_ltc, tmp_path: Path) -> None:
    source = tmp_path / "quiet.txt"
    destination = tmp_path / "scan"
    source.write_text("The synthetic room stayed quiet.\n", encoding="utf-8")

    result = run_ltc("scan", source, "--output", destination)

    assert result.returncode == 0, result.stderr
    review = (destination / "review.md").read_text(encoding="utf-8")
    assert "Candidate count: 0" in review
    assert review.count("## Exact-minute resolved") == 1
    assert review.count("## Exact-minute ambiguous") == 1
    assert review.count("## Approximate or excluded") == 1
    assert "Candidate ID:" not in review


def test_scan_review_escapes_inline_metadata_without_changing_fixed_structure(
    run_ltc, tmp_path: Path
) -> None:
    source = tmp_path / "book.txt"
    destination = tmp_path / "scan"
    punctuation = "!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~"
    source.write_text("The bell rang at 13:15.\n", encoding="utf-8")

    result = run_ltc(
        "scan",
        source,
        "--output",
        destination,
        "--title",
        f"Safe title {punctuation}",
        "--author",
        "~~text~~ Author",
    )

    assert result.returncode == 0, result.stderr
    review = (destination / "review.md").read_text(encoding="utf-8")
    escaped_punctuation = "".join(f"\\{character}" for character in punctuation)
    assert f"Title: Safe title {escaped_punctuation}" in review
    assert "Author: \\~\\~text\\~\\~ Author" in review
    assert "~~text~~" not in review
    assert review.count("# Literary time candidate review\n") == 1
    assert review.count("This file is a review view, not a review record.") == 1
    assert review.count("Candidates are not approved for publication.") == 1
    assert (
        review.count("The user is responsible for permission to process the input text.")
        == 1
    )
    assert "13:15" in review


def test_review_renderer_escapes_multiline_rule_and_reason_fields(
    run_ltc, tmp_path: Path
) -> None:
    source = tmp_path / "book.txt"
    destination = tmp_path / "scan"
    source.write_text("café 😀 ```source``` at 13:15.\n", encoding="utf-8")
    result = run_ltc("scan", source, "--output", destination)
    assert result.returncode == 0, result.stderr
    candidate = read_rows(destination)[0]
    candidate["ruleId"] = "rule\n===\t~~name~~"
    candidate["warningReasonCodes"] = ["warning\r\n~~reason~~"]
    candidate["exclusionReasonCodes"] = ["excluded\v\fvalue"]
    metadata = candidate["workMetadata"]
    assert isinstance(metadata, dict)

    review = render_review_markdown([candidate], metadata).decode("utf-8")

    assert "Rule ID: rule\\n\\=\\=\\=\\t\\~\\~name\\~\\~" in review
    assert "Warnings: warning\\r\\n\\~\\~reason\\~\\~" in review
    assert "Exclusions: excluded\\v\\fvalue" in review
    assert candidate["context"] in review
    assert "````text\n" in review
    assert "\n===\n" not in review


@pytest.mark.parametrize(
    ("field", "unsafe_value"),
    [
        ("--title", "Safe title\n==="),
        ("--title", "safe\x1b]8;;https://evil.example\x07link\x1b]8;;\x07"),
        ("--author", "safe\u202eunsafe"),
    ],
)
def test_scan_rejects_unsafe_metadata_controls_without_echo(
    run_ltc, tmp_path: Path, field: str, unsafe_value: str
) -> None:
    source = tmp_path / "book.txt"
    destination = tmp_path / "scan"
    source.write_text("The bell rang at 13:15.\n", encoding="utf-8")

    result = run_ltc(
        "scan", source, "--output", destination, field, unsafe_value
    )

    assert result.returncode == 2
    assert result.stdout == ""
    error = json.loads(result.stderr)["error"]
    assert error["code"] == "invalid-scan-metadata"
    assert error["details"] == {"stage": "metadata"}
    assert unsafe_value not in result.stderr
    assert "evil.example" not in result.stderr
    assert not destination.exists()


def test_scan_allows_zwj_and_zwnj_in_explicit_metadata(
    run_ltc, tmp_path: Path
) -> None:
    source = tmp_path / "book.txt"
    destination = tmp_path / "scan"
    title = "Family 👨‍👩‍👧‍👦 and Persian می‌رود"
    source.write_text("The bell rang at 13:15.\n", encoding="utf-8")

    result = run_ltc(
        "scan", source, "--output", destination, "--title", title
    )

    assert result.returncode == 0, result.stderr
    assert json.loads((destination / "run.json").read_text())["workMetadata"][
        "title"
    ] == title
    assert title in (destination / "review.md").read_text(encoding="utf-8")


@pytest.mark.parametrize("title", ["family👨‍👩‍👧‍👦", "نام‌کتاب"])
def test_scan_allows_zwj_and_zwnj_in_default_filename_stem(
    run_ltc, tmp_path: Path, title: str
) -> None:
    source = tmp_path / f"{title}.txt"
    destination = tmp_path / "scan"
    source.write_text("The bell rang at 13:15.\n", encoding="utf-8")

    result = run_ltc("scan", source, "--output", destination)

    assert result.returncode == 0, result.stderr
    assert json.loads((destination / "run.json").read_text())["workMetadata"][
        "title"
    ] == title
    assert title in (destination / "review.md").read_text(encoding="utf-8")


def test_review_renderer_visibly_encodes_non_whitespace_controls(
    run_ltc, tmp_path: Path
) -> None:
    source = tmp_path / "book.txt"
    destination = tmp_path / "scan"
    source.write_text("The bell rang at 13:15.\n", encoding="utf-8")
    assert run_ltc("scan", source, "--output", destination).returncode == 0
    candidate = read_rows(destination)[0]
    candidate["ruleId"] = "rule\x1b"
    candidate["warningReasonCodes"] = [
        "link\x1b]8;;https://evil.example\x07text\x1b]8;;\x07"
    ]
    candidate["exclusionReasonCodes"] = ["bidi\u202ereason"]
    metadata = candidate["workMetadata"]
    assert isinstance(metadata, dict)

    review = render_review_markdown([candidate], metadata).decode("utf-8")

    assert "Rule ID: rule\\x1b" in review
    assert "Warnings: link\\x1b\\]8\\;\\;https\\:\\/\\/evil\\.example\\x07" in review
    assert "Exclusions: bidi\\u202ereason" in review
    assert "\x1b" not in review
    assert "\x07" not in review
    assert "\u202e" not in review


def test_review_renderer_uses_bounded_alternate_fence_for_long_backtick_run(
    run_ltc, tmp_path: Path
) -> None:
    source = tmp_path / "book.txt"
    destination = tmp_path / "scan"
    source.write_text("The bell rang at 13:15.\n", encoding="utf-8")
    assert run_ltc("scan", source, "--output", destination).returncode == 0
    original = read_rows(destination)[0]
    candidate = candidate_with_context(original, "`" * 255 + "\n# injected\n")
    metadata = candidate["workMetadata"]
    assert isinstance(metadata, dict)

    review = render_review_markdown([candidate], metadata).decode("utf-8")

    assert f"~~~text\n{candidate['context']}\n~~~" in review
    assert read_rows(destination)[0]["context"] == original["context"]


def test_review_renderer_rejects_when_both_fence_delimiters_are_too_long(
    run_ltc, tmp_path: Path
) -> None:
    source = tmp_path / "book.txt"
    destination = tmp_path / "scan"
    source.write_text("The bell rang at 13:15.\n", encoding="utf-8")
    assert run_ltc("scan", source, "--output", destination).returncode == 0
    original = read_rows(destination)[0]
    context_before = "`" * 255 + "\n" + "~" * 255 + "\n# injected\n"
    candidate = candidate_with_context(original, context_before)
    metadata = candidate["workMetadata"]
    assert isinstance(metadata, dict)

    with pytest.raises(ValueError, match="safe Markdown fence"):
        render_review_markdown([candidate], metadata)


@pytest.mark.parametrize(
    ("long_delimiter", "short_delimiter", "expected_fence"),
    [
        ("`", "~", "~~~text"),
        ("~", "`", "```text"),
    ],
)
def test_review_uses_bounded_fence_and_preserves_boundary_newlines(
    run_ltc,
    tmp_path: Path,
    long_delimiter: str,
    short_delimiter: str,
    expected_fence: str,
) -> None:
    source = tmp_path / "book.txt"
    destination = tmp_path / "scan"
    source.write_text("The bell rang at 13:15.\n", encoding="utf-8")
    assert run_ltc("scan", source, "--output", destination).returncode == 0
    original = read_rows(destination)[0]
    non_markdown_separators = "\u0085\v\f\u2028\u2029"
    context_before = (
        "\r\n\n"
        + long_delimiter * 255
        + f"\r{short_delimiter * 2}before{non_markdown_separators}\n"
    )
    context_after = "\r\n\n\r"
    candidate = candidate_with_context(original, context_before, context_after)
    metadata = candidate["workMetadata"]
    assert isinstance(metadata, dict)

    review = render_review_markdown([candidate], metadata).decode("utf-8")

    assert expected_fence in review
    assert str(candidate["context"]) in review
    assert expected_fence[0] * 256 not in review
    assert read_rows(destination)[0]["context"] == original["context"]


def test_scan_reports_controlled_error_when_no_safe_review_fence_exists(
    run_ltc, tmp_path: Path, monkeypatch, capsys
) -> None:
    source = tmp_path / "book.txt"
    destination = tmp_path / "scan"
    source.write_text("The bell rang at 13:15.\n", encoding="utf-8")
    assert run_ltc("scan", source, "--output", destination).returncode == 0
    candidate = candidate_with_context(
        read_rows(destination)[0],
        "`" * 255 + "\n" + "~" * 255 + "\nprivate-source-sentinel\n",
    )
    rejected_destination = tmp_path / "rejected"

    monkeypatch.setattr(
        scan_module,
        "extract_candidates",
        lambda document, work_metadata: [
            {**candidate, "workMetadata": dict(work_metadata)}
        ],
    )
    exit_code = main(["scan", str(source), "--output", str(rejected_destination)])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert captured.out == ""
    error = json.loads(captured.err)["error"]
    assert error["code"] == "review-render-failed"
    assert error["details"] == {"stage": "review-render"}
    assert "private-source-sentinel" not in captured.err
    assert not rejected_destination.exists()


def test_review_renderer_rejects_duplicate_candidate_ids(
    run_ltc, tmp_path: Path
) -> None:
    source = tmp_path / "book.txt"
    destination = tmp_path / "scan"
    source.write_text("The bell rang at 13:15.\n", encoding="utf-8")
    assert run_ltc("scan", source, "--output", destination).returncode == 0
    candidate = read_rows(destination)[0]
    metadata = candidate["workMetadata"]
    assert isinstance(metadata, dict)

    with pytest.raises(ValueError, match="duplicate candidate ID"):
        render_review_markdown([candidate, dict(candidate)], metadata)


def test_review_renderer_rejects_candidate_header_metadata_mismatch(
    run_ltc, tmp_path: Path
) -> None:
    source = tmp_path / "book.txt"
    destination = tmp_path / "scan"
    source.write_text("The bell rang at 13:15.\n", encoding="utf-8")
    assert run_ltc("scan", source, "--output", destination).returncode == 0
    candidate = read_rows(destination)[0]
    metadata = dict(candidate["workMetadata"])
    metadata["author"] = "Different Author"

    with pytest.raises(ValueError, match="candidate metadata mismatch"):
        render_review_markdown([candidate], metadata)


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

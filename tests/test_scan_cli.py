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


def assert_retained_failure_details(
    error: dict[str, object],
    tmp_path: Path,
    *,
    stage: str,
) -> None:
    details = error["details"]
    assert isinstance(details, dict)
    assert details["stage"] == stage
    assert details["officialPathStatus"] == "absent"
    retained_name = details["retainedPathBasename"]
    assert isinstance(retained_name, str)
    assert Path(retained_name).name == retained_name
    assert (tmp_path / retained_name / "entry").is_dir()


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


def test_scan_run_manifest_has_exact_shape_and_binds_final_artifacts(
    run_ltc, tmp_path: Path
) -> None:
    source = tmp_path / "my-novel.txt"
    destination = tmp_path / "scan"
    source_bytes = "At 13:15 the café bell rang.\n".encode("utf-8")
    source.write_bytes(source_bytes)

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

    assert result.returncode == 0, result.stderr
    run = json.loads((destination / "run.json").read_bytes())
    assert set(run) == {
        "artifactDigests",
        "bodySelection",
        "candidateCount",
        "input",
        "metadata",
        "resolvedMinuteCount",
        "schemaVersion",
        "status",
        "toolVersions",
    }
    assert run["schemaVersion"] == "scan-run-v1"
    assert run["status"] == "complete"
    assert run["input"] == {
        "basename": "my-novel.txt",
        "byteSize": len(source_bytes),
        "sha256": hashlib.sha256(source_bytes).hexdigest(),
    }
    assert run["metadata"] == {
        "author": "Example Author",
        "metadataComplete": True,
        "schemaVersion": "scan-work-metadata-v1",
        "sourceUrl": "https://example.org/book",
        "title": "Example Book",
    }
    assert run["bodySelection"] == {"mode": "full-file"}
    assert run["toolVersions"] == {
        "candidateSchemaVersion": "time-candidate-v1",
        "extractionVersion": "extract-v1",
        "normalizationVersion": "normalize-v1",
        "normalizedSchemaVersion": "normalized-source-v1",
        "reportSchemaVersion": "candidate-report-v1",
        "reportVersion": "report-v1",
        "scanVersion": "scan-v1",
        "workMetadataSchemaVersion": "scan-work-metadata-v1",
    }
    assert set(run["artifactDigests"]) == ARTIFACTS - {"run.json"}
    for name, digest in run["artifactDigests"].items():
        content = (destination / name).read_bytes()
        assert digest == {
            "byteSize": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
        }

    candidates_bytes = (destination / "candidates.jsonl").read_bytes()
    candidates = read_rows(destination)
    report = json.loads((destination / "report.json").read_bytes())
    assert run["candidateCount"] == len(candidates) == report["candidateCount"]
    assert run["resolvedMinuteCount"] == report["resolvedMinuteCount"]
    assert report["inputSha256"] == hashlib.sha256(candidates_bytes).hexdigest()
    review = (destination / "review.md").read_text(encoding="utf-8")
    assert review.count("Candidate ID:") == run["candidateCount"]
    for candidate in candidates:
        assert review.count(f"Candidate ID: `{candidate['candidateId']}`") == 1


def test_scan_run_manifest_records_literal_body_markers(
    run_ltc, tmp_path: Path
) -> None:
    source = tmp_path / "marked.txt"
    destination = tmp_path / "scan"
    source.write_text("Header\nBEGIN\nAt 13:15.\nEND\nFooter\n", encoding="utf-8")

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
    run = json.loads((destination / "run.json").read_bytes())
    assert run["bodySelection"] == {
        "endMarker": "END",
        "mode": "literal-markers",
        "startMarker": "BEGIN",
    }


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
    assert json.loads((destination / "run.json").read_text())["metadata"] == expected


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


def test_scan_allows_candidate_id_label_text_inside_source(
    run_ltc, tmp_path: Path
) -> None:
    source = tmp_path / "book.txt"
    destination = tmp_path / "scan"
    source.write_text(
        "The words Candidate ID: appeared beside 13:15 in the source.\n",
        encoding="utf-8",
    )

    result = run_ltc("scan", source, "--output", destination)

    assert result.returncode == 0, result.stderr
    candidates = read_rows(destination)
    assert len(candidates) == 1
    review = (destination / "review.md").read_text(encoding="utf-8")
    assert "The words Candidate ID: appeared beside 13:15" in review
    assert review.count(f"Candidate ID: `{candidates[0]['candidateId']}`") == 1


def test_scan_rejects_tampered_staged_review_without_publishing(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    source = tmp_path / "book.txt"
    destination = tmp_path / "scan"
    source.write_text("The bell rang at 13:15.\n", encoding="utf-8")
    verify_staging = scan_module._verify_staging

    def tamper_then_verify(
        staging_path: Path,
        expected_run: dict[str, object],
        **verification_inputs,
    ) -> None:
        review_path = staging_path / "review.md"
        review_path.write_bytes(review_path.read_bytes() + b"tampered\n")
        artifact_digests = expected_run["artifactDigests"]
        assert isinstance(artifact_digests, dict)
        artifact_digests["review.md"] = scan_module.artifact_digest(review_path)
        scan_module.write_json_atomic(staging_path / "run.json", expected_run)
        verify_staging(staging_path, expected_run, **verification_inputs)

    monkeypatch.setattr(scan_module, "_verify_staging", tamper_then_verify)

    exit_code = main(["scan", str(source), "--output", str(destination)])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert captured.out == ""
    error = json.loads(captured.err)["error"]
    assert error["code"] == "scan-verification-failed"
    assert_retained_failure_details(error, tmp_path, stage="verification")
    assert not destination.exists()


def test_scan_rejects_coherent_artifacts_not_regenerated_from_source(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    source = tmp_path / "book.txt"
    destination = tmp_path / "scan"
    source_bytes = b"At 13:15 the first bell rang.\n"
    source.write_bytes(source_bytes)
    normalize = scan_module.normalize_bytes
    forged = normalize(b"At 14:45 another bell rang.\n")
    source_sha256 = hashlib.sha256(source_bytes).hexdigest()
    forged["sourceSha256"] = source_sha256
    forged["sourceId"] = f"local_{source_sha256[:12]}"
    call_count = 0

    def forge_first_normalization(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return forged
        return normalize(*args, **kwargs)

    monkeypatch.setattr(scan_module, "normalize_bytes", forge_first_normalization)

    exit_code = main(["scan", str(source), "--output", str(destination)])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert captured.out == ""
    error = json.loads(captured.err)["error"]
    assert error["code"] == "scan-verification-failed"
    assert_retained_failure_details(error, tmp_path, stage="verification")
    assert not destination.exists()


@pytest.mark.parametrize("mutation", ["pretty", "float-count"])
def test_scan_rejects_noncanonical_run_json_without_publishing(
    tmp_path: Path, monkeypatch, capsys, mutation: str
) -> None:
    source = tmp_path / "book.txt"
    destination = tmp_path / "scan"
    source.write_text("The bell rang at 13:15.\n", encoding="utf-8")
    verify_staging = scan_module._verify_staging

    def mutate_then_verify(
        staging_path: Path,
        expected_run: dict[str, object],
        **verification_inputs,
    ) -> object:
        altered = dict(expected_run)
        if mutation == "float-count":
            altered["candidateCount"] = 1.0
            content = json.dumps(
                altered,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ) + "\n"
        else:
            content = json.dumps(altered, ensure_ascii=False, indent=2) + "\n"
        (staging_path / "run.json").write_text(content, encoding="utf-8")
        return verify_staging(staging_path, expected_run, **verification_inputs)

    monkeypatch.setattr(scan_module, "_verify_staging", mutate_then_verify)

    exit_code = main(["scan", str(source), "--output", str(destination)])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert captured.out == ""
    error = json.loads(captured.err)["error"]
    assert error["code"] == "scan-verification-failed"
    assert_retained_failure_details(error, tmp_path, stage="verification")
    assert not destination.exists()


def test_scan_rejects_symlinked_staged_artifact_without_publishing(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    source = tmp_path / "book.txt"
    destination = tmp_path / "scan"
    source.write_text("The bell rang at 13:15.\n", encoding="utf-8")
    verify_staging = scan_module._verify_staging

    def symlink_then_verify(
        staging_path: Path,
        expected_run: dict[str, object],
        **verification_inputs,
    ) -> object:
        review_path = staging_path / "review.md"
        external_review = tmp_path / "external-review.md"
        external_review.write_bytes(review_path.read_bytes())
        review_path.unlink()
        review_path.symlink_to(external_review)
        return verify_staging(staging_path, expected_run, **verification_inputs)

    monkeypatch.setattr(scan_module, "_verify_staging", symlink_then_verify)

    exit_code = main(["scan", str(source), "--output", str(destination)])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert captured.out == ""
    error = json.loads(captured.err)["error"]
    assert error["code"] == "scan-verification-failed"
    assert_retained_failure_details(error, tmp_path, stage="verification")
    assert not destination.exists()


def test_scan_reverifies_after_publish_and_retains_corrupt_created_directory(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    source = tmp_path / "book.txt"
    destination = tmp_path / "scan"
    source.write_text("The bell rang at 13:15.\n", encoding="utf-8")
    verify_staging = scan_module._verify_staging
    call_count = 0

    def mutate_after_first_verification(
        artifact_directory: Path,
        expected_run: dict[str, object],
        **verification_inputs,
    ) -> object:
        nonlocal call_count
        call_count += 1
        result = verify_staging(
            artifact_directory,
            expected_run,
            **verification_inputs,
        )
        if call_count == 1:
            review_path = artifact_directory / "review.md"
            review_path.write_bytes(review_path.read_bytes() + b"corrupt\n")
        return result

    monkeypatch.setattr(
        scan_module,
        "_verify_staging",
        mutate_after_first_verification,
    )

    exit_code = main(["scan", str(source), "--output", str(destination)])
    captured = capsys.readouterr()

    assert call_count == 2
    assert exit_code == 2
    assert captured.out == ""
    error = json.loads(captured.err)["error"]
    assert error["code"] == "scan-verification-failed"
    assert_retained_failure_details(error, tmp_path, stage="verification")
    assert not destination.exists()


def test_scan_does_not_remove_replacement_of_its_created_staging_directory(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    source = tmp_path / "book.txt"
    destination = tmp_path / "scan"
    source.write_text("The bell rang at 13:15.\n", encoding="utf-8")
    verify_staging = scan_module._verify_staging
    replacement_paths: list[Path] = []

    def replace_after_first_verification(
        artifact_directory: Path,
        expected_run: dict[str, object],
        **verification_inputs,
    ) -> object:
        result = verify_staging(
            artifact_directory,
            expected_run,
            **verification_inputs,
        )
        if not replacement_paths:
            original = tmp_path / "displaced-original"
            artifact_directory.rename(original)
            artifact_directory.mkdir()
            (artifact_directory / "unrelated.txt").write_text(
                "keep",
                encoding="utf-8",
            )
            replacement_paths.append(artifact_directory)
        return result

    monkeypatch.setattr(
        scan_module,
        "_verify_staging",
        replace_after_first_verification,
    )

    exit_code = main(["scan", str(source), "--output", str(destination)])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert captured.out == ""
    error = json.loads(captured.err)["error"]
    assert error["code"] == "scan-verification-failed"
    assert error["details"]["stage"] == "verification"
    retained_name = error["details"]["retainedPathBasename"]
    assert isinstance(retained_name, str)
    assert error["details"]["officialPathStatus"] == "absent"
    assert not destination.exists()
    assert len(replacement_paths) == 1
    assert not replacement_paths[0].exists()
    assert (
        tmp_path / retained_name / "entry" / "unrelated.txt"
    ).read_text() == "keep"


@pytest.mark.parametrize("original_name_occupied", [False, True])
def test_quarantine_cleanup_retains_a_directory_swapped_before_atomic_rename(
    tmp_path: Path,
    monkeypatch,
    original_name_occupied: bool,
) -> None:
    owned = tmp_path / "owned"
    owned.mkdir()
    (owned / "owned.txt").write_text("owned", encoding="utf-8")
    owned_identity = scan_module._directory_identity(owned)
    displaced_owned = tmp_path / "displaced-owned"
    rename = scan_module.os.rename
    swap_injected = False

    def inject_swap(source, destination, *args, **kwargs):
        nonlocal swap_injected
        source_path = Path(source)
        destination_path = Path(destination)
        if source_path == owned and not swap_injected:
            swap_injected = True
            rename(owned, displaced_owned)
            owned.mkdir()
            (owned / "unrelated.txt").write_text("keep", encoding="utf-8")
        result = rename(source, destination, *args, **kwargs)
        if (
            swap_injected
            and original_name_occupied
            and destination_path.parent.parent == tmp_path
            and ".quarantine-" in destination_path.parent.name
        ):
            owned.mkdir()
            (owned / "occupant.txt").write_text("occupant", encoding="utf-8")
        return result

    monkeypatch.setattr(scan_module.os, "rename", inject_swap)

    outcome = scan_module._retain_path_entry_in_quarantine(
        owned,
        owned_identity,
    )

    assert (displaced_owned / "owned.txt").read_text() == "owned"
    assert outcome is not None
    retained_name = outcome["retainedPathBasename"]
    assert isinstance(retained_name, str)
    assert Path(retained_name).name == retained_name
    assert (tmp_path / retained_name).stat().st_mode & 0o777 == 0o700
    assert outcome["identityMatched"] is False
    if original_name_occupied:
        assert outcome["officialPathStatus"] == "present"
        assert (owned / "occupant.txt").read_text() == "occupant"
    else:
        assert outcome["officialPathStatus"] == "absent"
        assert not owned.exists()
    assert (
        tmp_path / retained_name / "entry" / "unrelated.txt"
    ).read_text() == "keep"


def test_quarantine_cleanup_retains_symlink_without_following_it(
    tmp_path: Path,
) -> None:
    owned = tmp_path / "owned"
    owned.mkdir()
    owned_identity = scan_module._directory_identity(owned)
    displaced_owned = tmp_path / "displaced-owned"
    owned.rename(displaced_owned)
    external = tmp_path / "external"
    external.mkdir()
    (external / "keep.txt").write_text("keep", encoding="utf-8")
    owned.symlink_to(external, target_is_directory=True)

    outcome = scan_module._retain_path_entry_in_quarantine(
        owned,
        owned_identity,
    )

    assert outcome is not None
    assert outcome["identityMatched"] is False
    assert outcome["officialPathStatus"] == "absent"
    retained_name = outcome["retainedPathBasename"]
    assert isinstance(retained_name, str)
    assert (tmp_path / retained_name / "entry").is_symlink()
    assert not owned.exists()
    assert (external / "keep.txt").read_text() == "keep"


def test_scan_reports_and_retains_failed_generation_staging(
    run_ltc, tmp_path: Path
) -> None:
    source = tmp_path / "invalid.txt"
    destination = tmp_path / "scan"
    source.write_bytes(b"invalid utf-8: \xff")

    result = run_ltc("scan", source, "--output", destination)

    assert result.returncode == 2
    assert result.stdout == ""
    error = json.loads(result.stderr)["error"]
    assert error["code"] == "invalid-utf8"
    assert error["details"]["stage"] == "normalization"
    retained_name = error["details"]["retainedPathBasename"]
    assert isinstance(retained_name, str)
    assert Path(retained_name).name == retained_name
    assert error["details"]["officialPathStatus"] == "absent"
    assert (tmp_path / retained_name / "entry").is_dir()
    assert not destination.exists()


def test_scan_reports_cleanup_failure_without_claiming_success(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    source = tmp_path / "book.txt"
    destination = tmp_path / "scan"
    source.write_text("The bell rang at 13:15.\n", encoding="utf-8")
    verify_staging = scan_module._verify_staging
    rename = scan_module.os.rename
    verification_count = 0

    def corrupt_after_first_verification(
        artifact_directory: Path,
        expected_run: dict[str, object],
        **verification_inputs,
    ) -> object:
        nonlocal verification_count
        verification_count += 1
        result = verify_staging(
            artifact_directory,
            expected_run,
            **verification_inputs,
        )
        if verification_count == 1:
            review_path = artifact_directory / "review.md"
            review_path.write_bytes(review_path.read_bytes() + b"corrupt\n")
        return result

    def reject_quarantine_move(source_path, destination_path, *args, **kwargs):
        if Path(source_path) == destination and Path(destination_path).name == "entry":
            raise PermissionError("synthetic cleanup failure")
        return rename(source_path, destination_path, *args, **kwargs)

    monkeypatch.setattr(scan_module, "_verify_staging", corrupt_after_first_verification)
    monkeypatch.setattr(scan_module.os, "rename", reject_quarantine_move)

    exit_code = main(["scan", str(source), "--output", str(destination)])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert captured.out == ""
    error = json.loads(captured.err)["error"]
    assert error["code"] == "scan-cleanup-failed"
    assert error["details"] == {
        "officialPathStatus": "present",
        "stage": "cleanup",
    }
    assert destination.exists()


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
    assert json.loads((destination / "run.json").read_text())["metadata"][
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
    assert json.loads((destination / "run.json").read_text())["metadata"][
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
    assert_retained_failure_details(error, tmp_path, stage="review-render")
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

    first_payload = b"".join((first / name).read_bytes() for name in sorted(ARTIFACTS))
    forbidden = (
        str(first_source.parent),
        str(second_source.parent),
        str(Path.cwd()),
        getpass.getuser(),
        socket.gethostname(),
        ".scan-",
    )
    for value in forbidden:
        if value:
            assert value.encode("utf-8") not in first_payload
    assert re.search(rb"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", first_payload) is None


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

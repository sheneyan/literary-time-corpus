from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path, PurePosixPath
from typing import Mapping


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
ALLOWED_ROOT_FILES = {
    PurePosixPath(".gitignore"),
    PurePosixPath("DATA_RIGHTS.md"),
    PurePosixPath("LICENSE"),
    PurePosixPath("README.md"),
    PurePosixPath("pyproject.toml"),
    PurePosixPath("uv.lock"),
}
ALLOWED_DOC_FILES = {
    PurePosixPath("docs/data-model.md"),
    PurePosixPath("docs/evaluation-protocol.md"),
    PurePosixPath("docs/operations/ubtmini-source-cache-plan.md"),
    PurePosixPath("docs/pilot-design.md"),
    PurePosixPath("docs/project-brief.md"),
    PurePosixPath("docs/research/china-public-domain-policy.md"),
    PurePosixPath("docs/research/gutenberg-private-mirror.md"),
    PurePosixPath("docs/research/gutenberg-source-policy.md"),
    PurePosixPath("docs/rights-policy.md"),
    PurePosixPath("docs/superpowers/plans/2026-09-14-gate-2-pipeline.md"),
    PurePosixPath("docs/superpowers/plans/2026-09-14-gutenberg-pilot-design.md"),
    PurePosixPath("docs/superpowers/plans/2026-09-14-initial-repository.md"),
    PurePosixPath(
        "docs/superpowers/plans/2026-09-14-mirror-and-jurisdiction-policy.md"
    ),
    PurePosixPath("docs/superpowers/plans/2026-09-14-public-txt-scanner.md"),
    PurePosixPath("docs/superpowers/plans/2026-09-15-extract-v2-oclock.md"),
    PurePosixPath("docs/superpowers/plans/2026-09-15-v0.1-release.md"),
    PurePosixPath("docs/superpowers/specs/2026-09-14-initial-repository-design.md"),
    PurePosixPath("docs/superpowers/specs/2026-09-14-public-txt-scanner-design.md"),
    PurePosixPath("docs/superpowers/specs/2026-09-15-extract-v2-oclock-design.md"),
    PurePosixPath("docs/superpowers/specs/2026-09-15-v0.1-release-design.md"),
}
ALLOWED_SOURCE_FILES = {
    PurePosixPath("src/literary_time_corpus/__init__.py"),
    PurePosixPath("src/literary_time_corpus/__main__.py"),
    PurePosixPath("src/literary_time_corpus/candidate.py"),
    PurePosixPath("src/literary_time_corpus/cli.py"),
    PurePosixPath("src/literary_time_corpus/encoding.py"),
    PurePosixPath("src/literary_time_corpus/extract.py"),
    PurePosixPath("src/literary_time_corpus/io.py"),
    PurePosixPath("src/literary_time_corpus/normalize.py"),
    PurePosixPath("src/literary_time_corpus/normalized.py"),
    PurePosixPath("src/literary_time_corpus/report.py"),
    PurePosixPath("src/literary_time_corpus/review.py"),
    PurePosixPath("src/literary_time_corpus/scan.py"),
    PurePosixPath("src/literary_time_corpus/validate.py"),
}
ALLOWED_TEST_FILES = {
    PurePosixPath("tests/conftest.py"),
    PurePosixPath("tests/test_encoding.py"),
    PurePosixPath("tests/test_extract_cli.py"),
    PurePosixPath("tests/test_input_paths_cli.py"),
    PurePosixPath("tests/test_normalize_cli.py"),
    PurePosixPath("tests/test_report_cli.py"),
    PurePosixPath("tests/test_repository_policy.py"),
    PurePosixPath("tests/test_scan_cli.py"),
    PurePosixPath("tests/test_scan_transaction_cli.py"),
    PurePosixPath("tests/test_validate_cli.py"),
    PurePosixPath("tests/test_wheel_install.py"),
}
ALLOWED_REVIEWED_TEXT_FILES = (
    ALLOWED_ROOT_FILES | ALLOWED_DOC_FILES | ALLOWED_SOURCE_FILES | ALLOWED_TEST_FILES
)
PRIVATE_KEY_MARKER = re.compile(
    rb"-----BEGIN (?:[A-Z0-9][A-Z0-9 -]* )?PRIVATE KEY-----"
)
TOKEN_ASSIGNMENT = re.compile(
    rb"(?<![A-Za-z0-9_-])"
    rb"(?:[A-Za-z][A-Za-z0-9]*[_-])*"
    rb"(?:api[_-]?key|token|secret(?:[_-][A-Za-z0-9]+)*)"
    rb"(?![A-Za-z0-9_-])"
    rb"['\"]?\s*[:=]\s*(?:['\"][A-Za-z0-9_./+=-]{16,}['\"]|"
    rb"[A-Za-z0-9_./+=-]{16,}(?=$|[\s;#]))",
    re.IGNORECASE,
)
GUTENBERG_BODY_MARKER = re.compile(
    rb"^\*\*\* (?:START|END) OF (?:THE|THIS) PROJECT GUTENBERG EBOOK\b",
    re.MULTILINE,
)
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
    PurePosixPath("tests/fixtures/report/candidates.jsonl"): (
        "cc58f58af344a7567ba5639a6ba7e1a020b486cd333ae9836e4f0ee45947f46d"
    ),
    PurePosixPath("tests/fixtures/validate/analysis.json"): (
        "8fde7f74b6762f8af60d2e6ff220a3324033a673a28a862637df039238fab541"
    ),
    PurePosixPath("tests/fixtures/validate/candidate.json"): (
        "9fecf5149804933fcfc8e0be6a2a8b453e96d69b18debab79ef69c524eb02b9e"
    ),
    PurePosixPath("tests/fixtures/validate/review.json"): (
        "8622d876cc7ec23d4aaf00c33bcec01d905746215ed02ffadb27925fbb6e8d3e"
    ),
    PurePosixPath("tests/fixtures/validate/rights.json"): (
        "975bd9dbdd56ce4a35551dba3d48c6a86b319263483335ed971ff2d6025c84b5"
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


def is_approved_synthetic_fixture(path: PurePosixPath, content: bytes) -> bool:
    expected_hash = APPROVED_SYNTHETIC_FIXTURE_SHA256.get(path)
    return (
        expected_hash is not None
        and hashlib.sha256(content).hexdigest() == expected_hash
    )


def has_disallowed_text_content(content: bytes) -> bool:
    return any(
        pattern.search(content) is not None
        for pattern in (
            PRIVATE_KEY_MARKER,
            TOKEN_ASSIGNMENT,
            GUTENBERG_BODY_MARKER,
        )
    )


def policy_violations(files: Mapping[str, bytes]) -> list[str]:
    violations: list[str] = []
    for raw_path, content in files.items():
        path = PurePosixPath(raw_path)
        if path.parts[:2] == ("tests", "fixtures"):
            if not is_approved_synthetic_fixture(path, content):
                violations.append(raw_path)
            continue
        if path.parts[:1] in {("manifests",), ("artifacts",), ("releases",)}:
            expected_placeholder = ALLOWED_DATA_ROOT_PLACEHOLDER_BYTES.get(path)
            if expected_placeholder is None or content != expected_placeholder:
                violations.append(raw_path)
            continue
        if path in ALLOWED_REVIEWED_TEXT_FILES:
            if has_disallowed_text_content(content):
                violations.append(raw_path)
            continue
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


def test_scan_output_is_ignored_and_never_approved_for_tracking() -> None:
    probe = "scans/example/normalized.json"
    ignored = subprocess.run(
        ["git", "check-ignore", "--quiet", probe],
        cwd=REPOSITORY_ROOT,
        check=False,
    )

    assert ignored.returncode == 0, "scans/ must be ignored by repository policy"
    assert policy_violations({probe: b'{"analysisText":"source text"}\n'}) == [
        probe
    ]


def test_public_documentation_matches_local_scanner_path_and_identity_contract() -> None:
    readme = (REPOSITORY_ROOT / "README.md").read_text(encoding="utf-8")
    data_model = (REPOSITORY_ROOT / "docs/data-model.md").read_text(
        encoding="utf-8"
    )

    assert "--output scans/book" not in readme
    assert "ltc scan book.txt --output book-scan" in readme
    assert "The output parent directory must already exist" in readme
    assert (
        "`local_<first 12 lowercase hexadecimal characters of sourceSha256>`"
        in data_model
    )
    assert "synthetic `sourceId`" not in data_model
    assert re.search(r"synthetic\s+source-ID", data_model) is None
    assert "### Future Project Gutenberg source snapshot" in data_model


def test_readme_describes_v010_release_and_verified_environment() -> None:
    readme = (REPOSITORY_ROOT / "README.md").read_text(encoding="utf-8")
    normalized_readme = " ".join(readme.split())

    assert "offline, provider-neutral TXT scanner" in normalized_readme
    assert "macOS 26.5" in normalized_readme
    assert "Apple Silicon (`arm64`)" in normalized_readme
    assert "Python 3.11.16" in normalized_readme
    assert "uv 0.10.0" in normalized_readme
    assert (
        "Other operating systems, architectures, and Python versions are "
        "untested" in normalized_readme
    )
    assert (
        "releases/download/v0.1.0/"
        "literary_time_corpus-0.1.0-py3-none-any.whl" in normalized_readme
    )
    assert (
        "Project Gutenberg is one possible external source" in normalized_readme
    )


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


def test_unknown_tracked_paths_are_denied_even_without_known_content_suffixes() -> None:
    files = {
        "data/book.json": b'{"hidden":"payload"}\n',
        "sources/book": b"extensionless payload\n",
        "unexpected.yaml": b"payload: true\n",
    }

    assert policy_violations(files) == sorted(files)


def test_familiar_suffixes_do_not_bypass_exact_reviewed_path_allowlists() -> None:
    files = {
        "docs/unapproved-book.md": b"unreviewed prose\n",
        "src/literary_time_corpus/unexpected.py": b"VALUE = 'unreviewed'\n",
        "tests/unexpected.py": b"def test_unreviewed(): pass\n",
    }

    assert policy_violations(files) == sorted(files)


def test_allowed_text_paths_reject_likely_secrets_and_gutenberg_bodies() -> None:
    private_key_marker = b"-----BEGIN " + b"PRIVATE KEY-----\n"
    token_assignment = (
        b"access_to" + b"ken = '" + b"0123456789abcdef0123456789abcdef'\n"
    )
    gutenberg_body_marker = (
        b"*** START OF THE PROJECT " + b"GUTENBERG EBOOK UNREVIEWED ***\n"
    )
    files = {
        "README.md": private_key_marker,
        "src/literary_time_corpus/cli.py": token_assignment,
        "docs/data-model.md": gutenberg_body_marker,
    }

    assert policy_violations(files) == sorted(files)


def test_private_key_filter_covers_pem_private_key_families_only() -> None:
    private_files = {
        "README.md": b"-----BEGIN ENCRYPTED " + b"PRIVATE KEY-----\n",
        "docs/data-model.md": b"-----BEGIN DSA " + b"PRIVATE KEY-----\n",
    }
    public_files = {
        "README.md": b"-----BEGIN " + b"PUBLIC KEY-----\n",
        "docs/data-model.md": b"-----BEGIN " + b"CERTIFICATE-----\n",
    }

    assert policy_violations(private_files) == sorted(private_files)
    assert policy_violations(public_files) == []


def test_secret_filter_rejects_unquoted_export_assignment() -> None:
    unquoted_secret = (
        b"export API_" + b"KEY=sk-proj-abcdefghijklmnopqrstuvwxyz\n"
    )

    assert policy_violations({"README.md": unquoted_secret}) == ["README.md"]


def test_secret_filter_rejects_quoted_assignments_before_closing_punctuation() -> None:
    secret_value = b"0123456789abcdef"
    files = {
        "README.md": b'"api_' + b'key": "' + secret_value + b'",\n',
        "docs/data-model.md": b'api_' + b'key = "' + secret_value + b'",\n',
        "src/literary_time_corpus/cli.py": (
            b'use(api_' + b'key="' + secret_value + b'")\n'
        ),
        "tests/conftest.py": (
            b'{"access_' + b'token": "' + secret_value + b'"}\n'
        ),
    }

    assert policy_violations(files) == sorted(files)


def test_secret_filter_allows_short_placeholders_and_descriptive_prose() -> None:
    files = {
        "README.md": b'api_' + b'key = "replace-me"\n',
        "docs/data-model.md": b"Document the access_" + b"token field.\n",
    }

    assert policy_violations(files) == []


def test_secret_filter_rejects_common_prefixed_credential_names() -> None:
    files = {
        "README.md": (
            b"OPENAI_API_" + b"KEY=sk-proj-abcdefghijklmnopqrstuvwxyz\n"
        ),
        "docs/data-model.md": (
            b"GITHUB_" + b"TOKEN=ghp_abcdefghijklmnopqrstuvwxyz1234\n"
        ),
        "src/literary_time_corpus/cli.py": (
            b'client_se' + b'cret="' + b'0123456789abcdef"\n'
        ),
        "tests/conftest.py": (
            b"AWS_SECRET_" + b"ACCESS_KEY=abcdefghijklmnopqrstuvwxyz123456\n"
        ),
    }

    assert policy_violations(files) == sorted(files)


def test_secret_filter_allows_redaction_env_lookups_and_ordinary_prose() -> None:
    files = {
        "README.md": b"OPENAI_API_" + b"KEY=redacted\n",
        "docs/data-model.md": (
            b"GITHUB_" + b'TOKEN = os.environ["GITHUB_TOKEN"]\n'
        ),
        "src/literary_time_corpus/cli.py": (
            b'client_' + b'secret = "<redacted>"\n'
        ),
        "tests/conftest.py": b"Describe a token assignment without a value.\n",
    }

    assert policy_violations(files) == []


def test_body_marker_filter_rejects_this_project_family() -> None:
    marker = (
        b"*** START OF THIS PROJECT "
        + b"GUTENBERG EBOOK UNREVIEWED ***\n"
    )

    assert policy_violations({"docs/data-model.md": marker}) == [
        "docs/data-model.md"
    ]


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


def test_json_fixture_copy_and_byte_changes_require_exact_hash_approval() -> None:
    approved_path = PurePosixPath("tests/fixtures/validate/review.json")
    approved_content = (REPOSITORY_ROOT / approved_path).read_bytes()
    files = {
        str(approved_path): approved_content + b" ",
        "tests/fixtures/validate/review-copy.json": approved_content,
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

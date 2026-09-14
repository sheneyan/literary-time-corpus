from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest


FIXTURES = Path(__file__).parent / "fixtures" / "normalize"
START_MARKER = "*** START OF THE PROJECT GUTENBERG EBOOK SYNTHETIC CLOCK ***"
END_MARKER = "*** END OF THE PROJECT GUTENBERG EBOOK SYNTHETIC CLOCK ***"


def parse_error(stderr: str) -> dict[str, object]:
    assert stderr.endswith("\n")
    assert len(stderr.splitlines()) == 1
    return json.loads(stderr)


def test_help_lists_the_four_approved_commands(run_ltc) -> None:
    result = run_ltc("--help")

    assert result.returncode == 0, result.stderr
    for command in ("normalize", "extract", "validate", "report"):
        assert command in result.stdout


def test_normalize_without_marker_flags_preserves_the_complete_utf8_file(
    run_ltc, tmp_path: Path
) -> None:
    source = tmp_path / "novel.txt"
    source_bytes = "Préface 😀\nAt 13:15 the bell rang.\n".encode("utf-8")
    source.write_bytes(source_bytes)
    output = tmp_path / "normalized.json"

    result = run_ltc("normalize", "--input", source, "--output", output)

    assert result.returncode == 0, result.stderr
    document = json.loads(output.read_text(encoding="utf-8"))
    source_hash = hashlib.sha256(source_bytes).hexdigest()
    assert document == {
        "analysisText": source_bytes.decode("utf-8"),
        "analysisTextSha256": source_hash,
        "bodyEndByte": len(source_bytes),
        "bodyStartByte": 0,
        "normalizationVersion": "normalize-v1",
        "schemaVersion": "normalized-source-v1",
        "sourceId": f"local_{source_hash[:12]}",
        "sourceSha256": source_hash,
        "transformationLog": [
            {
                "inputEndByte": len(source_bytes),
                "inputStartByte": 0,
                "method": "full-file-selection",
                "outputEndByte": len(source_bytes),
                "outputStartByte": 0,
            }
        ],
    }
    assert output.exists()


def test_normalize_is_byte_deterministic(run_ltc, tmp_path: Path) -> None:
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"

    first_result = run_ltc(
        "normalize", "--input", FIXTURES / "valid.txt", "--output", first
    )
    second_result = run_ltc(
        "normalize", "--input", FIXTURES / "valid.txt", "--output", second
    )

    assert first_result.returncode == second_result.returncode == 0
    assert first.read_bytes() == second.read_bytes()


def test_normalize_help_lists_optional_literal_marker_pair(run_ltc) -> None:
    result = run_ltc("normalize", "--help")

    assert result.returncode == 0, result.stderr
    assert "--start-marker" in result.stdout
    assert "--end-marker" in result.stdout


def test_normalize_selects_literal_marker_body_with_multibyte_byte_offsets(
    run_ltc, tmp_path: Path
) -> None:
    source = tmp_path / "source.txt"
    source_bytes = (
        f"Préface\r\n{START_MARKER}\r\n"
        "At 1:17 a.m., café lamps still glowed.\r\n"
        f"{END_MARKER}\r\nFooter\n"
    ).encode("utf-8")
    source.write_bytes(source_bytes)
    output = tmp_path / "normalized.json"

    result = run_ltc(
        "normalize",
        "--input",
        source,
        "--output",
        output,
        "--start-marker",
        START_MARKER,
        "--end-marker",
        END_MARKER,
    )

    assert result.returncode == 0, result.stderr
    document = json.loads(output.read_text(encoding="utf-8"))
    body = "At 1:17 a.m., café lamps still glowed."
    expected_start = source_bytes.index(START_MARKER.encode("utf-8")) + len(
        START_MARKER.encode("utf-8")
    ) + 2
    expected_end = source_bytes.index(END_MARKER.encode("utf-8")) - 2
    assert document["analysisText"] == body
    assert document["bodyStartByte"] == expected_start
    assert document["bodyEndByte"] == expected_end
    assert document["transformationLog"] == [
        {
            "inputEndByte": expected_end,
            "inputStartByte": expected_start,
            "method": "literal-marker-body-selection",
            "outputEndByte": len(body.encode("utf-8")),
            "outputStartByte": 0,
        }
    ]
    assert source_bytes[expected_start:expected_end] == body.encode("utf-8")


@pytest.mark.parametrize("marker_option", ["--start-marker", "--end-marker"])
def test_normalize_rejects_only_one_marker_option_and_preserves_output(
    run_ltc, tmp_path: Path, marker_option: str
) -> None:
    output = tmp_path / "normalized.json"
    output.write_bytes(b"keep\n")

    result = run_ltc(
        "normalize",
        "--input",
        FIXTURES / "valid.txt",
        "--output",
        output,
        marker_option,
        START_MARKER if marker_option == "--start-marker" else END_MARKER,
    )

    assert result.returncode == 2
    assert parse_error(result.stderr)["error"]["code"] == "invalid-arguments"
    assert output.read_bytes() == b"keep\n"


def test_normalize_classifies_shared_writer_invalid_output_path(
    run_ltc, tmp_path: Path
) -> None:
    output = tmp_path / "missing" / "normalized.json"

    result = run_ltc(
        "normalize", "--input", FIXTURES / "valid.txt", "--output", output
    )

    assert result.returncode == 2
    assert parse_error(result.stderr)["error"] == {
        "code": "invalid-output-path",
        "message": "could not write output path",
    }
    assert not output.exists()


def test_normalize_rejects_missing_start_marker(run_ltc, tmp_path: Path) -> None:
    output = tmp_path / "normalized.json"

    result = run_ltc(
        "normalize",
        "--input",
        FIXTURES / "missing-start.txt",
        "--output",
        output,
        "--start-marker",
        START_MARKER,
        "--end-marker",
        END_MARKER,
    )

    assert result.returncode == 2
    assert parse_error(result.stderr) == {
        "error": {
            "code": "invalid-markers",
            "message": "each marker must occur exactly once with start before end",
        }
    }
    assert not output.exists()


@pytest.mark.parametrize(
    ("body", "error_code"), [("", "invalid-markers"), (" \t\r\n", "empty-body")]
)
def test_normalize_rejects_empty_or_whitespace_marker_body(
    run_ltc, tmp_path: Path, body: str, error_code: str
) -> None:
    source = tmp_path / "empty.txt"
    source.write_text(
        "Synthetic metadata\n"
        "*** START OF THE PROJECT GUTENBERG EBOOK EMPTY ***\n"
        f"{body}"
        "*** END OF THE PROJECT GUTENBERG EBOOK EMPTY ***\n",
        encoding="utf-8",
    )
    output = tmp_path / "normalized.json"

    result = run_ltc(
        "normalize",
        "--input",
        source,
        "--output",
        output,
        "--start-marker",
        "*** START OF THE PROJECT GUTENBERG EBOOK EMPTY ***",
        "--end-marker",
        "*** END OF THE PROJECT GUTENBERG EBOOK EMPTY ***",
    )

    assert result.returncode == 2
    assert parse_error(result.stderr)["error"]["code"] == error_code
    assert not output.exists()


def test_normalize_rejects_adjacent_markers(run_ltc, tmp_path: Path) -> None:
    source = tmp_path / "adjacent.txt"
    source.write_text(f"{START_MARKER}{END_MARKER}", encoding="utf-8")
    output = tmp_path / "normalized.json"

    result = run_ltc(
        "normalize",
        "--input",
        source,
        "--output",
        output,
        "--start-marker",
        START_MARKER,
        "--end-marker",
        END_MARKER,
    )

    assert result.returncode == 2
    assert parse_error(result.stderr)["error"]["code"] == "invalid-markers"
    assert not output.exists()


@pytest.mark.parametrize("contents", [b"", b" \t\r\n"])
def test_normalize_rejects_empty_or_whitespace_complete_file(
    run_ltc, tmp_path: Path, contents: bytes
) -> None:
    source = tmp_path / "empty.txt"
    source.write_bytes(contents)
    output = tmp_path / "normalized.json"

    result = run_ltc("normalize", "--input", source, "--output", output)

    assert result.returncode == 2
    assert parse_error(result.stderr)["error"]["code"] == "empty-body"
    assert not output.exists()


def test_normalize_rejects_reversed_markers(run_ltc, tmp_path: Path) -> None:
    source = tmp_path / "reversed.txt"
    source.write_text(
        f"{END_MARKER}\nbody\n{START_MARKER}\n", encoding="utf-8"
    )
    output = tmp_path / "normalized.json"

    result = run_ltc(
        "normalize",
        "--input",
        source,
        "--output",
        output,
        "--start-marker",
        START_MARKER,
        "--end-marker",
        END_MARKER,
    )

    assert result.returncode == 2
    assert parse_error(result.stderr)["error"]["code"] == "invalid-markers"
    assert not output.exists()


def test_normalize_preserves_preexisting_output_when_input_is_invalid(
    run_ltc, tmp_path: Path
) -> None:
    output = tmp_path / "normalized.json"
    prior_output = b"keep this exact output\n"
    output.write_bytes(prior_output)

    result = run_ltc(
        "normalize",
        "--input",
        FIXTURES / "missing-start.txt",
        "--output",
        output,
        "--start-marker",
        START_MARKER,
        "--end-marker",
        END_MARKER,
    )

    assert result.returncode == 2
    assert parse_error(result.stderr)["error"]["code"] == "invalid-markers"
    assert output.read_bytes() == prior_output


@pytest.mark.parametrize("fixture_name", ["valid.txt", "missing-start.txt"])
def test_normalize_rejects_same_input_and_output_without_mutating_source(
    run_ltc, tmp_path: Path, fixture_name: str
) -> None:
    source = tmp_path / fixture_name
    source.write_bytes((FIXTURES / fixture_name).read_bytes())
    original = source.read_bytes()

    result = run_ltc("normalize", "--input", source, "--output", source)

    assert result.returncode == 2
    assert parse_error(result.stderr) == {
        "error": {
            "code": "unsafe-output-path",
            "message": "input and output must refer to different files",
        }
    }
    assert source.read_bytes() == original


def test_normalize_rejects_symlink_output_without_mutating_link_or_target(
    run_ltc, tmp_path: Path
) -> None:
    target = tmp_path / "target.json"
    target.write_text("target must survive", encoding="utf-8")
    output = tmp_path / "normalized.json"
    output.symlink_to(target)

    result = run_ltc(
        "normalize", "--input", FIXTURES / "valid.txt", "--output", output
    )

    assert result.returncode == 2
    assert parse_error(result.stderr) == {
        "error": {
            "code": "unsafe-output-path",
            "message": "output path must not be a symbolic link",
        }
    }
    assert output.is_symlink()
    assert target.read_text(encoding="utf-8") == "target must survive"


def test_normalize_rejects_fifo_input_promptly_and_preserves_output(
    project_root: Path, tmp_path: Path
) -> None:
    source = tmp_path / "source.pipe"
    os.mkfifo(source)
    output = tmp_path / "normalized.json"
    prior_output = b"keep this exact output\n"
    output.write_bytes(prior_output)

    try:
        result = subprocess.run(
            [
                "uv",
                "run",
                "ltc",
                "normalize",
                "--input",
                str(source),
                "--output",
                str(output),
            ],
            cwd=project_root,
            capture_output=True,
            text=True,
            check=False,
            timeout=3,
        )
    except subprocess.TimeoutExpired:
        pytest.fail("ltc normalize blocked while opening a FIFO input")

    assert result.returncode == 2
    assert parse_error(result.stderr)["error"] == {
        "code": "input-error",
        "message": "source must be a regular file",
    }
    assert output.read_bytes() == prior_output


def test_normalize_accepts_input_symlink_to_regular_file(
    run_ltc, tmp_path: Path
) -> None:
    target = tmp_path / "target.txt"
    target.write_text("At 13:15 the bell rang.\n", encoding="utf-8")
    source = tmp_path / "source.txt"
    source.symlink_to(target)
    output = tmp_path / "normalized.json"

    result = run_ltc("normalize", "--input", source, "--output", output)

    assert result.returncode == 0, result.stderr
    assert json.loads(output.read_text(encoding="utf-8"))["analysisText"] == (
        target.read_text(encoding="utf-8")
    )


def test_normalize_rejects_input_symlink_loop_and_preserves_output(
    run_ltc, tmp_path: Path
) -> None:
    source = tmp_path / "source.txt"
    source.symlink_to(source.name)
    output = tmp_path / "normalized.json"
    prior_output = b"keep this exact output\n"
    output.write_bytes(prior_output)

    result = run_ltc("normalize", "--input", source, "--output", output)

    assert result.returncode == 2
    assert parse_error(result.stderr)["error"]["code"] == "invalid-input-path"
    assert output.read_bytes() == prior_output


def test_normalize_preserves_domain_error_and_directory_output(
    run_ltc, tmp_path: Path
) -> None:
    output = tmp_path / "normalized.json"
    output.mkdir()

    result = run_ltc(
        "normalize",
        "--input",
        FIXTURES / "missing-start.txt",
        "--output",
        output,
        "--start-marker",
        START_MARKER,
        "--end-marker",
        END_MARKER,
    )

    assert result.returncode == 2
    assert parse_error(result.stderr)["error"]["code"] == "invalid-markers"
    assert output.is_dir()


def test_normalize_rejects_directory_input_without_leaking_path(
    run_ltc, tmp_path: Path
) -> None:
    source = tmp_path / "private-source-name"
    source.mkdir()
    output = tmp_path / "normalized.json"

    result = run_ltc("normalize", "--input", source, "--output", output)

    assert result.returncode == 2
    assert parse_error(result.stderr)["error"] == {
        "code": "input-error",
        "message": "source must be a regular file",
    }
    assert "private-source-name" not in result.stderr
    assert not output.exists()


def test_normalize_does_not_delete_non_regular_output_on_failure(
    run_ltc, tmp_path: Path
) -> None:
    output = tmp_path / "normalized.json"
    os.mkfifo(output)

    result = run_ltc(
        "normalize",
        "--input",
        FIXTURES / "missing-start.txt",
        "--output",
        output,
        "--start-marker",
        START_MARKER,
        "--end-marker",
        END_MARKER,
    )

    assert result.returncode == 2
    assert parse_error(result.stderr)["error"]["code"] == "invalid-markers"
    assert output.exists()


def test_normalize_rejects_duplicate_markers(run_ltc, tmp_path: Path) -> None:
    source = tmp_path / "duplicate.txt"
    source.write_text(
        f"{START_MARKER}\n"
        "first\n"
        f"{START_MARKER}\n"
        "second\n"
        f"{END_MARKER}\n",
        encoding="utf-8",
    )
    output = tmp_path / "normalized.json"

    result = run_ltc(
        "normalize",
        "--input",
        source,
        "--output",
        output,
        "--start-marker",
        START_MARKER,
        "--end-marker",
        END_MARKER,
    )

    assert result.returncode == 2
    assert parse_error(result.stderr)["error"]["code"] == "invalid-markers"
    assert not output.exists()


def test_normalize_rejects_non_utf8_without_replacing_bytes(
    run_ltc, tmp_path: Path
) -> None:
    source = tmp_path / "invalid-utf8.txt"
    source.write_bytes(
        b"*** START OF THE PROJECT GUTENBERG EBOOK BAD ***\n"
        b"invalid: \xff\n"
        b"*** END OF THE PROJECT GUTENBERG EBOOK BAD ***\n"
    )
    output = tmp_path / "normalized.json"

    result = run_ltc("normalize", "--input", source, "--output", output)

    assert result.returncode == 2
    assert parse_error(result.stderr) == {
        "error": {
            "code": "invalid-utf8",
            "message": "source is not valid UTF-8",
        }
    }
    assert not output.exists()

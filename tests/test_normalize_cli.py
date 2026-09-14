from __future__ import annotations

import json
import os
import stat
import subprocess
import threading
from pathlib import Path

import pytest


FIXTURES = Path(__file__).parent / "fixtures" / "normalize"


def parse_error(stderr: str) -> dict[str, object]:
    assert stderr.endswith("\n")
    assert len(stderr.splitlines()) == 1
    return json.loads(stderr)


def test_help_lists_the_four_approved_commands(run_ltc) -> None:
    result = run_ltc("--help")

    assert result.returncode == 0, result.stderr
    for command in ("normalize", "extract", "validate", "report"):
        assert command in result.stdout


def test_normalize_preserves_the_exact_utf8_body_and_provenance(
    run_ltc, tmp_path: Path
) -> None:
    output = tmp_path / "normalized.json"

    result = run_ltc(
        "normalize", "--input", FIXTURES / "valid.txt", "--output", output
    )

    assert result.returncode == 0, result.stderr
    document = json.loads(output.read_text(encoding="utf-8"))
    expected_body = (
        "At 1:17 a.m., café lamps still glowed.\n"
        "  The second line keeps leading spaces.\n"
    )
    assert document == {
        "analysisText": expected_body,
        "analysisTextSha256": (
            "13e61fdbb847a9956d83156ddc5a88e93bdd975aa93a8872477c1fffe66c96d5"
        ),
        "bodyEndByte": 179,
        "bodyStartByte": 99,
        "normalizationVersion": "normalize-v1",
        "schemaVersion": "normalized-source-v1",
        "sourceId": "synthetic_5e4fb58e2bad",
        "sourceSha256": (
            "5e4fb58e2bad12b054d129295152fba067b6147b7f11e2fcc83799ab511ccfb1"
        ),
        "transformationLog": [
            {
                "inputEndByte": 179,
                "inputStartByte": 99,
                "method": "project-gutenberg-marker-body-selection",
                "outputEndByte": 80,
                "outputStartByte": 0,
            }
        ],
    }
    source_bytes = (FIXTURES / "valid.txt").read_bytes()
    assert source_bytes[document["bodyStartByte"] : document["bodyEndByte"]] == (
        expected_body.encode("utf-8")
    )


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
    )

    assert result.returncode == 2
    assert parse_error(result.stderr) == {
        "error": {
            "code": "invalid-markers",
            "message": "source must contain exactly one complete START/END marker pair",
        }
    }
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


def test_normalize_replaces_output_symlink_swapped_after_path_validation(
    project_root: Path, tmp_path: Path
) -> None:
    source = tmp_path / "source.pipe"
    os.mkfifo(source)
    victim = tmp_path / "victim.json"
    victim.write_bytes(b"victim must survive\n")
    output = tmp_path / "normalized.json"
    reader_open = threading.Event()
    release_source = threading.Event()

    def feed_source() -> None:
        descriptor = os.open(source, os.O_WRONLY)
        try:
            reader_open.set()
            assert release_source.wait(timeout=10)
            os.write(descriptor, (FIXTURES / "valid.txt").read_bytes())
        finally:
            os.close(descriptor)

    feeder = threading.Thread(target=feed_source)
    feeder.start()
    process = subprocess.Popen(
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
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert reader_open.wait(timeout=10), "ltc did not open the coordinated input"
        output.symlink_to(victim)
        release_source.set()
        _stdout, stderr = process.communicate(timeout=10)
    finally:
        release_source.set()
        feeder.join(timeout=10)
        if process.poll() is None:
            process.kill()
            process.wait(timeout=10)

    assert process.returncode == 0, stderr
    assert not output.is_symlink()
    assert json.loads(output.read_text(encoding="utf-8"))["schemaVersion"] == (
        "normalized-source-v1"
    )
    assert victim.read_bytes() == b"victim must survive\n"
    assert stat.S_ISFIFO(source.lstat().st_mode)


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
    )

    assert result.returncode == 2
    assert parse_error(result.stderr)["error"]["code"] == "invalid-markers"
    assert output.is_dir()


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
    )

    assert result.returncode == 2
    assert parse_error(result.stderr)["error"]["code"] == "invalid-markers"
    assert output.exists()


def test_normalize_rejects_duplicate_markers(run_ltc, tmp_path: Path) -> None:
    source = tmp_path / "duplicate.txt"
    source.write_text(
        "*** START OF THE PROJECT GUTENBERG EBOOK FIRST ***\n"
        "first\n"
        "*** START OF THE PROJECT GUTENBERG EBOOK SECOND ***\n"
        "second\n"
        "*** END OF THE PROJECT GUTENBERG EBOOK SECOND ***\n",
        encoding="utf-8",
    )
    output = tmp_path / "normalized.json"

    result = run_ltc("normalize", "--input", source, "--output", output)

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

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from literary_time_corpus.extract import ExtractionError, extract_file
from literary_time_corpus.io import OutputPathError
from literary_time_corpus.normalize import NormalizationError, normalize_file
from literary_time_corpus.report import ReportError, report_file
from literary_time_corpus.scan import ScanError, scan_file
from literary_time_corpus.validate import (
    ReleaseValidationError,
    ValidationInputError,
    validate_file,
)


class CommandError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise CommandError("invalid-arguments", message)


def build_parser() -> argparse.ArgumentParser:
    parser = JsonArgumentParser(prog="ltc")
    subparsers = parser.add_subparsers(dest="command", required=True)

    normalize = subparsers.add_parser(
        "normalize", help="preserve and hash a literary source body"
    )
    normalize.add_argument("--input", type=Path, required=True)
    normalize.add_argument("--output", type=Path, required=True)
    normalize.add_argument("--start-marker")
    normalize.add_argument("--end-marker")

    extract = subparsers.add_parser("extract", help="extract time candidates")
    extract.add_argument("--input", type=Path, required=True)
    extract.add_argument("--output", type=Path, required=True)
    validate = subparsers.add_parser("validate", help="validate a release candidate")
    validate.add_argument("--analysis", type=Path, required=True)
    validate.add_argument("--candidate", type=Path, required=True)
    validate.add_argument("--review", type=Path, required=True)
    validate.add_argument("--rights", type=Path, required=True)
    validate.add_argument("--output", type=Path, required=True)
    report = subparsers.add_parser("report", help="summarize candidate output")
    report.add_argument("--input", type=Path, required=True)
    report.add_argument("--output", type=Path, required=True)
    scan = subparsers.add_parser("scan", help="scan a local UTF-8 TXT file")
    scan.add_argument("input", type=Path)
    scan.add_argument("--output", type=Path, required=True)
    scan.add_argument("--title")
    scan.add_argument("--author")
    scan.add_argument("--source-url")
    scan.add_argument("--start-marker")
    scan.add_argument("--end-marker")
    scan.add_argument("--force", action="store_true")
    return parser


def write_error(
    code: str,
    message: str,
    *,
    exit_code: int,
    details: dict[str, object] | None = None,
) -> int:
    envelope = {"error": {"code": code, "message": message}}
    if details is not None:
        envelope["error"]["details"] = details
    sys.stderr.write(
        json.dumps(envelope, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    )
    return exit_code


def validate_normalize_paths(input_path: Path, output_path: Path) -> None:
    try:
        resolved_input = input_path.resolve(strict=False)
    except (OSError, RuntimeError) as error:
        raise CommandError(
            "invalid-input-path", "could not resolve input path"
        ) from error

    if output_path.is_symlink():
        raise CommandError(
            "unsafe-output-path", "output path must not be a symbolic link"
        )

    try:
        resolved_output = output_path.resolve(strict=False)
    except (OSError, RuntimeError) as error:
        raise OutputPathError() from error

    try:
        paths_are_same = input_path.samefile(output_path)
    except OSError:
        paths_are_same = resolved_input == resolved_output
    if paths_are_same:
        raise CommandError(
            "unsafe-output-path", "input and output must refer to different files"
        )


def main(argv: Sequence[str] | None = None) -> int:
    try:
        arguments = build_parser().parse_args(argv)
        if arguments.command == "normalize":
            if (arguments.start_marker is None) != (arguments.end_marker is None):
                raise CommandError(
                    "invalid-arguments",
                    "--start-marker and --end-marker must be supplied together",
                )
            validate_normalize_paths(arguments.input, arguments.output)
            normalize_file(
                arguments.input,
                arguments.output,
                start_marker=arguments.start_marker,
                end_marker=arguments.end_marker,
            )
            return 0
        if arguments.command == "extract":
            validate_normalize_paths(arguments.input, arguments.output)
            extract_file(arguments.input, arguments.output)
            return 0
        if arguments.command == "validate":
            for input_path in (
                arguments.analysis,
                arguments.candidate,
                arguments.review,
                arguments.rights,
            ):
                validate_normalize_paths(input_path, arguments.output)
            validate_file(
                arguments.analysis,
                arguments.candidate,
                arguments.review,
                arguments.rights,
                arguments.output,
            )
            return 0
        if arguments.command == "report":
            validate_normalize_paths(arguments.input, arguments.output)
            report_file(arguments.input, arguments.output)
            return 0
        if arguments.command == "scan":
            summary = scan_file(
                arguments.input,
                arguments.output,
                title=arguments.title,
                author=arguments.author,
                source_url=arguments.source_url,
                start_marker=arguments.start_marker,
                end_marker=arguments.end_marker,
                force=arguments.force,
            )
            sys.stdout.write(
                json.dumps(
                    summary,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n"
            )
            return 0
        raise CommandError("not-implemented", f"{arguments.command} is not implemented")
    except ScanError as error:
        return write_error(
            error.code,
            str(error),
            exit_code=error.exit_code,
            details=error.details,
        )
    except (
        CommandError,
        ExtractionError,
        NormalizationError,
        OutputPathError,
        ReportError,
        ReleaseValidationError,
        ValidationInputError,
    ) as error:
        return write_error(
            error.code,
            str(error),
            exit_code=2,
            details=getattr(error, "details", None),
        )
    except Exception:
        return write_error(
            "internal-error", "an unexpected internal error occurred", exit_code=1
        )

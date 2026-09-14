from __future__ import annotations

import argparse
import json
import stat
import sys
from pathlib import Path
from typing import Sequence

from literary_time_corpus.extract import ExtractionError, extract_file
from literary_time_corpus.normalize import NormalizationError, normalize_file
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

    extract = subparsers.add_parser("extract", help="extract time candidates")
    extract.add_argument("--input", type=Path, required=True)
    extract.add_argument("--output", type=Path, required=True)
    validate = subparsers.add_parser("validate", help="validate a release candidate")
    validate.add_argument("--analysis", type=Path, required=True)
    validate.add_argument("--candidate", type=Path, required=True)
    validate.add_argument("--review", type=Path, required=True)
    validate.add_argument("--rights", type=Path, required=True)
    validate.add_argument("--output", type=Path, required=True)
    subparsers.add_parser("report", help="summarize candidate output")
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
    if output_path.is_symlink():
        raise CommandError(
            "unsafe-output-path", "output path must not be a symbolic link"
        )

    try:
        paths_are_same = input_path.samefile(output_path)
    except OSError:
        paths_are_same = input_path.resolve(strict=False) == output_path.resolve(
            strict=False
        )
    if paths_are_same:
        raise CommandError(
            "unsafe-output-path", "input and output must refer to different files"
        )


def regular_file_identity(path: Path) -> tuple[int, int] | None:
    try:
        metadata = path.lstat()
    except OSError:
        return None
    if not stat.S_ISREG(metadata.st_mode):
        return None
    return metadata.st_dev, metadata.st_ino


def remove_unchanged_regular_file(
    path: Path, expected_identity: tuple[int, int] | None
) -> None:
    if expected_identity is None:
        return
    try:
        metadata = path.lstat()
        if stat.S_ISREG(metadata.st_mode) and (
            metadata.st_dev,
            metadata.st_ino,
        ) == expected_identity:
            path.unlink()
    except OSError:
        pass


def main(argv: Sequence[str] | None = None) -> int:
    try:
        arguments = build_parser().parse_args(argv)
        if arguments.command == "normalize":
            validate_normalize_paths(arguments.input, arguments.output)
            prior_output = regular_file_identity(arguments.output)
            try:
                normalize_file(arguments.input, arguments.output)
            except Exception:
                remove_unchanged_regular_file(arguments.output, prior_output)
                raise
            return 0
        if arguments.command == "extract":
            validate_normalize_paths(arguments.input, arguments.output)
            prior_output = regular_file_identity(arguments.output)
            try:
                extract_file(arguments.input, arguments.output)
            except Exception:
                remove_unchanged_regular_file(arguments.output, prior_output)
                raise
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
        raise CommandError("not-implemented", f"{arguments.command} is not implemented")
    except (
        CommandError,
        ExtractionError,
        NormalizationError,
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

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from literary_time_corpus.normalize import NormalizationError, normalize_file


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

    subparsers.add_parser("extract", help="extract time candidates")
    subparsers.add_parser("validate", help="validate a release candidate")
    subparsers.add_parser("report", help="summarize candidate output")
    return parser


def write_error(code: str, message: str, *, exit_code: int) -> int:
    envelope = {"error": {"code": code, "message": message}}
    sys.stderr.write(
        json.dumps(envelope, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    )
    return exit_code


def main(argv: Sequence[str] | None = None) -> int:
    try:
        arguments = build_parser().parse_args(argv)
        if arguments.command == "normalize":
            normalize_file(arguments.input, arguments.output)
            return 0
        raise CommandError("not-implemented", f"{arguments.command} is not implemented")
    except (CommandError, NormalizationError) as error:
        return write_error(error.code, str(error), exit_code=2)
    except Exception:
        return write_error(
            "internal-error", "an unexpected internal error occurred", exit_code=1
        )

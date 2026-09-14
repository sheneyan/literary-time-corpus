from __future__ import annotations

import json
import os
import secrets
from pathlib import Path
from typing import Any, Iterable


class OutputPathError(ValueError):
    def __init__(self) -> None:
        super().__init__("could not write output path")
        self.code = "invalid-output-path"


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def write_bytes_atomic(path: Path, chunks: Iterable[bytes]) -> None:
    try:
        parent = path.parent.resolve()
        destination_name = path.name
        directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        directory_descriptor = os.open(parent, directory_flags)
    except OSError as error:
        raise OutputPathError() from error
    temporary_name: str | None = None
    try:
        while temporary_name is None:
            candidate_name = f".{destination_name}.{secrets.token_hex(8)}.tmp"
            try:
                file_descriptor = os.open(
                    candidate_name,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                    0o600,
                    dir_fd=directory_descriptor,
                )
            except FileExistsError:
                continue
            temporary_name = candidate_name

        with os.fdopen(file_descriptor, "wb") as temporary:
            for chunk in chunks:
                temporary.write(chunk)
            temporary.flush()
            os.fsync(temporary.fileno())
        try:
            os.replace(
                temporary_name,
                destination_name,
                src_dir_fd=directory_descriptor,
                dst_dir_fd=directory_descriptor,
            )
        except OSError as error:
            raise OutputPathError() from error
        temporary_name = None
    except OSError as error:
        raise OutputPathError() from error
    finally:
        if temporary_name is not None:
            try:
                os.unlink(temporary_name, dir_fd=directory_descriptor)
            except FileNotFoundError:
                pass
        os.close(directory_descriptor)


def write_json_atomic(path: Path, value: Any) -> None:
    write_bytes_atomic(path, (canonical_json_bytes(value),))


def write_jsonl_atomic(path: Path, values: Iterable[Any]) -> None:
    write_bytes_atomic(path, (canonical_json_bytes(value) for value in values))

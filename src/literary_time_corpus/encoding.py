from __future__ import annotations

from typing import Any


def all_strings_encode_utf8(value: Any) -> bool:
    if isinstance(value, str):
        try:
            value.encode("utf-8")
        except UnicodeEncodeError:
            return False
        return True
    if isinstance(value, list):
        return all(all_strings_encode_utf8(item) for item in value)
    if isinstance(value, dict):
        return all(
            all_strings_encode_utf8(key) and all_strings_encode_utf8(item)
            for key, item in value.items()
        )
    return True

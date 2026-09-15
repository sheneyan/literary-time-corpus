from __future__ import annotations

from typing import Any


MAX_CONTAINER_NODES = 100_000


def all_strings_encode_utf8(value: Any) -> bool:
    """Check nested list/dict strings without recursion or unbounded traversal."""
    pending = [value]
    visited_containers: set[int] = set()
    while pending:
        current = pending.pop()
        if isinstance(current, str):
            try:
                current.encode("utf-8")
            except UnicodeEncodeError:
                return False
            continue
        if not isinstance(current, (list, dict)):
            continue
        identity = id(current)
        if identity in visited_containers:
            continue
        visited_containers.add(identity)
        if len(visited_containers) > MAX_CONTAINER_NODES:
            return False
        if isinstance(current, list):
            pending.extend(current)
        else:
            for key, item in current.items():
                pending.append(key)
                pending.append(item)
    return True

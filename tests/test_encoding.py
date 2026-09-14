from __future__ import annotations

from literary_time_corpus.candidate import work_metadata_violations
from literary_time_corpus.encoding import all_strings_encode_utf8


def test_utf8_string_validation_is_cycle_safe() -> None:
    cyclic: dict[str, object] = {"label": "valid"}
    cyclic["self"] = cyclic

    assert all_strings_encode_utf8(cyclic)


def test_utf8_string_validation_is_safe_for_deep_containers() -> None:
    root: list[object] = []
    current = root
    for _ in range(5_000):
        child: list[object] = []
        current.append(child)
        current = child
    current.append("valid")

    assert all_strings_encode_utf8(root)


def test_work_metadata_validation_handles_cyclic_malformed_field() -> None:
    metadata: dict[str, object] = {
        "author": "Example Author",
        "metadataComplete": True,
        "schemaVersion": "scan-work-metadata-v1",
        "sourceUrl": None,
        "title": "Example Book",
    }
    metadata["sourceUrl"] = metadata

    assert "invalid-sourceUrl" in work_metadata_violations(metadata)

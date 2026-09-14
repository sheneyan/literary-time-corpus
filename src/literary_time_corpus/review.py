from __future__ import annotations

import re
import string

from literary_time_corpus.candidate import (
    candidate_record_violations,
    work_metadata_violations,
)


GROUPS = (
    ("resolved", "Exact-minute resolved"),
    ("ambiguous", "Exact-minute ambiguous"),
    ("excluded", "Approximate or excluded"),
)
BACKTICK_RUN = re.compile(r"`+")
CONTROL_WHITESPACE = {
    "\t": r"\t",
    "\n": r"\n",
    "\v": r"\v",
    "\f": r"\f",
    "\r": r"\r",
}


def _escape_markdown(value: str) -> str:
    rendered: list[str] = []
    for character in value:
        if character in CONTROL_WHITESPACE:
            rendered.append(CONTROL_WHITESPACE[character])
        elif character.isspace() and character != " ":
            codepoint = ord(character)
            rendered.append(
                f"\\u{codepoint:04x}"
                if codepoint <= 0xFFFF
                else f"\\U{codepoint:08x}"
            )
        elif character in string.punctuation:
            rendered.append(f"\\{character}")
        else:
            rendered.append(character)
    return "".join(rendered)


def _fenced_text(value: str) -> str:
    longest_run = max(
        (len(match.group()) for match in BACKTICK_RUN.finditer(value)),
        default=0,
    )
    fence = "`" * max(3, longest_run + 1)
    closing_prefix = "" if value.endswith("\n") else "\n"
    return f"{fence}text\n{value}{closing_prefix}{fence}"


def _review_group(candidate: dict[str, object]) -> str:
    if (
        candidate["status"] == "automatically-excluded"
        or candidate["precision"] == "approximate"
    ):
        return "excluded"
    if candidate["precision"] == "exact-minute-ambiguous":
        return "ambiguous"
    return "resolved"


def _render_reasons(values: list[str]) -> str:
    if not values:
        return "none"
    return ", ".join(_escape_markdown(value) for value in values)


def _render_candidate(candidate: dict[str, object], ordinal: int) -> list[str]:
    normalized_times = candidate["normalizedTimes"]
    assert isinstance(normalized_times, list)
    matched_text = candidate["matchedText"]
    context = candidate["context"]
    rule_id = candidate["ruleId"]
    warnings = candidate["warningReasonCodes"]
    exclusions = candidate["exclusionReasonCodes"]
    candidate_id = candidate["candidateId"]
    assert isinstance(matched_text, str)
    assert isinstance(context, str)
    assert isinstance(rule_id, str)
    assert isinstance(warnings, list)
    assert isinstance(exclusions, list)
    assert isinstance(candidate_id, str)
    rendered_times = (
        ", ".join(normalized_times)
        if normalized_times
        else "none"
    )
    return [
        f"### Candidate {ordinal}",
        "",
        f"Normalized time(s): {rendered_times}",
        "",
        "Matched expression:",
        "",
        _fenced_text(matched_text),
        "",
        "Context:",
        "",
        _fenced_text(context),
        "",
        f"Rule ID: {_escape_markdown(rule_id)}",
        f"Warnings: {_render_reasons(warnings)}",
        f"Exclusions: {_render_reasons(exclusions)}",
        f"Candidate ID: `{candidate_id}`",
        "",
    ]


def render_review_markdown(
    candidates: list[dict[str, object]],
    work_metadata: dict[str, object],
) -> bytes:
    if work_metadata_violations(work_metadata):
        raise ValueError("invalid work metadata")
    candidate_violations = [
        candidate_record_violations(candidate) for candidate in candidates
    ]
    if any(candidate_violations):
        raise ValueError("invalid candidate")

    grouped = {key: [] for key, _ in GROUPS}
    for candidate in candidates:
        grouped[_review_group(candidate)].append(candidate)

    title = work_metadata["title"]
    author = work_metadata["author"]
    metadata_complete = work_metadata["metadataComplete"]
    assert isinstance(title, str)
    assert isinstance(author, str)
    assert isinstance(metadata_complete, bool)
    lines = [
        "# Literary time candidate review",
        "",
        f"Title: {_escape_markdown(title)}",
        f"Author: {_escape_markdown(author)}",
        f"Metadata complete: {'yes' if metadata_complete else 'no'}",
        f"Candidate count: {len(candidates)}",
        "",
        "This file is a review view, not a review record.",
        "Candidates are not approved for publication.",
        "The user is responsible for permission to process the input text.",
        "",
    ]
    for group_key, heading in GROUPS:
        lines.extend((f"## {heading}", ""))
        for ordinal, candidate in enumerate(grouped[group_key], start=1):
            lines.extend(_render_candidate(candidate, ordinal))

    return "\n".join(lines).rstrip("\n").encode("utf-8") + b"\n"

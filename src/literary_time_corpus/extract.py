from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Callable

from literary_time_corpus.candidate import (
    candidate_record_violations,
    work_metadata_violations,
)
from literary_time_corpus.io import write_jsonl_atomic
from literary_time_corpus.normalized import normalized_record_violations


SCHEMA_VERSION = "time-candidate-v1"
EXTRACTION_VERSION = "extract-v1"


class ExtractionError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "twenty": 20,
    "twenty-one": 21,
    "twenty-two": 22,
    "twenty-three": 23,
    "twenty-four": 24,
    "twenty-five": 25,
    "twenty-six": 26,
    "twenty-seven": 27,
    "twenty-eight": 28,
    "twenty-nine": 29,
}
HOUR_WORDS = {word: value for word, value in NUMBER_WORDS.items() if value <= 12}
NUMBER_PATTERN = "|".join(sorted(NUMBER_WORDS, key=len, reverse=True))
HOUR_PATTERN = "|".join(sorted(HOUR_WORDS, key=len, reverse=True))
SCRIPTURE_REFERENCE_BEFORE = re.compile(
    r"\b(?:[1-3]\s*)?(?:"
    r"gen(?:esis)?|exod(?:us)?|lev(?:iticus)?|num(?:bers)?|deut(?:eronomy)?|"
    r"josh(?:ua)?|judg(?:es)?|ruth|sam(?:uel)?|kings?|chron(?:icles)?|ezra|"
    r"neh(?:emiah)?|esth(?:er)?|job|ps(?:alms?)?|prov(?:erbs)?|"
    r"eccl(?:esiastes)?|song(?:\s+of\s+(?:songs|solomon))?|isa(?:iah)?|"
    r"jer(?:emiah)?|lam(?:entations)?|ezek(?:iel)?|dan(?:iel)?|hos(?:ea)?|"
    r"joel|amos|obad(?:iah)?|jonah|mic(?:ah)?|nah(?:um)?|hab(?:akkuk)?|"
    r"zeph(?:aniah)?|hag(?:gai)?|zech(?:ariah)?|mal(?:achi)?|matt(?:hew)?|"
    r"mark|luke|john|acts|rom(?:ans)?|cor(?:inthians)?|gal(?:atians)?|"
    r"eph(?:esians)?|phil(?:ippians)?|col(?:ossians)?|thess(?:alonians)?|"
    r"tim(?:othy)?|titus|philem(?:on)?|heb(?:rews)?|james|peter|jude|"
    r"rev(?:elation)?"
    r")\.?\s+$",
    re.IGNORECASE,
)


def _read_normalized(path: Path) -> dict[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ExtractionError(
            "invalid-normalized-source", "could not read a normalized source document"
        ) from error

    violations = normalized_record_violations(document)
    if "analysis-hash-mismatch" in violations:
        raise ExtractionError(
            "invalid-normalized-source",
            "analysis text hash does not match its content",
        )
    if "source-identity-mismatch" in violations:
        raise ExtractionError(
            "invalid-normalized-source",
            "source identity is inconsistent with carried source hash",
        )
    if violations:
        raise ExtractionError(
            "invalid-normalized-source", "normalized source document is malformed"
        )
    return document


def _byte_offset(text: str, character_offset: int) -> int:
    return len(text[:character_offset].encode("utf-8"))


def _clock(hour: int, minute: int) -> str:
    return f"{hour:02d}:{minute:02d}"


def _twelve_hour_values(hour: int, minute: int) -> list[str]:
    morning = hour % 12
    return [_clock(morning, minute), _clock(morning + 12, minute)]


def _candidate(
    document: dict[str, Any],
    match: re.Match[str],
    *,
    rule_family: str,
    rule_id: str,
    normalized_times: list[str],
    precision: str,
    status: str = "detected",
    exclusions: list[str] | None = None,
    warnings: list[str] | None = None,
    contextual_resolution: dict[str, Any] | None = None,
) -> dict[str, Any]:
    analysis = document["analysisText"]
    match_start = _byte_offset(analysis, match.start())
    match_end = _byte_offset(analysis, match.end())
    excerpt_character_start = max(0, match.start() - 80)
    excerpt_character_end = min(len(analysis), match.end() + 80)
    excerpt_start = _byte_offset(analysis, excerpt_character_start)
    excerpt_end = _byte_offset(analysis, excerpt_character_end)
    quote_before = analysis[excerpt_character_start : match.start()]
    quote_time = match.group(0)
    quote_after = analysis[match.end() : excerpt_character_end]
    excerpt = quote_before + quote_time + quote_after
    identity = "\0".join(
        (
            document["sourceId"],
            document["analysisTextSha256"],
            str(match_start),
            str(match_end),
        )
    )
    return {
        "analysisTextSha256": document["analysisTextSha256"],
        "candidateId": hashlib.sha256(identity.encode("utf-8")).hexdigest(),
        "context": excerpt,
        "contextualResolution": contextual_resolution,
        "excerpt": excerpt,
        "excerptEndByte": excerpt_end,
        "excerptStartByte": excerpt_start,
        "exclusionReasonCodes": exclusions or [],
        "extractionVersion": EXTRACTION_VERSION,
        "matchEndByte": match_end,
        "matchStartByte": match_start,
        "matchedText": quote_time,
        "normalizationVersion": document["normalizationVersion"],
        "normalizedTimes": normalized_times,
        "precision": precision,
        "quoteAfter": quote_after,
        "quoteBefore": quote_before,
        "quoteTime": quote_time,
        "ruleFamily": rule_family,
        "ruleId": rule_id,
        "schemaVersion": SCHEMA_VERSION,
        "sourceId": document["sourceId"],
        "sourceHashStatus": "carried-from-normalization",
        "sourceSha256": document["sourceSha256"],
        "status": status,
        "warningReasonCodes": warnings or [],
    }


def extract_candidates(
    document: dict[str, Any],
    work_metadata: dict[str, object] | None = None,
) -> list[dict[str, Any]]:
    if work_metadata is not None and work_metadata_violations(work_metadata):
        raise ExtractionError(
            "invalid-work-metadata", "work metadata is malformed"
        )
    text = document["analysisText"]
    candidates: list[dict[str, Any]] = []
    occupied: list[tuple[int, int]] = []

    def add_matches(
        pattern: re.Pattern[str],
        build: Callable[[re.Match[str]], dict[str, Any] | None],
    ) -> None:
        for match in pattern.finditer(text):
            if any(match.start() < end and match.end() > start for start, end in occupied):
                continue
            candidate = build(match)
            if candidate is not None:
                if work_metadata is not None:
                    candidate["workMetadata"] = dict(work_metadata)
                candidates.append(candidate)
                occupied.append((match.start(), match.end()))

    approximate = re.compile(
        rf"\babout\s+({HOUR_PATTERN})\s+o'clock\b", re.IGNORECASE
    )
    add_matches(
        approximate,
        lambda match: _candidate(
            document,
            match,
            rule_family="approximate-clock",
            rule_id="approx-about-oclock-v1",
            normalized_times=[],
            precision="approximate",
            status="automatically-excluded",
            exclusions=["approximate-expression"],
        ),
    )

    approximate_numeric = re.compile(
        r"\b(?:about|approximately)\s+(?:[01]?[0-9]|2[0-3]):[0-5][0-9](?![0-9:]|\s*(?:hours?|minutes?|seconds?)\b)",
        re.IGNORECASE,
    )
    add_matches(
        approximate_numeric,
        lambda match: _candidate(
            document,
            match,
            rule_family="approximate-clock",
            rule_id="approx-numeric-v1",
            normalized_times=[],
            precision="approximate",
            status="automatically-excluded",
            exclusions=["approximate-expression"],
        ),
    )

    numeric_meridiem = re.compile(
        r"(?<![\w$])((?:0?[1-9]|1[0-2])):([0-5][0-9])\s*([ap])\.?m\.?(?!\w)",
        re.IGNORECASE,
    )

    def build_meridiem(match: re.Match[str]) -> dict[str, Any]:
        hour = int(match.group(1)) % 12
        if match.group(3).lower() == "p":
            hour += 12
        evidence = re.search(r"[ap]\.?m\.?$", match.group(0), re.IGNORECASE)
        assert evidence is not None
        return _candidate(
            document,
            match,
            rule_family="numeric-12-hour",
            rule_id="numeric-12h-meridiem-v1",
            normalized_times=[_clock(hour, int(match.group(2)))],
            precision="exact-minute-resolved",
            contextual_resolution={
                "evidenceEndByte": _byte_offset(text, match.start() + evidence.end()),
                "evidenceStartByte": _byte_offset(text, match.start() + evidence.start()),
                "evidenceText": evidence.group(0),
                "method": "explicit-meridiem",
            },
        )

    add_matches(numeric_meridiem, build_meridiem)

    written_minutes = re.compile(
        rf"\b({NUMBER_PATTERN})\s+minutes?\s+(past|to)\s+({HOUR_PATTERN})\b",
        re.IGNORECASE,
    )

    def build_written_minutes(match: re.Match[str]) -> dict[str, Any] | None:
        minute = NUMBER_WORDS[match.group(1).lower()]
        hour = HOUR_WORDS[match.group(3).lower()]
        if match.group(2).lower() == "to":
            hour = (hour - 1) % 12
            minute = 60 - minute
        return _candidate(
            document,
            match,
            rule_family="written-minutes",
            rule_id="written-minutes-past-to-v1",
            normalized_times=_twelve_hour_values(hour, minute),
            precision="exact-minute-ambiguous",
            warnings=["missing-meridiem"],
        )

    add_matches(written_minutes, build_written_minutes)

    fraction = re.compile(
        rf"\b(?:a\s+)?(quarter|half)\s+(past|to)\s+({HOUR_PATTERN})\b", re.IGNORECASE
    )

    def build_fraction(match: re.Match[str]) -> dict[str, Any] | None:
        fraction_word, relation = match.group(1).lower(), match.group(2).lower()
        if fraction_word == "half" and relation == "to":
            return None
        hour = HOUR_WORDS[match.group(3).lower()]
        minute = 30 if fraction_word == "half" else 15
        if relation == "to":
            hour = (hour - 1) % 12
            minute = 60 - minute
        return _candidate(
            document,
            match,
            rule_family="written-fraction",
            rule_id="written-quarter-half-v1",
            normalized_times=_twelve_hour_values(hour, minute),
            precision="exact-minute-ambiguous",
            warnings=["missing-meridiem"],
        )

    add_matches(fraction, build_fraction)

    named = re.compile(r"\b(noon|midnight)\b", re.IGNORECASE)
    add_matches(
        named,
        lambda match: _candidate(
            document,
            match,
            rule_family="named-time",
            rule_id="named-noon-midnight-v1",
            normalized_times=["12:00" if match.group(1).lower() == "noon" else "00:00"],
            precision="exact-minute-resolved",
            contextual_resolution={
                "evidenceEndByte": _byte_offset(text, match.end()),
                "evidenceStartByte": _byte_offset(text, match.start()),
                "evidenceText": match.group(0),
                "method": "named-time",
            },
        ),
    )

    numeric_bare = re.compile(
        r"(?<![\w$€£¥])([1-9]|1[0-9]|2[0-3]|0[0-9]):([0-5][0-9])(?![0-9])"
    )

    def build_bare(match: re.Match[str]) -> dict[str, Any] | None:
        following = text[match.end() : match.end() + 12]
        preceding = text[max(0, match.start() - 32) : match.start()]
        if re.match(
            r"(?::[0-5][0-9]|\s*[ap]\.?m\.?(?!\w)|\s+(?:hours?|minutes?|seconds?)\b)",
            following,
            re.IGNORECASE,
        ):
            return None
        if re.search(r"[$€£¥]\s*$", preceding):
            return None
        if re.search(r"\b(?:chapter|verse)\s+$", preceding, re.IGNORECASE):
            return None
        if SCRIPTURE_REFERENCE_BEFORE.search(preceding):
            return None
        raw_hour = match.group(1)
        hour, minute = int(raw_hour), int(match.group(2))
        if hour >= 13 or (len(raw_hour) == 2 and raw_hour.startswith("0")):
            return _candidate(
                document,
                match,
                rule_family="numeric-24-hour",
                rule_id="numeric-24h-v1",
                normalized_times=[_clock(hour, minute)],
                precision="exact-minute-resolved",
                contextual_resolution={
                    "evidenceEndByte": _byte_offset(text, match.end()),
                    "evidenceStartByte": _byte_offset(text, match.start()),
                    "evidenceText": match.group(0),
                    "method": "explicit-24-hour-clock",
                },
            )
        if hour == 0:
            return _candidate(
                document,
                match,
                rule_family="numeric-24-hour",
                rule_id="numeric-24h-v1",
                normalized_times=[_clock(hour, minute)],
                precision="exact-minute-resolved",
                contextual_resolution={
                    "evidenceEndByte": _byte_offset(text, match.end()),
                    "evidenceStartByte": _byte_offset(text, match.start()),
                    "evidenceText": match.group(0),
                    "method": "explicit-24-hour-clock",
                },
            )
        return _candidate(
            document,
            match,
            rule_family="numeric-12-hour",
            rule_id="numeric-12h-bare-v1",
            normalized_times=_twelve_hour_values(hour, minute),
            precision="exact-minute-ambiguous",
            warnings=["missing-meridiem"],
        )

    add_matches(numeric_bare, build_bare)
    return sorted(
        candidates,
        key=lambda candidate: (
            candidate["matchStartByte"],
            candidate["matchEndByte"],
            candidate["candidateId"],
        ),
    )


def extract_file(input_path: Path, output_path: Path) -> None:
    document = _read_normalized(input_path)
    candidates = extract_candidates(document)
    if any(candidate_record_violations(candidate) for candidate in candidates):
        raise ExtractionError(
            "candidate-generation-failed",
            "generated candidate failed validation",
        )
    write_jsonl_atomic(output_path, candidates)

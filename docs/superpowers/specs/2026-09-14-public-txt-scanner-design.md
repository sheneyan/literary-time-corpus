# Public TXT scanner design

## Status

Approved conversational design for turning the Gate 2 pipeline into a
source-agnostic public tool. This document authorizes implementation planning,
not source acquisition, corpus publication, or deployment of host-specific
configuration.

## Goal

Let another person supply a local UTF-8 plain-text book and reproducibly
extract reviewable literary clock-time excerpts without knowing the internal
pipeline or preparing intermediate JSON by hand.

The primary public workflow is:

```bash
ltc scan book.txt --output scans/book
```

Project Gutenberg search, eligibility screening, and download are outside the
tool's scope. Gutenberg is one possible upstream source, not a required
provider. EPUB, PDF, and provider adapters are deferred; version 1 accepts only
local UTF-8 plain text.

## Architecture

The command-line interface has two layers:

- `ltc scan` is the user-facing workflow command.
- `ltc normalize`, `ltc extract`, `ltc validate`, and `ltc report` remain the
  stable composable commands for advanced use.

`scan` is an orchestration layer over the same Python modules used by the
lower-level commands. It must not invoke child processes or implement a second
normalizer, extractor, or reporter.

The version 1 data flow is:

```text
local UTF-8 TXT
  -> provider-neutral body normalization
  -> exact-time candidate extraction
  -> deterministic candidate report
  -> human-readable Markdown rendering
  -> self-contained local scan directory
```

The boundary before normalization is the future input-adapter seam. Version 1
does not publish a plugin API or anticipate concrete provider interfaces.

## Command interface

The minimum command is:

```bash
ltc scan INPUT.txt --output OUTPUT_DIRECTORY
```

Optional descriptive metadata is accepted without changing eligibility:

```bash
ltc scan book.txt \
  --output scans/book \
  --title "Example Book" \
  --author "Example Author" \
  --source-url "https://example.org/book"
```

When title is omitted, the input filename stem is recorded as a temporary
title. When author is omitted, it is recorded as `unknown`. The run and review
artifacts must say that metadata is incomplete. Incomplete metadata does not
block scanning, but it cannot satisfy the separate release gate.

Optional literal body markers are supported:

```bash
ltc scan book.txt \
  --output scans/book \
  --start-marker "CHAPTER I" \
  --end-marker "APPENDIX"
```

The default body is the complete decoded file. The tool performs no provider
guessing. If either marker is supplied, both are required. Each must occur
exactly once and the start must precede the end. The retained body begins after
the start marker and ends before the end marker; separator newlines immediately
adjacent to those markers are excluded using the same documented byte-range
semantics as the existing normalizer. Missing, duplicate, reversed, or empty
boundaries are controlled input errors.

The input must be a regular file that decodes strictly as UTF-8. Version 1 does
not perform character-set detection, lossy replacement, ebook conversion, OCR,
or newline normalization.

## Output directory

A successful scan creates exactly these public artifacts:

```text
OUTPUT_DIRECTORY/
├── normalized.json
├── candidates.jsonl
├── report.json
├── review.md
└── run.json
```

Their roles are:

- `normalized.json`: the provider-neutral normalized-source record, including
  analysis text, hashes, byte boundaries, and transformation log;
- `candidates.jsonl`: authoritative machine-readable immutable candidate
  observations;
- `report.json`: deterministic extraction and coverage statistics;
- `review.md`: a derived, human-readable review view; and
- `run.json`: a deterministic manifest binding the input, options, versions,
  metadata, and output hashes.

The directory contains analysis artifacts, not an approved corpus release.
Because `normalized.json` contains the complete retained body, scan directories
belong in ignored local storage by default and must not be committed to this
repository.

## Output replacement and transactional safety

If the output directory does not exist, `scan` creates it only after all five
artifacts have been generated and verified in a sibling temporary directory.

If the output directory already exists, the default behavior is a controlled
error. The command never merges into it or overwrites individual files.

`--force` authorizes replacement of that exact output directory. The command
still generates and verifies the complete new directory first. Cross-platform
Python cannot atomically replace an existing non-empty directory, so the tool
uses a guarded same-parent transaction: rename the old directory to a unique
backup, rename the verified new directory into place, then remove the backup.
If the second rename fails, it restores the backup before returning an error.
There may be a brief interval in which the output pathname is absent, but it
must never expose a partially generated directory. Replacement must not follow
a final-component symbolic link and must preserve unrelated sibling paths.
Temporary and backup directories are removed after success; a failed rollback
retains the backup and reports its non-sensitive basename for manual recovery.

Failure cleanup for an invocation-owned staging directory or a newly published
directory is retention-only. The command creates a unique same-parent `0700`
quarantine, atomically moves the current path entry into it without following
symbolic links, inspects the moved device and inode, and retains the entry
regardless of whether that identity matches. It never recursively deletes or
restores the moved entry in-process and never overwrites a replacement at the
official path. The error reports only `retainedPathBasename` and
`officialPathStatus`. If quarantine creation or movement fails, the command
returns the distinct `scan-cleanup-failed` error with the non-sensitive official
path status and cannot report success.

The ownership snapshot and all staged artifact generation, write, build,
verification, and publication operations are inside the same ordinary-exception
boundary. Every such failure attempts retention and reports the retained
basename/status. Controlled domain errors preserve their code and stage;
unexpected exceptions use `internal-generation-failed` with stage `staging`.
The boundary does not catch `KeyboardInterrupt` or `SystemExit`.

Expected failures exit `2`; unexpected internal failures exit `1`. Errors use
the existing single-object JSON stderr envelope and add the failed stage to
`error.details.stage`. Standard output contains exactly one compact JSON object
on success with the status, output directory basename, candidate count, and
resolved-minute count. It never echoes an absolute output path.

Errors must not include source text, extracted excerpts, URL credentials,
machine usernames, or expanded absolute input paths.

## Candidate and review artifacts

`candidates.jsonl` remains the authoritative candidate artifact. Every row must
pass the shared `time-candidate-v1` validator and include:

- immutable source and candidate identity;
- source and analysis hashes;
- exact match and bounded unchanged context;
- UTF-8 byte offsets;
- rule family and rule identifier;
- normalized times and precision class;
- contextual resolution method and exact evidence where applicable; and
- explicit warning and exclusion reason arrays.

`review.md` is a projection, not a review database and not an input to
`validate`. It does not encode machine decisions from Markdown checkboxes.
Candidates are grouped in this order:

1. exact-minute resolved;
2. exact-minute ambiguous;
3. approximate or automatically excluded.

Each entry shows the normalized time or alternatives, unchanged context,
matched expression, rule, warning or exclusion reasons, and candidate ID.
Reviewers use the candidate ID when creating a formal append-only review JSON
record. An interactive terminal reviewer, browser UI, and CSV round trip are
deferred until actual use provides evidence for the right interface.

## Run manifest

`run.json` uses a new versioned schema and records:

- input basename and untouched input SHA-256;
- user-supplied title, author, and source URL values;
- an explicit `metadataComplete` boolean;
- body-boundary mode and literal marker values when supplied;
- normalized-source, candidate, report, and run schema/tool versions;
- SHA-256 and byte size of each of the other four output artifacts;
- total candidate count, resolved-minute count, and successful status.

It must not contain the absolute input path, current working directory,
username, hostname, temporary paths, wall-clock timestamp, random identifier,
or environment details. The source URL is descriptive user input only; scan
does not fetch it or interpret it as rights evidence. URLs containing userinfo
are rejected to prevent accidental credential persistence.

The manifest cannot include its own digest. Canonical JSON serialization and a
stable artifact ordering make every output byte-identical for identical input,
options, metadata, and tool versions.

## Normalization behavior

The existing provider-shaped START/END marker behavior becomes one explicit
marker mode inside a provider-neutral normalizer. The default full-file mode
selects byte range `0..len(inputBytes)` and records a deterministic
transformation-log entry for that selection. Marker mode records the selected
range and method without altering the retained bytes.

No mode trims body whitespace, changes line endings, modernizes spelling, or
performs Unicode normalization. An empty file or an empty/whitespace-only
retained body is rejected.

The source identity for a local file is deterministic and provider-neutral:
`local_<first 12 lowercase hexadecimal characters of sourceSha256>`. It does
not retain the existing `synthetic_` prefix. Changing this spelling later
requires a schema or normalizer version change.

## Rights boundary

Scanning is analysis, not publication approval. It requires no rights JSON and
does not call `validate`. The output must prominently state:

- the user is responsible for having permission to process the input;
- extracted candidates are not automatically public-domain or publishable;
- incomplete metadata is allowed only for analysis; and
- a public release still requires the separate human-review and US plus
  China-mainland rights gate currently implemented by `ltc validate`.

MIT covers the project-authored tool and documentation, not the user's source
text or generated excerpts.

## Determinism and validation

A scan is successful only after all produced normalized and candidate records
pass the same shared validators used by the lower-level commands. The report is
then regenerated from the final candidates. Before publication into the
output directory, `scan` recomputes every artifact digest recorded in
`run.json` and checks that the Markdown renderer consumed the same candidate
set.

For identical input bytes, options, metadata, and tool versions, all five files
must be byte-identical across runs. Filesystem paths, modification times, locale,
timezone, hash randomization, and directory enumeration order must not affect
content.

## Testing and acceptance

Tests continue to exercise only installed CLI behavior, exit status,
stdout/stderr, and public artifacts. They must cover:

- full-file scanning without provider markers;
- optional unique paired markers and every invalid-marker case;
- strict UTF-8, regular-file, empty-body, and whitespace-only-body failures;
- multibyte text before and inside matches with exact UTF-8 byte offsets;
- no-time input producing an empty JSONL, zero report, and empty review section;
- incomplete and complete metadata behavior;
- credential-bearing source URL rejection;
- byte-identical repeat runs;
- existing-directory refusal;
- successful transactional `--force` replacement and rollback;
- failure during forced generation preserving the complete previous directory;
- final-component symbolic-link and input/output alias safety;
- exact five-file output inventory and cross-artifact SHA-256 validation;
- absence of absolute paths, machine data, timestamps, and source excerpts from
  stdout and error output;
- every emitted candidate passing the shared validator;
- preservation of the existing lower-level command suite; and
- an installed wheel working in a clean virtual environment without the source
  tree or `uv` at runtime.

The packaged runtime remains Python 3.11+ and standard-library-only. Pytest and
build tooling are development dependencies.

## Deferred work

Version 1 explicitly defers:

- Project Gutenberg or other provider search, screening, and download;
- EPUB, PDF, HTML, OCR, and encoding conversion;
- a provider or converter plugin protocol;
- contextual AM/PM inference beyond the current extraction contract;
- an interactive review command or UI;
- automated legal conclusions;
- corpus packaging, dataset licensing, and public release; and
- UBTmini deployment or any host-specific configuration.

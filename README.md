# Literary Time Corpus

A traceable corpus of literary excerpts containing exact clock times, with
per-record provenance and rights evidence.

## Status

Literary Time Corpus v0.1.0 provides an offline, provider-neutral TXT scanner
for extracting literary time candidates from user-supplied UTF-8 text. It does
not acquire books or publish a quotation corpus. The command-line pipeline is
verified against repository-owned synthetic fixtures only.

## Principles

- The displayed time must occur in the literary original.
- Only expressions that resolve to one exact minute may become publishable.
- Original-language text is preserved; generated, rewritten, and machine-
  translated quotations are excluded.
- Every published record must be traceable to a fixed source snapshot and a
  documented rights decision.
- Software licensing, corpus or database licensing, and rights in each work and
  edition are evaluated separately.

## Current scope

The public tool scans one local UTF-8 TXT file and writes deterministic analysis
artifacts for machine processing and human review. Project Gutenberg is one
possible external source of eligible text, but it is not a dependency or
Provider implemented by this repository. Source discovery, acquisition, and
rights screening remain external responsibilities.

The project does not publish unreviewed excerpts, fill missing minutes with
approximate text, or implement the Literature Clock user interface.

Passing the current test suite is evidence about the synthetic pipeline; it
authorizes neither ebook acquisition nor publication. Those actions remain
subject to the gates in the pilot design and rights policy.

See the [project brief](docs/project-brief.md) for the confirmed scope, data
semantics, evaluation requirements, and publication gates.

## Scan a local TXT file

`ltc scan` is the primary workflow. It accepts one local plain-text file,
decodes it strictly as UTF-8, and works without a network connection or a
provider-specific format:

```bash
ltc scan book.txt --output book-scan
```

The output parent directory must already exist. Scan creates only the final
output directory (`book-scan` here), after all five staged artifacts pass
verification.

Version 1 is deliberately TXT-only. It does not detect other encodings, run
OCR, convert EPUB or PDF, search or download from Project Gutenberg, or expose
a `Provider` or converter API. Gutenberg is one possible upstream source, not
a dependency of the scanner.

Add descriptive metadata when it is known:

```bash
ltc scan book.txt \
  --output book-scan \
  --title "Example Book" \
  --author "Example Author" \
  --source-url "https://example.org/book"
```

Metadata is copied into the run and candidate records; `--source-url` is never
fetched and is not rights evidence. Without `--title` and `--author`, scanning
still succeeds for analysis, but `metadata.metadataComplete` is `false`.

To exclude literal front and back matter, supply both markers. Each marker must
occur exactly once and the start must precede the end:

```bash
ltc scan book.txt \
  --output book-scan \
  --start-marker "CHAPTER I" \
  --end-marker "APPENDIX"
```

An existing output directory is preserved by default. `--force` authorizes
replacement of that exact directory only:

```bash
ltc scan book.txt --output book-scan --force
```

Forced replacement is supported only when the platform provides the anchored
open, stat, private-directory creation, and no-replace rename primitives used
by the safe transaction. Otherwise the command fails before staging with
`error.code=unsupported-safe-replacement` and leaves the existing directory
unchanged. Creating a previously absent output does not require those forced-
replacement primitives.

### Outputs and scripting contract

A successful scan creates exactly five files:

```text
book-scan/
├── normalized.json
├── candidates.jsonl
├── report.json
├── review.md
└── run.json
```

- `normalized.json` contains the complete retained source body in
  `analysisText` (the whole file unless markers select a body).
- `candidates.jsonl` contains machine-readable observations and unchanged,
  bounded source context; `review.md` renders those contexts for a person.
- `report.json` contains aggregate extraction metrics, while `run.json` binds
  input hashes, options, versions, metadata, counts, and artifact hashes. These
  two do not contain the full source body or extracted context.

The five files are deterministic for identical input bytes, basename, options,
metadata, and tool versions. Scan outputs can contain copyrighted text, so
`scans/` is ignored and must not be committed.

Success exits `0`, writes no stderr, and writes exactly one compact JSON object
to stdout with `status`, `outputName`, `candidateCount`, and
`resolvedMinuteCount`. Expected input, output, or invariant failures exit `2`;
unexpected internal failures exit `1`. A failure writes exactly one JSON object
to stderr with `error.code`, `error.message`, and optional `error.details`, and
does not report success. If failed work is safely quarantined for inspection,
details expose only its basename through `retainedPathBasename`, never an
absolute path or source text.

### Installation

The v0.1.0 release was manually verified on macOS 26.5, Apple Silicon (`arm64`),
Python 3.11.16, and uv 0.10.0. Python 3.11 is the minimum runtime requirement.
Other operating systems, architectures, and Python versions are untested, not
unsupported.

For the current source checkout, install the locked development environment and
prefix commands with `uv run`:

```bash
uv sync --locked
uv run ltc scan book.txt --output book-scan
```

Install the v0.1.0 wheel directly from its GitHub Release:

```bash
python3 -m pip install \
  https://github.com/sheneyan/literary-time-corpus/releases/download/v0.1.0/literary_time_corpus-0.1.0-py3-none-any.whl
```

To install the current wheel in another environment:

```bash
uv build --wheel
python3 -m pip install dist/literary_time_corpus-0.1.0-py3-none-any.whl
ltc scan book.txt --output book-scan
```

If a release is published to PyPI in the future, installation can use
`python3 -m pip install literary-time-corpus`. The project does not currently
claim that a PyPI package is available.

### Analysis is not release approval

Scanning creates analysis and a Markdown review aid. `review.md` is not a
formal review record, and candidates are not automatically public-domain or
publishable. The user is responsible for permission to process the input.
Release still requires append-only human review plus the separate United States
and China-mainland rights decision enforced by `ltc validate`.

The MIT license covers only project-authored software and documentation. It
does not license user-supplied books, third-party editions, scan outputs,
excerpts, provider names, or a future dataset. See [DATA_RIGHTS.md](DATA_RIGHTS.md).

### Advanced commands

The same offline modules remain available as four composable commands. These
examples use repository-owned synthetic fixtures:

```bash
uv run ltc normalize \
  --input tests/fixtures/normalize/valid.txt \
  --output /tmp/ltc-normalized.json

uv run ltc extract \
  --input /tmp/ltc-normalized.json \
  --output /tmp/ltc-candidates.jsonl

uv run ltc report \
  --input tests/fixtures/report/candidates.jsonl \
  --output /tmp/ltc-report.json

uv run ltc validate \
  --analysis tests/fixtures/validate/analysis.json \
  --candidate tests/fixtures/validate/candidate.json \
  --review tests/fixtures/validate/review.json \
  --rights tests/fixtures/validate/rights.json \
  --output /tmp/ltc-release.json
```

`normalize`, `report`, and `validate` emit canonical JSON; `extract` emits
canonical JSON Lines. An empty, valid candidates file is not an error. Every
parsed JSON record rejects strings or object keys that cannot be encoded as
UTF-8, including lone surrogate code points in nested fields.

Gate 2 keeps `manifests/`, `artifacts/`, and `releases/` closed by default. The
repository policy permits only exact empty `.gitkeep` files or fixed root
`README.md` placeholders there. Opening Gate 3 requires reviewed,
schema-specific allowlists; an extension such as JSON or JSONL never authorizes
tracking data.

The implemented record and tool versions are:

| Artifact | Schema version | Tool or policy version |
| --- | --- | --- |
| normalized source | `normalized-source-v1` | `normalizationVersion=normalize-v1` |
| time candidate | `time-candidate-v1` | `extractionVersion=extract-v1`; carries `normalizationVersion` |
| human review input | `time-review-v1` | human-supplied review metadata |
| rights input | `rights-decision-v1` | `policyVersion=rights-policy-v1`; `targetUseProfile=zi5-public-corpus-v1` |
| release projection | `time-release-v1` | `releaseVersion=release-v1`; carries normalization, extraction, and rights-policy versions |
| candidate report | `candidate-report-v1` | `reportVersion=report-v1`; carries `candidateSchemaVersion` |
| scan run manifest | `scan-run-v1` | `toolVersions.scanVersion=scan-v1`; binds every other scan artifact |

These identifiers describe the executable contract. Published versioned JSON
Schema files remain future work and are required before real-source acquisition.

## Documentation

- [Project brief](docs/project-brief.md)
- [Project Gutenberg source-policy research](docs/research/gutenberg-source-policy.md)
- [Project Gutenberg private-mirror research](docs/research/gutenberg-private-mirror.md)
- [China mainland copyright research](docs/research/china-public-domain-policy.md)
- [Bounded pilot design](docs/pilot-design.md)
- [Pilot data model](docs/data-model.md)
- [Rights and publication policy](docs/rights-policy.md)
- [Evaluation protocol](docs/evaluation-protocol.md)
- [UBTmini source-cache plan](docs/operations/ubtmini-source-cache-plan.md)

## Licensing and rights

Project-authored software and documentation are licensed under the
[MIT License](LICENSE).

The MIT License does **not** grant rights in third-party literary works,
editions, source ebooks, excerpts, or provider names and trademarks. No future
corpus release should be assumed to be covered by MIT merely because it is
stored in this repository. Dataset terms will be documented separately before
the first data release, with per-record provenance and rights evidence. See
[DATA_RIGHTS.md](DATA_RIGHTS.md).

## Contributing

The synthetic extraction pipeline is implemented, but the real-source
contribution and publication workflows have not been approved. Please open an
issue before submitting source texts or literary excerpts. Never commit source
ebooks: local source and analysis files belong under ignored `.local/` paths.
Until Gate 4 opens a release process, `releases/` may contain only a root
`README.md` matching the approved no-release template or a zero-byte `.gitkeep`,
never corpus data in any format.

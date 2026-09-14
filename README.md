# Literary Time Corpus

A traceable corpus of literary excerpts containing exact clock times, with
per-record provenance and rights evidence.

## Status

This project is in its feasibility-pilot stage. The Gate 2 command-line
pipeline is implemented and locally verified against synthetic fixtures only.
It does not yet acquire Project Gutenberg ebooks or publish a quote corpus. The
next empirical milestone is to measure how much of a 1,440-minute day can be
covered by eligible English-language source texts, how reliably exact time
expressions can be extracted, and how much human review is required.

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

The initial pilot will use a bounded allowlist of English-language works from
Project Gutenberg. It will use documented catalog and bulk-access facilities,
retain source identifiers and hashes, and keep acquisition, analysis, review,
and release artifacts separate. Discovery uses a local RDF metadata copy;
acquisition caches only the exact approved UTF-8 text paths rather than mirroring
every ebook format or every file ending in `.txt`.

The project will not ingest Project Gutenberg at scale, publish unreviewed
excerpts, fill missing minutes with approximate text, or implement the
Literature Clock user interface during the pilot.

Passing the current test suite is evidence about the synthetic pipeline; it
authorizes neither ebook acquisition nor publication. Those actions remain
subject to the gates in the pilot design and rights policy.

See the [project brief](docs/project-brief.md) for the confirmed scope, data
semantics, evaluation requirements, and publication gates.

## Local synthetic pipeline

Python 3.11 or newer and [uv](https://docs.astral.sh/uv/) are required. Install
the project and its development environment from the lockfile:

```bash
uv sync
```

The installed `ltc` command exposes four offline operations. These examples use
only the repository's synthetic fixtures:

```bash
uv run ltc normalize \
  --input tests/fixtures/normalize/valid.txt \
  --output /tmp/ltc-normalized.json

uv run ltc extract \
  --input /tmp/ltc-normalized.json \
  --output /tmp/ltc-candidates.jsonl

uv run ltc validate \
  --analysis tests/fixtures/validate/analysis.json \
  --candidate tests/fixtures/validate/candidate.json \
  --review tests/fixtures/validate/review.json \
  --rights tests/fixtures/validate/rights.json \
  --output /tmp/ltc-release.json

uv run ltc report \
  --input tests/fixtures/report/candidates.jsonl \
  --output /tmp/ltc-report.json
```

`normalize`, `validate`, and `report` emit canonical JSON; `extract` emits
canonical JSON Lines. Identical inputs produce byte-identical outputs. Expected
input or invariant failures exit `2`; unexpected internal failures exit `1`.
Both write exactly one JSON error object to stderr with `error.code`,
`error.message`, and optional `error.details`. A failed command does not create
or modify its requested output path. Output destinations whose parent is
missing, is not a directory, or otherwise cannot be opened safely return exit
`2` with `error.code=invalid-output-path`.
Inputs whose paths cannot be resolved safely, including symlink loops, return
exit `2` with `error.code=invalid-input-path` before any output is changed.
An empty candidates JSONL from a valid no-match extraction is not an error:
`report` emits the deterministic `time-candidate-v1` zero-metrics report.
Every parsed JSON record recursively rejects strings or object keys that cannot
be encoded as UTF-8, including lone surrogate code points in nested fields.

Gate 2 keeps `manifests/`, `artifacts/`, and `releases/` closed by default. The
repository policy permits only exact empty `.gitkeep` files or fixed root
`README.md` placeholders in those directories. Opening Gate 3 must first add
reviewed, schema-specific allowlists; a generic JSON/JSONL extension is not
authorization to track data.

The implemented record and tool versions are:

| Artifact | Schema version | Tool or policy version |
| --- | --- | --- |
| normalized source | `normalized-source-v1` | `normalize-v1` |
| time candidate | `time-candidate-v1` | `extract-v1` plus the input normalization version |
| human review input | `time-review-v1` | supplied review evidence |
| rights input | `rights-decision-v1` | `rights-policy-v1`, profile `zi5-public-corpus-v1` |
| release projection | `time-release-v1` | `release-v1` |
| candidate report | `candidate-report-v1` | `report-v1` plus the candidate schema version |

These identifiers describe the current executable contract. Published JSON
Schema files are still future work and are required before real-source
acquisition is approved.

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

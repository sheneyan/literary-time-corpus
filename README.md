# Literary Time Corpus

A traceable corpus of literary excerpts containing exact clock times, with
per-record provenance and rights evidence.

## Status

This project is in its feasibility-pilot stage. It does not yet publish a quote
corpus. The first milestone is to measure how much of a 1,440-minute day can be
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

See the [project brief](docs/project-brief.md) for the confirmed scope, data
semantics, evaluation requirements, and publication gates.

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

The extraction pipeline and contribution workflow have not yet been approved.
Please open an issue before submitting source texts or literary excerpts.

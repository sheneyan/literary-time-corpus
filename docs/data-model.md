# Pilot data model

## Design goals

The model must preserve exact source text, reproduce every transformation,
separate automated conclusions from human decisions, and prevent ambiguous or
insufficiently cleared candidates from entering a release.

The Gate 2 implementation uses UTF-8 JSON for normalized sources, validation
inputs, release projections, and reports, and UTF-8 JSON Lines for candidates.
The CLI validates the current record shapes and version identifiers. Published
versioned JSON Schema files remain future work and are required before real
source acquisition. JSON property order is not semantically significant;
generated artifacts nevertheless use a stable serialization for deterministic
hashes and diffs.

## Implemented Gate 2 versions

The synthetic CLI currently emits or accepts these schema and version fields:

| Record | `schemaVersion` | Additional version fields |
| --- | --- | --- |
| normalized source | `normalized-source-v1` | `normalizationVersion=normalize-v1` |
| candidate | `time-candidate-v1` | `extractionVersion=extract-v1`; carries `normalizationVersion` |
| review input | `time-review-v1` | human-supplied review metadata |
| rights input | `rights-decision-v1` | `policyVersion=rights-policy-v1`; `targetUseProfile=zi5-public-corpus-v1` |
| release projection | `time-release-v1` | `releaseVersion=release-v1`; carries normalization, extraction, and rights-policy versions |
| report | `candidate-report-v1` | `reportVersion=report-v1`; carries `candidateSchemaVersion` |

This version table describes only the locally verified synthetic interface. It
is not an acquisition manifest or a dataset publication specification.

## Entity boundaries

### Work

A bibliographic work independent of a particular ebook or edition.

Required semantics:

- stable project-assigned `workId`;
- canonical title and author names;
- original language;
- original publication year when supported by evidence;
- author birth and death years with evidence when used in a China-mainland
  rights decision;
- author nationality or habitual residence and first-publication country/date
  when used to establish foreign-work or treaty status; and
- references supporting bibliographic or rights facts.

`workId` is an opaque identifier assigned once. It must not be regenerated from
a title or author spelling that may later be corrected.

### Source snapshot

One exact acquired file used for analysis.

Required semantics:

- `sourceId`;
- provider and provider item ID;
- ebook page URL and exact file URL;
- media type and declared or detected encoding;
- UTC acquisition timestamp;
- SHA-256 of untouched downloaded bytes;
- SHA-256 of the normalized analysis text;
- normalization version and transformation log;
- UTF-8 byte position at which the retained literary body begins in the
  untouched decoded source, when a direct mapping is possible; and
- references to the captured provider metadata and rights evidence.

`sourceId` has the deterministic form
`pg_<itemId>_<first-12-source-sha256-hex-digits>`.

The exact acquisition URL is internal provenance because hosted file paths may
change and Project Gutenberg asks public citations to use the ebook landing
page. A public release includes the canonical landing page and source hashes,
but not the acquisition URL unless a later policy review approves it.

The source record also identifies the dated RDF snapshot and exact RDF resource
from which its `text/plain; charset=utf-8` path was selected. Filename suffixes
are evidence neither of encoding nor of preferred-edition status.

### Candidate match

An immutable automated observation against one source snapshot.

Required semantics:

- `candidateId` and `sourceId`;
- extraction and normalization versions;
- rule family and rule ID;
- matched text and sufficient original context;
- excerpt and match start/end offsets measured in UTF-8 bytes in the analysis
  text;
- zero, one, or multiple normalized `HH:MM` values;
- precision class;
- contextual resolution method and exact evidence span, if any; and
- automated exclusion or warning reason codes.

The Gate 2 candidate also emits
`sourceHashStatus="carried-from-normalization"`. This means extraction checked
the normalized document's analysis-text hash and the consistency of its
synthetic `sourceId` with the carried `sourceSha256`; it did **not** have the
untouched source bytes available to recompute that source hash. Release
validation likewise verifies candidates against the supplied normalized
analysis snapshot, not against a downloaded ebook. Real-source acquisition
must retain and independently verify the untouched source snapshot before this
status can support a release decision.

`candidateId` is the lowercase hexadecimal SHA-256 of the UTF-8 encoding of:

```text
sourceId NUL analysisTextSha256 NUL matchStartByte NUL matchEndByte
```

The rule ID is deliberately excluded so two extractor versions finding the
same source span have the same identity.

### Review event

An append-only human decision about a candidate.

Required semantics:

- unique `reviewId`;
- `candidateId`;
- stable reviewer alias;
- review timestamp in UTC;
- decision and reason codes;
- confirmed precision class and normalized time values;
- confirmed excerpt boundary and attribution; and
- references to the rights decision reviewed.

Corrections append a superseding review event; they do not rewrite audit
history. Private reviewer notes may remain outside a public release.

### Release record

A deterministic projection of a candidate and its effective approved reviews.
It contains only fields approved for publication but retains source identity,
hashes, match text segmentation, exact normalized minute, attribution, rights
decision, and release version.

The implemented `ltc validate` interface requires the normalized analysis
snapshot explicitly through `--analysis`, as well as `--candidate`, `--review`,
`--rights`, and `--output`. Validation recomputes the analysis hash and checks
the candidate's UTF-8 byte spans against that snapshot before projecting a
release record.

## Controlled vocabularies

### Precision

- `exact-minute-resolved`
- `exact-minute-ambiguous`
- `approximate`

### Candidate status

- `detected`
- `automatically-excluded`
- `awaiting-review`
- `reviewed`

### Review decision

- `accepted`
- `rejected-not-clock-time`
- `rejected-approximate`
- `rejected-context-insufficient`
- `rejected-excerpt-boundary`
- `rejected-attribution`
- `rejected-rights`
- `needs-second-review`

Rights vocabularies are defined in [rights-policy.md](rights-policy.md).

### Jurisdiction assessment

Each rights object contains one assessment for `US` and one for `CN-mainland`.
Each assessment records:

- jurisdiction;
- `workStatus`: `not-restricted`, `restricted`, or `uncertain`;
- `editionStatus`: `eligible`, `contains-protected-material`, or `uncertain`;
- basis reason codes;
- evidence references; and
- reviewer and decision date.

The overall decision cannot be `eligible` unless both required jurisdiction
assessments are present and pass.

## Invariants

A release record must satisfy all of these conditions:

1. `precision` is `exact-minute-resolved`;
2. `normalizedTimes` contains exactly one valid zero-padded `HH:MM` value;
3. concatenating `quoteBefore`, `quoteTime`, and `quoteAfter` exactly reproduces
   the approved excerpt;
4. `quoteTime` exactly matches the source span without spelling modernization;
5. source and analysis SHA-256 values are present;
6. offsets select the recorded text from the fixed analysis snapshot;
7. the effective human review is `accepted`;
8. the United States and China-mainland work and edition assessments pass, and
   the aggregate rights decision is `eligible` for the release's target-use
   profile; and
9. no unresolved warning or superseding rejection exists.

An ambiguous candidate may contain multiple normalized times, but it cannot be
projected into a release record.

## Artifact separation

The implementation plan should preserve these logical zones:

```text
config/             committed pilot configuration and schemas
manifests/          committed source selections and evidence references
.local/source/      ignored untouched downloads
.local/analysis/    ignored normalized analysis copies
artifacts/          reproducible candidates, reviews, and reports
releases/           separately approved public corpus packages
```

No source ebook belongs in `manifests/`, `artifacts/`, or `releases/`. Before
implementation begins, `.local/` must be ignored and an automated repository
check must reject source ebooks and unapproved excerpt data.

That repository check is now implemented for the current Gate 2 boundary. It
examines the tracked Git index without requiring a clean worktree and applies
these conventions:

- binary ebook, document, HTML, and archive extensions are rejected throughout
  the repository;
- likely raw-text extensions such as `.txt`, `.text`, `.utf8`, and `.utf-8` are
  rejected everywhere except small UTF-8 files under `tests/fixtures/` whose
  content explicitly identifies them as synthetic and contains no copied
  Project Gutenberg license boilerplate;
- `manifests/` accepts committed metadata only as JSON, JSON Lines, or RDF, plus
  root `README.md`/`.gitkeep` placeholders and strictly validated relative
  ebook-path lists named `*-paths.txt`; and
- while Gate 4 remains unopened, `releases/` accepts only root `README.md` and
  `.gitkeep` placeholders. Every other tracked file is rejected regardless of
  whether it uses JSON, CSV, TSV, NDJSON, a binary extension, or no extension.

The release rule is intentionally absolute because Gate 4 has approved no
public excerpt artifact. A future release approval process must replace it
before any corpus package is committed.

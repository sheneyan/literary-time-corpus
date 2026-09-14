# Pilot data model

## Design goals

The model must preserve exact source text, reproduce every transformation,
separate automated conclusions from human decisions, and prevent ambiguous or
insufficiently cleared candidates from entering a release.

The first implementation should use UTF-8 JSON Lines for manifests, candidates,
and review events, validated by versioned JSON Schemas. JSON property order is
not semantically significant; generated artifacts must nevertheless use a
stable serialization for deterministic hashes and diffs.

## Entity boundaries

### Work

A bibliographic work independent of a particular ebook or edition.

Required semantics:

- stable project-assigned `workId`;
- canonical title and author names;
- original language;
- original publication year when supported by evidence;
- author birth and death years when used in a rights decision; and
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
8. the applicable rights decision is `eligible` for the release's target-use
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

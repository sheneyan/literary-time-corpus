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

Before domain validation or serialization, one shared recursive guard checks
every string value and object key in normalized, candidate, review, and rights
records for UTF-8 encodability. This includes unknown extension fields at any
nesting depth; lone surrogate code points fail under the record's normal error
category rather than reaching an internal serialization error.

## Implemented Gate 2 versions

The CLI currently emits or accepts these schema and version fields:

| Record | `schemaVersion` | Additional version fields |
| --- | --- | --- |
| normalized source | `normalized-source-v1` | `normalizationVersion=normalize-v1` |
| candidate | `time-candidate-v1` | `extractionVersion=extract-v1`; carries `normalizationVersion` |
| review input | `time-review-v1` | human-supplied review metadata |
| rights input | `rights-decision-v1` | `policyVersion=rights-policy-v1`; `targetUseProfile=zi5-public-corpus-v1` |
| release projection | `time-release-v1` | `releaseVersion=release-v1`; carries normalization, extraction, and rights-policy versions |
| report | `candidate-report-v1` | `reportVersion=report-v1`; carries `candidateSchemaVersion` |
| scan run manifest | `scan-run-v1` | `toolVersions.scanVersion=scan-v1`; binds every other scan artifact |

This version table describes the locally verified executable interface. Public
`ltc scan` runs may analyze user-supplied eligible text, but the table is not an
acquisition manifest or a dataset publication specification.

A valid extraction may contain zero candidate rows. Reporting an empty JSONL
therefore emits deterministic zero counts, zero coverage and duplicate
fractions, empty maps/lists, the SHA-256 of empty bytes, and
`candidateSchemaVersion=time-candidate-v1`; malformed nonempty rows still fail
closed.

### Scan run manifest

`ltc scan` writes `run.json` as canonical UTF-8 JSON with exactly these
top-level properties:

```json
{
  "artifactDigests": {
    "candidates.jsonl": {"byteSize": 0, "sha256": "<lowercase SHA-256>"},
    "normalized.json": {"byteSize": 0, "sha256": "<lowercase SHA-256>"},
    "report.json": {"byteSize": 0, "sha256": "<lowercase SHA-256>"},
    "review.md": {"byteSize": 0, "sha256": "<lowercase SHA-256>"}
  },
  "bodySelection": {"mode": "full-file"},
  "candidateCount": 0,
  "input": {"basename": "book.txt", "byteSize": 0, "sha256": "<lowercase SHA-256>"},
  "metadata": {
    "author": "unknown",
    "metadataComplete": false,
    "schemaVersion": "scan-work-metadata-v1",
    "sourceUrl": null,
    "title": "book"
  },
  "resolvedMinuteCount": 0,
  "schemaVersion": "scan-run-v1",
  "status": "complete",
  "toolVersions": {
    "candidateSchemaVersion": "time-candidate-v1",
    "extractionVersion": "extract-v1",
    "normalizationVersion": "normalize-v1",
    "normalizedSchemaVersion": "normalized-source-v1",
    "reportSchemaVersion": "candidate-report-v1",
    "reportVersion": "report-v1",
    "scanVersion": "scan-v1",
    "workMetadataSchemaVersion": "scan-work-metadata-v1"
  }
}
```

The numeric `byteSize` and lowercase hexadecimal `sha256` in `input` describe
the untouched input bytes. `basename` is the final input filename only, never
an absolute path. `metadata` is the exact `scan-work-metadata-v1` object copied
to every scan-produced candidate. `candidateCount` is the number of validated
candidate rows; `resolvedMinuteCount` is the number of distinct normalized
minutes among validated `exact-minute-resolved` candidates. Both counts must
agree with `report.json`.

`bodySelection` has one of exactly two shapes. Full-file selection is
`{"mode":"full-file"}` and contains no marker properties. Literal-marker
selection is
`{"endMarker":"<literal>","mode":"literal-markers","startMarker":"<literal>"}`;
`startMarker` and `endMarker` preserve the two supplied values exactly.

`toolVersions` has exactly the eight properties shown above. It binds the scan,
normalization, extraction, and reporting tool versions to their output schema
versions and records the schema of the copied work metadata.
`artifactDigests` has exactly the four named entries shown above and hashes the
final bytes of each artifact. `run.json` cannot and does not digest itself.

Immediately before publishing the staging directory, scan re-reads all five
files as regular, non-symbolic-link files and captures each device, inode, and
byte size. Starting from the original source bytes, marker options, and work
metadata, it regenerates the normalized record and candidates and requires
their exact canonical bytes. It then regenerates the report, including its
candidate-input hash and counts, and regenerates the expected Markdown bytes.
The deterministic renderer rejects duplicate candidate IDs and emits each
candidate exactly once, while an incidental `Candidate ID:` phrase inside
source context remains ordinary source text. Scan also recomputes the four
artifact digests. The raw `run.json` bytes must exactly equal the canonical JSON
serialization of the expected manifest; semantically equal pretty JSON and
numeric substitutions such as `1.0` for an integer are invalid.

After renaming a new scan directory into place, scan repeats the complete
verification and requires the captured artifact identities to be unchanged.
If that post-publication check fails, scan reports an error instead of success
and quarantines the current output entry. Successful scans still rename staging
to output directly and leave no temporary directory. These checks close the
program-controlled publication window; they cannot cryptographically prevent a
same-user process from modifying an artifact after scan has successfully
exited.

Replacing an existing scan directory additionally requires a platform capable
of anchoring publication operations to an opened parent directory. The
capability check covers the anchored open, stat, private-directory creation,
and no-replace rename operations used by the transaction; optional chmod and
recursive-cleanup facilities are selected independently. When the publication
anchor is unavailable, `scan --force` fails before staging with
`unsupported-safe-replacement` and preserves the existing directory exactly.
This restriction does not apply when the requested output path is absent.

Failed generation and failed post-publication verification use safe retention,
not in-process deletion or restoration. Scan creates a unique same-parent
quarantine directory with mode `0700`, atomically renames the current staging or
output entry into it without following symbolic links, and then inspects the
moved entry's device and inode. Whether that identity matches the
invocation-owned directory or not, the entry remains quarantined for manual
inspection; scan never recursively deletes it, moves it back, or overwrites a
new entry at the official path. The original error includes only the
non-sensitive `retainedPathBasename` and `officialPathStatus`. A successful move
normally leaves the official output path `absent`; if another process creates a
new entry there, its status is `present` and it is untouched.
`retainedPathBasename` is only the randomly suffixed quarantine directory name,
not a path; the retained tree is its `entry` child in the original output
parent.

The initial staging-directory ownership snapshot and every subsequent
generation, artifact-write, report/review build, verification, and publication
step share one exception boundary. Any ordinary `Exception` after staging is
created therefore attempts the same retention protocol. Controlled scan errors
keep their existing code and stage; an escaped output-write error keeps its
domain code and uses stage `staging`; other unexpected generation exceptions
become `internal-generation-failed` at stage `staging` and exit `1`, while all
controlled scan errors retain exit `2`. Both categories preserve quarantine
basename/status details. `KeyboardInterrupt` and `SystemExit` are not caught by
this boundary.

If the quarantine cannot be created or the atomic move fails, scan returns the
distinct `scan-cleanup-failed` error at stage `cleanup`, never reports success,
and includes the non-sensitive `officialPathStatus` (`absent`, `present`, or
`unknown`). It does not attempt a check-then-delete or check-then-restore
fallback.

Successful forced replacement removes the invocation-owned backup only after
identity checks. Descriptor-relative traversal is used where available, with a
guarded pathname fallback on platforms that require it. These checks reduce
race exposure but cannot make the final unlink or rmdir syscall conditional on
the previously checked inode. The scanner therefore does not claim a security
guarantee against a malicious process running as the same UID during that final
cleanup syscall; `--force` is supported only where the anchored publication
primitives above are available.

The manifest contains no current working directory, absolute path, username,
hostname, staging name, timestamp, locale, timezone, or environment value.
Given identical input bytes, basename, scan options, metadata, and tool
versions, all five artifacts are byte-identical even when the source and output
reside in different directories.

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

### Local scanner source identity

The current normalized-source validator accepts only the deterministic,
provider-neutral local scanner form
`local_<first 12 lowercase hexadecimal characters of sourceSha256>`. The
lowercase 64-character `sourceSha256` hashes the untouched input bytes. This
identifier binds local analysis to those bytes; it is not provider provenance,
an acquisition record, or rights approval. The current validator does not
accept a `pg_` identity.

### Future Project Gutenberg source snapshot

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

For a future approved Project Gutenberg acquisition record, `sourceId` has the
planned deterministic form
`pg_<itemId>_<first-12-source-sha256-hex-digits>`.

The exact acquisition URL is internal provenance because hosted file paths may
change and Project Gutenberg asks public citations to use the ebook landing
page. A public release includes the canonical landing page and source hashes,
but not the acquisition URL unless a later policy review approves it.

The source record also identifies the dated RDF snapshot and exact RDF resource
from which its `text/plain; charset=utf-8` path was selected. Filename suffixes
are evidence neither of encoding nor of preferred-edition status.

For the Gate 2 normalizer, `transformationLog` contains exactly one deterministic
entry. Its `method` is `full-file-selection` for the default mode or
`literal-marker-body-selection` when both literal markers are supplied. Its
`inputStartByte` and `inputEndByte` select the retained body from the untouched
source bytes, while `outputStartByte=0` and `outputEndByte` select the same bytes
from `analysisText`. Apart from excluding a single adjacent LF or CRLF in marker
mode, no trimming or line-ending conversion is performed.

Both `ltc extract` and `ltc validate` use the same normalized-record validator.
It accepts only `schemaVersion=normalized-source-v1` with
`normalizationVersion=normalize-v1`; verifies the analysis hash and synthetic
source-ID/hash relationship; and requires nonempty, internally consistent body
bounds plus the exact one-entry transformation log described above. Missing,
extra, or inconsistent transformation fields fail closed.
The normalizer runs this validator against its own generated record before any
atomic write and rejects marker bodies that contain only Unicode whitespace.

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

Gate 2 represents contextual resolution as `contextualResolution`. Resolved
candidates contain exactly `method`, `evidenceStartByte`, `evidenceEndByte`,
and `evidenceText`. The byte offsets select the evidence exactly from the fixed
UTF-8 analysis text and lie within the matched expression. Supported methods
are `explicit-meridiem`, `explicit-24-hour-clock`, and `named-time`.
Ambiguous and approximate candidates set `contextualResolution` explicitly to
JSON `null`; absence, an empty object, or an invented method is invalid.

The method also fixes the evidence semantics. `explicit-meridiem` selects only
the complete AM/PM suffix token (including its original punctuation),
`explicit-24-hour-clock` selects the complete numeric match and accepts no
meridiem, and `named-time` selects exactly the original `noon` or `midnight`
token. Each method must agree with the normalized minute produced from that
matched text; a smaller but internally consistent evidence span is invalid.
Likewise, extraction validates every generated candidate with the shared
candidate validator before writing JSONL. A zero hour is canonical only as
`00:MM`; forms such as `0:07` are not emitted as 24-hour candidates.

The Gate 2 candidate also emits
`sourceHashStatus="carried-from-normalization"`. This means extraction checked
the normalized document's analysis-text hash and the consistency of its
local `sourceId` with the carried `sourceSha256`; it did **not** have the
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

Candidate `workMetadata` is optional only for candidates produced by the
lower-level `ltc extract` command. Every candidate produced by `ltc scan` must
contain `workMetadata`, it must be a valid `scan-work-metadata-v1` object, and
it must exactly equal the manifest's `metadata` object.

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
scans/              ignored user-supplied scanner outputs
artifacts/          reproducible candidates, reviews, and reports
releases/           separately approved public corpus packages
```

No data payload belongs in `manifests/`, `artifacts/`, or `releases/` while
Gate 3 is closed. Both `.local/` and `scans/` are ignored; the automated
repository check rejects source ebooks, scan output, and unapproved excerpt
data even if an ignored path is explicitly offered for tracking.

That repository check is now implemented for the current Gate 2 boundary. It
examines the tracked Git index without requiring a clean worktree and applies
these conventions:

- only the exact approved root project files, `docs/**/*.md`, `src/**/*.py`,
  `tests/**/*.py`, the hash-pinned fixture inventory, and exact reserved-root
  placeholders are accepted;
- every file under `tests/fixtures/`, including JSON and JSONL, is approved only
  by its exact repository path and SHA-256 rather than by extension or a
  self-attested `synthetic` label; a copied path or one-byte change fails;
- while Gate 3 remains unopened, `manifests/` and `artifacts/` accept only an
  exact zero-byte root `.gitkeep` or their fixed root `README.md` placeholder;
- while Gate 4 remains unopened, `releases/` has the same deny-by-default rule;
  and
- every other tracked file in those roots is rejected regardless of whether it
  uses JSON, JSONL, RDF, CSV, a binary extension, or no extension.

```markdown
# Manifests

No Gate 3 manifest schema is approved.
```

```markdown
# Artifacts

No Gate 3 artifact schema is approved.
```

```markdown
# Releases

No public corpus release is approved.
```

These rules are intentionally absolute because Gate 3 has approved no tracked
data schema and Gate 4 has approved no public excerpt artifact. Gate 3 must
introduce reviewed, exact schema/path allowlists before any manifest or
generated artifact is committed; suffix-only exceptions are forbidden. A
future release approval process must separately replace the release rule before
any corpus package is committed. Changing a synthetic fixture's path or any
byte of its contents also fails repository policy until a reviewer verifies
that it remains fully synthetic and deliberately updates the fixture SHA-256
allowlist.

Any new top-level file, directory, source extension, generated format, or test
fixture therefore requires an explicit reviewed allowlist update. The policy
does not guess safety from content, filename, or an unfamiliar extension.

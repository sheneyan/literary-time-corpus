# Rights and publication policy

## Purpose

This policy records how Literary Time Corpus separates evidence from project
decisions. It is an engineering and publication-control policy, not a claim of
legal advice or worldwide public-domain status.

The root MIT License covers project-authored software and documentation. It
does not automatically license source ebooks, literary excerpts, translations,
editions, provider material, or a future dataset. See [DATA_RIGHTS.md](../DATA_RIGHTS.md).

## Target-use profile

The initial profile is `zi5-public-corpus-v1`:

- a versioned corpus package publicly downloadable from GitHub;
- display of approved excerpts on `labs.zi5.io`;
- no advertising, paywall, or sponsored placement;
- English-language original text only;
- excerpts rather than complete ebooks;
- separate United States and China-mainland work and edition assessments;
- per-record source, attribution, evidence, and jurisdiction fields; and
- no representation that a United States copyright assessment establishes
  worldwide status.

The required jurisdictions for version 1 are `US` and `CN-mainland`. A record
must pass both; one assessment cannot be derived from the other. Adding a
destination, commercial use, translation, full-text redistribution, or another
jurisdiction creates a new profile version or requires a fresh decision.

## Separate assessment layers

Each candidate must keep these questions independent:

1. Is the underlying literary work eligible in each checked jurisdiction?
2. Is the selected edition free of protected translations, introductions,
   annotations, illustrations, or other additions?
3. Does the source ebook contain a restriction or copyright-holder permission
   notice that limits downstream use?
4. Are provider terms, license text, names, and trademarks handled correctly?
5. Does the intended corpus use match the approved target-use profile?

A positive answer at one layer cannot substitute for evidence at another.

## Controlled vocabularies

### Work status per jurisdiction

- `not-restricted`: the recorded evidence supports absence or expiry of the
  relevant economic-right restriction for the named jurisdiction and profile.
- `restricted`: evidence identifies an applicable copyright restriction.
- `uncertain`: available evidence is incomplete or conflicting.

### Edition status

- `eligible`: the selected text is an eligible original-language edition for
  the checked use.
- `contains-protected-material`: the selected source includes material that
  cannot be included under the target-use profile.
- `uncertain`: edition boundaries or added material cannot be resolved.

### Project decision

- `eligible`: all required evidence and checks for the named profile are
  complete.
- `analysis-only`: local pilot analysis is permitted by project policy, but the
  excerpt is not approved for release.
- `review-required`: a specific unresolved question needs qualified review.
- `blocked`: known evidence conflicts with the target-use profile.

Missing evidence is never interpreted as `eligible`.

## United States gate

Project Gutenberg catalog or RDF status is an initial signal, not the final
decision. The selected ebook's internal notice must also show that the item is
not restricted under United States copyright law, and the edition must be
reviewed for protected translations or additions. A file posted under a
copyright holder's permission is blocked unless its downstream license is
separately approved.

## China-mainland gate

For a known natural-person author, the general economic-right term is screened
as life plus 50 years, ending on December 31 of the fiftieth year after death.
For a 2026 publication, death in 1975 or earlier may pass this term screen;
death in 1976 remains within the term through December 31, 2026.

This screen is not the final assessment. Review must also cover joint authors,
foreign-work and treaty connections, origin country and first publication,
anonymous or organizational authorship, translations, annotations, modern
editorial matter, and treaty-transition questions. Authorship, alteration, and
integrity rights remain protected without a time limit, so releases preserve
the author and title, reproduce the approved original text faithfully, and do
not present project normalization as the author's wording.

See the official-source [China-mainland research](research/china-public-domain-policy.md).

## Evidence requirements

Each decision must cite immutable or captured evidence sufficient to audit:

- the provider item and exact acquired file;
- the source ebook's internal copyright and license notice;
- provider catalog metadata captured on the acquisition date;
- author and original-publication facts used in the decision;
- edition or translation information;
- jurisdictions checked;
- reviewer, review date, decision, and reason codes; and
- the version of this policy and the target-use profile.

Evidence records should store a URL, access timestamp, SHA-256 where content is
captured, evidence type, and a short factual note. A URL alone is insufficient
when its content may change.

## Project Gutenberg handling

The pilot must follow the approved acquisition method documented in
[the source-policy research](research/gutenberg-source-policy.md) and
[private-mirror research](research/gutenberg-private-mirror.md). Catalog
metadata is not enough: the selected ebook's internal notice and both required
jurisdiction assessments must also be checked.

Project Gutenberg boilerplate must be removed from the analysis body without
altering literary text, while the untouched local source snapshot remains
available for audit. The public corpus may identify and link to Project
Gutenberg as a provenance source, but it must not copy provider boilerplate into
an excerpt or use the provider name as part of the project or release title.

## Release gate

A candidate is blocked from release when any of these conditions holds:

- work, edition, source, jurisdiction, or target-use evidence is missing;
- the source notice conflicts with catalog metadata;
- the work or relevant edition is restricted for a checked jurisdiction;
- the excerpt includes provider boilerplate or protected added material;
- the record lacks an accepted human review;
- the record is approximate or resolves to more than one minute;
- the exact source snapshot cannot be reproduced; or
- dataset-wide terms and the machine-readable rights report have not been
  approved for that release.

The pilot feasibility report is not a data release. A separate approval must
define the license or dedication, attribution file, rights report, and removal
process for the first public corpus package.

## Challenges and removals

A future public release must publish a contact route for rights questions.
Challenged records are quarantined from subsequent releases while reviewed.
Removal must preserve an internal tombstone containing the record ID, affected
release versions, decision date, and non-sensitive reason code so that a record
is not silently reintroduced.

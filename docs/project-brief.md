# Literary Time Corpus project brief

## Purpose

Build a traceable corpus of literary excerpts in which the original text states
a precise clock time. This is a standalone data project. Literature Clock may
consume a future approved release, but its UI, themes, deployment, and upstream-
code adaptation are outside this project's scope.

The first task is feasibility research: measure how much of a 1,440-minute day
can be covered from eligible English source texts. Do not assume full coverage
or begin product integration before that measurement exists.

## Confirmed decisions

- Preserve the defining mechanism: the displayed time must appear in the
  literary original, and the matched words must be highlighted by consumers.
- Publish only precise matches that normalize to one specific minute.
- Keep excerpts in their source language. Machine translation is not source
  text and is not part of the initial corpus.
- Treat software licensing, corpus or database licensing, and copyright in each
  literary work or edition as separate checks.
- Keep the corpus independent from the Literature Clock application. The
  application waits for corpus evidence before deciding its release scope.

### Precision classes

| Class | Example | Normalization | Corpus treatment |
| --- | --- | --- | --- |
| `exact-minute-resolved` | `1:17 a.m.`; `seventeen minutes past one in the morning`; `noon` | Exactly one `HH:MM` value | Eligible after rights and human-review gates pass. |
| `exact-minute-ambiguous` | `at one o'clock`, with no reliable morning/evening context | More than one candidate `HH:MM` value | Retain as a reserve candidate. Do not publish by default. |
| `approximate` | `about one`; `nearly midnight`; `shortly after five` | No exact normalized minute | Reject as a clock entry. It may remain in extraction diagnostics only. |

Expressions such as `a quarter to seven` and `half past twelve` are minute-
precise. They are publishable only when the text or reliable context resolves
the intended time of day where that distinction is required.

A publishable record must have `precision: exact-minute-resolved` and exactly
one value in `normalizedTimes`. A record with multiple possible times must never
enter the published corpus.

## Initial source strategy

Begin with English-language original works available from Project Gutenberg.
Use its catalog and documented robot or harvest facilities rather than scraping
interactive pages. Preserve the source ebook identifier, exact downloaded-file
URL, acquisition date, and source hash.

For the pilot, keep a dated local copy of the official RDF metadata and derive a
reviewed allowlist from it. Cache only the exact approved file whose RDF media
type is `text/plain; charset=utf-8` for each selected ebook. Do not mirror every
format or use a global `*.txt` suffix rule as the semantic selector: the main
collection also contains historical versions, alternate encodings, indexes,
instructions, and supplemental text.

Project Gutenberg determines copyright status primarily under United States
law and does not guarantee reuse rights elsewhere. The project must therefore
record rights evidence per work and edition. A public-domain original does not
make a later translation, introduction, annotation, or edition public domain.

The extraction output should contain only the reviewed excerpt and provenance
required by this project, not republish complete Gutenberg ebooks. Project
Gutenberg names and boilerplate should not be copied into the excerpt corpus
unless their applicable terms are deliberately followed.

Potential additional sources may be evaluated later, but each source needs an
explicit acquisition policy and rights model before ingestion.

## Target-use profiles and rights decisions

Rights approval must be tied to a versioned target-use profile rather than a
generic claim of worldwide clearance. The first proposed profile,
`zi5-public-corpus-v1`, covers a publicly downloadable corpus and display of
approved excerpts on `labs.zi5.io`, without advertising or a paywall.

The profile requires separate United States and China-mainland assessments for
the underlying work and selected edition. A record is eligible only when both
assessments pass. The profile does not claim worldwide public-domain status;
distribution decisions for other jurisdictions require their own review.

Rights vocabulary must keep evidence facts separate from project decisions:

- each jurisdiction assessment records `workStatus` as `not-restricted`,
  `restricted`, or `uncertain`;
- `editionStatus`: `eligible`, `contains-protected-material`, or `uncertain`;
- `decision`: `eligible`, `analysis-only`, `review-required`, or `blocked`.

## Candidate extraction pipeline

1. **Select sources.** Build an allowlist of eligible works and record title,
   author, author dates, language, Gutenberg ID, source URLs, edition
   information when available, acquisition date, source hash, and rights
   evidence. Completion: every input has a provenance record and a reason it is
   eligible for the pilot.
2. **Normalize source text.** Remove Project Gutenberg headers and footers from
   the analysis copy while retaining an untouched local snapshot. Hash both
   versions and record the transformation version. Completion: boilerplate is
   excluded without modifying literary text.
3. **Extract candidates.** Detect numeric and written time expressions,
   including `HH:MM`, words, `past`/`to`, `quarter`, `half`, `noon`, `midnight`,
   and clock-strike constructions. Completion: candidates retain the exact
   matched span, source offsets, extraction rule, and enough original context
   for review.
4. **Resolve time.** Normalize candidates to zero, one, or more `HH:MM` values
   and assign a precision class. Do not guess AM or PM from weak context.
   Completion: every retained candidate has an explainable result and recorded
   evidence for contextual resolution.
5. **Filter false positives.** Exclude dates, years, prices, durations, chapter
   numbers, coordinates, scores, and other non-clock uses. Completion: a
   reviewed sample reports precision and major remaining false-positive types.
6. **Human review.** Confirm source text, highlight span, time interpretation,
   excerpt boundary, attribution, and rights evidence. Completion: only human-
   reviewed `exact-minute-resolved` records become publishable.
7. **Measure coverage.** Report exact coverage across all 1,440 minutes,
   alternatives per minute, hour-by-hour gaps, ambiguous reserves, duplicate
   works and authors, and review backlog. Completion: the report supports a
   product decision without filling gaps with approximate text.
8. **Generate a release artifact.** Only after the data design and quality
   thresholds are approved, emit a versioned deterministic corpus package and
   machine-readable attribution and rights report. Completion: identical
   reviewed input produces identical output and every row is traceable.

## Minimum candidate record semantics

The physical storage format may change, but it must preserve these semantics:

```json
{
  "id": "pg-12345-sourcehash-matchoffset",
  "normalizedTimes": ["01:17"],
  "precision": "exact-minute-resolved",
  "quoteBefore": "When he woke it was ",
  "quoteTime": "1:17",
  "quoteAfter": " by the clock ...",
  "title": "Book title",
  "author": "Author name",
  "language": "en",
  "source": {
    "provider": "project-gutenberg",
    "itemId": "12345",
    "ebookUrl": "https://www.gutenberg.org/ebooks/12345",
    "fileUrl": "exact-downloaded-file-url",
    "format": "text/plain; charset=utf-8",
    "accessedAt": "YYYY-MM-DD",
    "sourceSha256": "sha256-of-untouched-source",
    "analysisTextSha256": "sha256-of-analysis-copy",
    "metadataSnapshot": "provenance/pg-12345.json"
  },
  "match": {
    "startOffset": 123456,
    "endOffset": 123460,
    "extractorVersion": "0.1.0",
    "ruleId": "numeric-12h-with-period"
  },
  "resolution": {
    "method": "explicit-day-period",
    "evidenceText": "in the morning"
  },
  "rights": {
    "targetUseProfile": "zi5-public-corpus-v1",
    "decision": "eligible",
    "jurisdictionAssessments": [
      {
        "jurisdiction": "US",
        "workStatus": "not-restricted",
        "editionStatus": "eligible",
        "basis": ["gutenberg-us-status", "ebook-internal-notice"]
      },
      {
        "jurisdiction": "CN-mainland",
        "workStatus": "not-restricted",
        "editionStatus": "eligible",
        "basis": ["author-term-expired", "foreign-work-review"]
      }
    ],
    "evidence": [
      {
        "type": "gutenberg-metadata",
        "url": "evidence-url",
        "accessedAt": "YYYY-MM-DD",
        "note": "evidence summary"
      }
    ]
  },
  "review": {
    "status": "human-reviewed",
    "decision": "accepted",
    "reviewer": "reviewer-alias",
    "reviewedAt": "YYYY-MM-DD",
    "reasonCodes": [],
    "notes": ""
  }
}
```

Stable record IDs must be derived deterministically from the provider item ID,
fixed source hash, and match location, rather than mutable titles or excerpt
text. Review status, decisions, and reason codes must use documented controlled
vocabularies. Public artifacts may omit private review notes but must retain
source identity, hashes, normalization evidence, and the rights decision.

## Pilot before scale

Run a bounded pilot rather than downloading the full Gutenberg collection. The
pilot must answer:

- Which time-expression families can be extracted reliably?
- What are candidate precision and estimated recall after automated filtering?
- How many distinct minutes are covered by the selected sample?
- Which minutes and hours remain sparse?
- What are median and P90 human-review times per candidate and accepted entry?
- What evidence and review effort are required for the United States and
  China-mainland publication gates?
- Are the results strong enough to justify a larger corpus run?

### Evaluation design

Keep a development set for discovering expression families and tuning rules,
and a frozen held-out set for final evaluation. Results from the development
set must not be reported as final extraction quality.

Select works using a documented stratified method that considers genre,
publication period, text length, author diversity, and relevant textual
features. Prevent one author, work, or series from dominating the sample.

Measure candidate precision from reviewed extraction results. Estimate recall
against independently annotated, fixed text windows from the held-out set.
Report accepted and rejected counts, false-positive and false-negative classes,
review-time distribution, minute and hour coverage, concentration by author and
work, ambiguous reserves, and review backlog.

Choose numerical pilot sizes only after checking official bulk-access guidance
and available metadata. Do not set a coverage target before the first measured
sample.

## Non-goals

- Literature Clock UI, settings, themes, routing, hosting, or deployment.
- Copying the complete quote corpus from cdmoro, Johannes Enevoldsen, Jaap
  Meijers, or The Guardian.
- Treating a software license as permission for inherited excerpts.
- Filling gaps with approximate, generated, translated, or rewritten quotes.
- Publishing ambiguous candidates before a later product decision.
- Claiming worldwide public-domain status from a United States assessment.

## Pilot-design deliverables

Before ingestion begins, the pilot design must define:

- the allowlist construction and sample-size rationale;
- the acquisition and source-snapshot policy;
- the candidate schema and controlled vocabularies;
- the extraction and evaluation protocol;
- the human-review procedure and timing method; and
- the target-use profile and evidence requirements.

No source ingestion, excerpt publication, or Literature Clock integration begins
until that pilot design is reviewed and approved.

## References

- [Project Gutenberg license guidance](https://www.gutenberg.org/policy/license.html)
- [Project Gutenberg permission guidance](https://www.gutenberg.org/policy/permission.html)
- [Project Gutenberg robot-access guidance](https://dev.gutenberg.org/policy/robot_access.html)
- [Private-mirror research](research/gutenberg-private-mirror.md)
- [China-mainland copyright research](research/china-public-domain-policy.md)
- [cdmoro/literature-clock permission request](https://github.com/cdmoro/literature-clock/issues/53)
- [cdmoro/literature-clock licensing clarification](https://github.com/cdmoro/literature-clock/pull/57)
- [JohsEnevoldsen/literature-clock](https://github.com/JohsEnevoldsen/literature-clock)
- [The Guardian's reader-contributed literary clock source list](https://www.theguardian.com/books/table/2011/apr/21/literary-clock)

# Project Gutenberg pilot design

## Status and authority

This document defines the first bounded feasibility pilot for Literary Time
Corpus. It is subordinate to the [project brief](project-brief.md). Approval of
this design authorizes neither source acquisition nor publication: those remain
separate gates.

## Pilot questions

The pilot must determine:

1. which exact-time expression families can be extracted reliably;
2. candidate precision and estimated recall on unseen texts;
3. exact-minute coverage achieved by the bounded sample;
4. the distribution of gaps and duplicate concentration;
5. median and P90 human-review effort; and
6. whether the evidence supports a larger run.

It must not assume that all 1,440 minutes can be covered.

## Eligible source pool

A work may enter the selection pool only when all of the following are true:

- its original language is English;
- the selected Project Gutenberg ebook contains an original English text, not
  a later translation;
- the ebook's own notice does not say that it is posted with permission from a
  copyright holder or otherwise restricted under United States copyright law;
- the source is available in a documented plain-text UTF-8 format suitable for
  deterministic processing;
- title, author, language, ebook identifier, exact file URL, and acquisition
  evidence can be recorded; and
- introductions, annotations, illustrations, translations, and other edition-
  specific additions can be identified or excluded.

Anthologies containing multiple authors or uncertain edition boundaries are
excluded from the first pilot. Eligibility for analysis does not by itself make
a record eligible for public release.

The public `ltc scan` command may analyze a local UTF-8 plain-text file supplied
by a user who has determined that the processing is permitted. That public,
provider-neutral analysis path does not apply the eligibility screens above,
select a pilot work, create or approve the 72-work allowlist, acquire an ebook,
or authorize Gate 3. Those remain separate governed activities.

For the initial profile, source selection must pass both a United States screen
and a China-mainland screen. For a known natural-person author in a 2026 pilot,
death in 1975 or earlier is a China-mainland term-screening condition, not a
complete clearance rule. Cooperation, foreign-work treaty status, source
country, editions, additions, and perpetual authorship, alteration, and
integrity rights remain review fields.

## Acquisition model

Maintain a local copy of the official RDF metadata for discovery. For each
approved ebook ID, freeze exactly one current RDF path whose media type is
`text/plain; charset=utf-8`, then acquire only those 72 allowlisted paths through
an official mirror or documented robot facility.

Do not use a global `*.txt` rsync include as the pilot selector. The dated
official main-collection file list contained 157,544 `.txt` paths totaling about
63.081 GB, including historical copies, alternate encodings, and non-book text.
The allowlist's exact RDF-selected paths, not that suffix total, define pilot
storage and network volume. See the [private-mirror research](research/gutenberg-private-mirror.md).

The planned cache host is UBTmini, using a private directory that exposes no
public HTTP, FTP, or rsync service. Deployment is governed by the separate
[UBTmini source-cache plan](operations/ubtmini-source-cache-plan.md). No host
change is authorized by this document.

## Sample design

The pilot uses 72 source snapshots split before extraction:

| Set | Novels | Short-fiction collections | Drama | Poetry | Total |
| --- | ---: | ---: | ---: | ---: | ---: |
| Development | 12 | 4 | 4 | 4 | 24 |
| Held-out evaluation | 24 | 8 | 8 | 8 | 48 |

The 1:2 split provides enough development texts to exercise rule families while
reserving twice as many unseen texts for evaluation. Half of each set is prose
novels, where clock references are expected to be most common; the remaining
half tests whether the approach transfers across other literary forms. This is
a feasibility sample, not a statistically representative estimate of all
English literature.

Within each form, selection must balance publication periods and text-length
bands as far as the eligible pool permits. Prefer one work per author and never
allow more than two works by one author in the complete pilot.

Selection proceeds in this order:

1. take a dated metadata snapshot using an approved official catalog method;
2. apply the objective eligibility filters;
3. complete source and edition rights review;
4. assign eligible records to form, period, and length strata;
5. order each stratum deterministically using the seed
   `literary-time-corpus-pilot-v1`; and
6. fill the development and held-out quotas without author leakage between the
   two sets.

The allowlist manifest, selection algorithm version, seed, exclusions, and
reason codes must be committed before held-out extraction. Source ebooks are
not committed.

## Workload limits

The pilot is bounded by all of these limits:

- 72 acquired source snapshots;
- 100 MiB of untouched source text in total;
- 2,000 manually reviewed extraction candidates; and
- 500,000 manually annotated words for recall estimation.

When acquisition is later approved, use no concurrent downloads, wait at least
two seconds between requests, and acquire no more than the 72 approved files in
one UTC day. These are conservative project safeguards, not a representation
that Project Gutenberg guarantees this schedule for every endpoint.

If extraction produces more than 2,000 candidates, review a rule-stratified
sample for precision and cost, report the remaining backlog, and treat measured
minute coverage as a lower bound rather than complete pilot coverage. Do not
silently discard excess candidates.

## Stages and gates

### Gate 1: design approval

Required artifacts:

- official-source research;
- this pilot design;
- the data model;
- the rights policy; and
- the evaluation protocol.

Passing Gate 1 permits implementation planning, not ebook acquisition.

### Gate 2: pipeline approval

The command-line implementation now demonstrates locally, using synthetic
fixtures only:

- deterministic source hashing and IDs;
- exact preservation of matched text;
- correct UTF-8 byte offsets;
- precision-class invariants;
- false-positive filters; and
- reproducible reports.

Its primary installed public interface is the offline, provider-neutral
`ltc scan` workflow for user-supplied eligible UTF-8 TXT files. `ltc normalize`,
`ltc extract`, `ltc report`, and `ltc validate` remain composable lower-level
commands. None searches for or downloads Project Gutenberg works. Expected
input and invariant failures exit `2`, unexpected internal failures exit `1`,
and both use one structured JSON error on stderr without reporting success. The
current schemas and versions are recorded in the [data model](data-model.md).

The report's duplicate fraction is defined as:

```text
duplicateCandidateCount = resolvedCandidateCount - resolvedMinuteCount
duplicateFraction = duplicateCandidateCount / resolvedCandidateCount
```

When `resolvedCandidateCount` is zero, `duplicateFraction` is `0.0`. These
counts include every candidate classified `exact-minute-resolved` in the report
input, regardless of review status; the report does not claim that those
candidates are publishable.

Passing Gate 2 is a technical prerequisite for acquisition. Actual acquisition
also requires completed United States and China-mainland source screens, the
approved UBTmini cache deployment, and the frozen 72-work allowlist.

Current status: the Gate 2 implementation is complete and locally verified on
synthetic data. This status is technical evidence only. It does not approve or
authorize Project Gutenberg access, real ebook processing, UBTmini changes, or
publication of any excerpt. Gates 3 and 4 remain unchanged and have not begun.

### Gate 3: pilot execution

Run the development set first. Freeze extraction and normalization versions
before processing the held-out set. Any rule change after inspecting held-out
results invalidates those results and requires a fresh held-out run.

Passing Gate 3 produces a feasibility report, not a public corpus.

### Gate 4: scale or release decision

The feasibility report must state measured quality, coverage, concentration,
review cost, rights backlog, and limitations. A separate approval decides
whether to stop, revise the pilot, scale acquisition, or design a public data
release.

## Stop conditions

Stop acquisition or processing and record the reason when:

- official access guidance cannot be followed;
- a selected ebook's internal notice conflicts with catalog metadata;
- the selected file or edition cannot be fixed and hashed;
- raw source storage exceeds the pilot cap;
- provenance cannot be reconstructed for any input;
- held-out membership or contents leak into rule development; or
- a rights question would require an unsupported assumption.

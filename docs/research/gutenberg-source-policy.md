# Project Gutenberg source policy for the bounded pilot

**Status:** research note for pilot design

**Checked:** 2026-09-14

**Scope:** official Project Gutenberg sources only; no ebook content was acquired
during this research.

This note turns Project Gutenberg's current published guidance into a
conservative acquisition and rights policy for the Literary Time Corpus pilot.
It is not a legal opinion and does not approve publication of any excerpt.

## Recommended pilot policy

1. Build a preliminary English-text pool from a dated snapshot of the official
   machine-readable catalog. Do not crawl search results or ebook landing
   pages.
2. Select a bounded, documented allowlist from that snapshot. Catalog status is
   only a screening signal, not a final rights decision.
3. Acquire only the approved works through Project Gutenberg's documented
   robot/harvest or mirror facilities, with a project-identifying user agent
   and at least the two-second delay shown in its robot example.
4. Prefer a manually curated UTF-8 plain-text file from the main collection as
   the pilot source of record. Exclude a work from this first pilot if that
   source is unavailable rather than adding another parsing path.
5. Preserve the untouched acquired file locally, its exact acquisition URL,
   acquisition time, reported modification time when available, and SHA-256.
   Treat a changed hash as a new source version even when the ebook number is
   unchanged.
6. Before extraction, inspect and preserve the copyright/license statement
   inside each ebook. Reject or quarantine any item marked copyrighted or
   posted with a copyright holder's permission unless a separate downstream
   license has been reviewed for this use.
7. Derive an analysis copy by removing the Project Gutenberg header, footer,
   license, and other Project Gutenberg references. Fail closed when boundaries
   are missing or ambiguous. Never extract time candidates from boilerplate.
8. Publish a canonical `https://www.gutenberg.org/ebooks/<id>` citation in
   provenance, not a deep link to a hosted ebook file. Keep the exact
   acquisition URL in internal provenance unless later policy review approves
   exposing it.
9. Record only the jurisdictions actually checked. A Project Gutenberg U.S.
   status must never be represented as worldwide public-domain clearance.

The two-second pacing, UTF-8-only first-pilot rule, fail-closed boundary rule,
and keeping acquisition URLs internal are project safeguards inferred from the
official guidance; Project Gutenberg does not prescribe this exact combined
workflow.

## Evidence and implications

### Automated access and bulk acquisition

Project Gutenberg states that its main website is intended for human users and
that perceived automated access can be blocked. It directs users downloading
"many books"—defined in a footnote as more than about 100 per day—to mirrors
and its roboting guidance instead. It also prohibits large-scale deep-linking
that leaves ebook-serving costs on its infrastructure. See the official
[Terms of Use](https://www.gutenberg.org/policy/terms_of_use.html).

The documented harvest interface supports filters for `txt`, `html`, EPUB,
Kindle, and other formats, plus ISO language codes. Its example uses `wget` with
a two-second delay. A full local copy should instead be built as a private
mirror; Project Gutenberg recommends `rsync` for mirror creation and refreshes.
See [Robot Access to Pages](https://www.gutenberg.org/policy/robot_access.html)
and the [Mirroring How-To](https://www.gutenberg.org/help/mirroring.html).

**Pilot implication:** discovery and download are separate operations. Catalog
metadata creates the allowlist; an approved acquisition endpoint supplies only
that bounded set. The pilot must not automate ordinary `/ebooks/<id>` pages.
The full weekly plain-text archive and a full mirror are unnecessary for this
phase.

### Catalog and metadata

Project Gutenberg provides daily XML/RDF metadata, the same metadata as
per-ebook RDF, and a weekly CSV. It explicitly recommends these machine-readable
files for databases and tools instead of crawling the website. GUTINDEX is not
recommended as automation input. XML OPDS is expected to sunset in 2027, while
OPDS2 is currently test-only and requires contact, so neither should be the
pilot's catalog dependency. See [Offline Catalogs and
Feeds](https://www.gutenberg.org/ebooks/offline_catalogs.html) and the official
[feed directory](https://www.gutenberg.org/cache/epub/feeds/).

The robot policy says catalog data are granted to the public domain. The weekly
CSV is useful for compact stratification, but its published columns do not
contain per-file URLs or a copyright-status field. The richer RDF carries file
formats, modification times, and a U.S. rights statement, so the pilot should
archive the RDF snapshot used for final per-item screening. See [Robot Access
to Pages](https://www.gutenberg.org/policy/robot_access.html).

Catalog metadata is not edition-complete evidence. Project Gutenberg says its
metadata does not generally include original print publication dates, its
ebooks may combine multiple print editions, and its transformations may include
dehyphenation, spelling changes, typography changes, and moved material.
Original-publication metadata is only available for some newer records. See
[Offline Catalogs and Feeds](https://www.gutenberg.org/ebooks/offline_catalogs.html)
and [Download Options and Bibliographic
Record](https://www.gutenberg.org/help/bibliographic_record.html).

**Pilot implication:** retain the catalog snapshot and per-item RDF, but do not
infer an exact print edition, original publication year, or original-language
status solely from catalog fields. Translation, contributor, and source-edition
questions remain human-review gates.

### Source-file selection and versioning

Project Gutenberg describes plain text and HTML as master formats for almost
all ebooks since 2004; EPUB and Kindle formats are generated. UTF-8 is now its
plain-text master encoding, and nearly every ebook offers plain-text UTF-8.
The main mirror collection contains manually curated plain text and HTML,
whereas the generated collection contains automatically generated formats.
See [File Formats](https://www.gutenberg.org/help/file_formats.html), [Download
Options](https://www.gutenberg.org/help/bibliographic_record.html), and the
[Mirroring How-To](https://www.gutenberg.org/help/mirroring.html).

Project Gutenberg also warns that ebook files change as corrections are made
and generated files are rebuilt. Direct file paths can be renamed or
reorganized, while the ebook landing page is intended to remain permanent.
See [Robot Access to Pages](https://www.gutenberg.org/policy/robot_access.html)
and [Terms of Use](https://www.gutenberg.org/policy/terms_of_use.html).

**Pilot implication:** use the exact acquired bytes and hash—not the ebook ID
alone—as the reproducibility anchor. Public citations point to the landing page;
internal provenance records the actual mirror/harvest URL and file metadata.

### Copyright status, permission, and editions

Project Gutenberg distinguishes works not restricted by U.S. copyright law
from copyrighted works distributed with a holder's permission. It warns that
the catalog can be wrong and says the license inside each ebook must be checked.
Permission granted to Project Gutenberg for a copyrighted ebook does not
automatically extend to downstream users. See the [Project Gutenberg
License](https://www.gutenberg.org/policy/license).

Project Gutenberg says thousands of items in its collection remain copyright-
restricted; absent an included downstream license, reuse permission must come
from the copyright holder. It also says it will not provide paperwork that
independently guarantees a public-domain conclusion. See [Permissions,
Licensing and Common Requests](https://www.gutenberg.org/policy/permission).

Each edition can have its own copyright status, and every translation has an
independent status. Project Gutenberg's research is performed for its own U.S.
distribution decisions, not as clearance for other organizations. See the
[Copyright How-To](https://www.gutenberg.org/help/copyright).

**Pilot implication:** an RDF/catalog statement such as "Public domain in the
USA" can shortlist an item, but only the acquired file's internal notice plus
edition/translation review can satisfy the pilot's U.S. evidence gate.
`workStatus`, `editionStatus`, and the project's publication `decision` must
remain separate fields.

### Trademark, boilerplate, and attribution

The Project Gutenberg license treats the underlying unrestricted book text and
the Project Gutenberg trademark/license as different layers. It states that,
for a work unrestricted under U.S. law, removing the Project Gutenberg license
and all Project Gutenberg references leaves text that may be used without the
trademark conditions in the United States. If the name remains associated with
a distributed Project Gutenberg work, the full trademark-license conditions
apply. See the [Project Gutenberg
License](https://www.gutenberg.org/policy/license).

Project Gutenberg separately permits factual citation of it as publication
source and says references in acknowledgements, reference sections, or
colophons are not trademark use. It asks citations to link to the ebook landing
page rather than a specific hosted file. See [Permissions, Licensing and Common
Requests](https://www.gutenberg.org/policy/permission).

**Pilot implication:** the excerpt itself must contain only the reviewed
literary passage. Put factual source attribution in structured provenance or a
reference section; do not use Project Gutenberg in the corpus title, branding,
or promotional language, and do not imply endorsement. Preserve the unmodified
source privately for audit. Project Gutenberg does not publish a universal
header/footer parsing algorithm, so ambiguous boundary detection requires
manual review.

### Jurisdiction limit and a public GitHub release

Project Gutenberg operates under U.S. copyright law and makes no representation
about an item's status outside the United States. It tells non-U.S. users to
check local law before accessing or reusing content and notes that the law of
the country of publication or distribution applies there. See the [Terms of
Use](https://www.gutenberg.org/policy/terms_of_use.html), [Copyright
How-To](https://www.gutenberg.org/help/copyright), and [permission
guidance](https://www.gutenberg.org/policy/permission).

**Pilot implication:** a public GitHub repository is globally accessible.
Project Gutenberg evidence can support a precise claim such as
`public-domain-us` or `unrestricted-under-us-law`; it cannot support
`public-domain-worldwide`. Whether a U.S.-only finding is an acceptable release
gate for a globally reachable excerpt corpus is a project/legal decision still
to be made.

## Required provenance from the pilot

For every acquired source, retain at least:

- Project Gutenberg ebook number and canonical landing page;
- dated catalog-snapshot identifier and the per-item RDF record;
- exact internal acquisition URL, media type, reported modification time, and
  acquisition timestamp;
- SHA-256 of the untouched source and of the derived analysis text;
- detected header/footer boundaries and transformation version;
- the complete internal copyright/license classification and reviewer decision;
- creator, contributor roles, language, title, credits/source notes, and any
  translation or edition evidence available; and
- the jurisdictions checked and the target-use profile version.

## Unresolved questions before ingestion approval

1. Is the first public release authorized on a documented U.S.-only rights
   conclusion, or must additional jurisdictions be cleared because GitHub and
   `labs.zi5.io` are globally accessible?
2. Which jurisdictions define `zi5-public-corpus-v1`, and who can approve their
   legal evidence rules?
3. Should an exact acquisition URL remain private provenance, as recommended
   here, or is an unlinked file URL acceptable in the public artifact despite
   Project Gutenberg's instruction to cite landing pages?
4. What evidence is sufficient to establish that an English text is the
   original work rather than a translation, and that its editorial matter is
   eligible?
5. How will multiple Gutenberg ebooks of the same work and ebooks assembled
   from multiple print editions be deduplicated without asserting unsupported
   edition identity?
6. Which START/END marker variants are supported, and what is the manual-review
   procedure when markers or internal copyright notices are missing or
   contradictory?
7. What numerical work cap and acquisition schedule will be used? A conservative
   first run should remain well below the main-site "many books" threshold even
   though it uses an approved harvest/mirror path.

Until these questions and the full pilot design are approved, this research
does not authorize ebook ingestion, excerpt publication, or product integration.

# Project Gutenberg private-mirror options

**Status:** official-source research note

**Checked:** 2026-09-14

**Scope:** Project Gutenberg's official pages and anonymous rsync endpoint
listings only. No ebook file or mirror content was downloaded.

## Executive conclusion

Project Gutenberg explicitly permits a private mirror and recommends one as
the best way to keep a local, current copy of all ebook files. A mirror does
**not** have to be public. Publication, official listing, and public rsync
service are optional additional roles with their own operational expectations.
See the official [Robot Access guidance][robot] and [Mirroring How-To][mirror].

For this project's bounded corpus pilot, a full mirror is technically supported
but disproportionate: the two official collections currently total about
**2.434 TB (2.213 TiB), 6.112 million files, and 451,952 directories**, before
local filesystem overhead. The lowest-risk default is therefore:

1. keep a dated local copy of official catalog metadata;
2. derive a reviewed allowlist from it; and
3. cache only the approved source files, refreshing them deliberately.

This recommendation is an engineering conclusion from the official capacity
and access guidance, not a Project Gutenberg requirement. It also does not
replace the per-ebook copyright and jurisdiction review in
[`gutenberg-source-policy.md`](./gutenberg-source-policy.md).

## Is a private mirror officially supported?

Yes. Project Gutenberg says that the best way to have a local, up-to-date copy
of all files is to set up a **private mirror**. Its mirror guide separately says
that a private mirror can be built even on a DSL or cable connection and may
retain only zip files, leave out audio, or make other selections with rsync
filters. These
statements both authorize private use and make clear that a mirror need not be
public. [Robot Access][robot]; [Mirroring How-To][mirror].

The public-mirror section is conditional: “If you wish to create a public
mirror.” A public operator may expose the collection over HTTP, FTP, rsync,
TOR, BitTorrent, peer-to-peer, or another method, but Project Gutenberg asks
that the upstream copy and refresh use rsync. Listing on Project Gutenberg's
mirror list is also optional; after setup and testing, the operator contacts
Project Gutenberg, which observes roughly a month of stability and recency
before listing it. [Mirroring How-To][mirror].

Consequently, a private mirror does not require a static public IP, a public
web server, public rsync access, or application to the official mirror list.
The guide's approximately 1.5 Mb/s symmetric permanent-connection minimum is
stated for a **public** mirror, not a private copy. [Mirroring How-To][mirror].

## Supported rsync modules and layout

Project Gutenberg documents two independent modules on two official endpoints:

| Collection | Contents | Official anonymous-rsync sources | Ebook 12345 example |
|---|---|---|---|
| Main | Manually curated HTML and plain text, zip archives, and audio | `rsync.ibiblio.org::gutenberg` or `gutenberg.pglaf.org::gutenberg` | `1/2/3/4/12345/` |
| Generated | EPUB, MOBI/Kindle, generated HTML, and other generated files | `rsync.ibiblio.org::gutenberg-epub` or `gutenberg.pglaf.org::gutenberg-epub` | `epub/12345/` |

These module names were also returned by anonymous module-listing requests to
both endpoints on 2026-09-14; no module contents were transferred. The commands,
collection definitions, and layouts are documented in the
[Mirroring How-To][mirror].

The two collections should not be treated as interchangeable:

- The main collection uses a digit hierarchy of small directories.
- The generated collection has one large root with a directory per ebook.
- Generated files live at `cache/epub` in the main tree, while catalog metadata
  refers to `cache/generated`. A public web front end that combines the trees
  may need the documented redirect between those paths.
- Project Gutenberg offers the **book directories** for mirroring. Its central
  search application and main website pages are not included. XML/RDF catalog
  metadata is available at the root of the generated content for operators who
  build their own search software.

Project Gutenberg highly recommends rsync for both initial creation and
refreshes. It says `wget` and `curl` are unsuitable for a mirror because they
must inspect all files to discover recent changes. The documented baseline
commands use archive/verbose mode and `--del`; that last option means a refresh
also deletes local paths removed upstream, so an implementation should keep
derived data and audit snapshots outside the rsynced destination.
[Mirroring How-To][mirror].

## Update and traffic expectations

The main collection changes daily as items are added or corrected, and Project
Gutenberg directs mirror operators to run a daily refresh check. Its example
also asks operators to choose their own time of day to spread load rather than
blindly copying the sample schedule. [Mirroring How-To][mirror].

The generated collection has a burstier profile. Project Gutenberg says those
formats are rebuilt monthly and may also change when generator software
improves; a batch regeneration can produce a mirror-refresh traffic spike.
[Robot Access][robot]; [Mirroring How-To][mirror]. Project Gutenberg does not
publish a guaranteed daily or monthly delta-byte figure, so capacity planning
should not invent a steady incremental-bandwidth estimate.

The ordinary `www.gutenberg.org` site is for human users. Automated access can
trigger temporary or permanent blocking, and Project Gutenberg defines “many
books” as more than approximately 100 per day. Such bulk access should use a
mirror or its documented robot facilities, not ordinary ebook pages. Automatic
traffic-volume blocks normally expire after a few days. [Terms of Use][terms].

Public products should link to the stable ebook landing page,
`https://www.gutenberg.org/ebooks/<id>`, rather than a specific hosted file or
anchor. Project Gutenberg does not allow large-scale deep-linking that leaves
file-serving costs on its donor-funded infrastructure. If a product needs a
stable link to a particular file or passage, Project Gutenberg tells the
operator to host its own copy. [Terms of Use][terms]; [Linking guidance][linking].

## Current official size and count

Project Gutenberg's live homepage reported **79,386 free ebooks** on
2026-09-14. This is the ebook count; it is not the number of mirror files.
[Project Gutenberg homepage][home].

The official mirror `metadata.json`, updated
`2026-09-14T02:47:29+00:00`, reported:

| Collection | Files | Directories | Bytes | Decimal TB | Binary TiB |
|---|---:|---:|---:|---:|---:|
| Main | 3,438,631 | 317,091 | 1,064,679,424,902 | 1.065 | 0.968 |
| Generated | 2,673,296 | 134,861 | 1,368,976,728,183 | 1.369 | 1.245 |
| **Both** | **6,111,927** | **451,952** | **2,433,656,153,085** | **2.434** | **2.213** |

Source: official live [mirror metadata][mirror-metadata]. Totals and TB/TiB
conversions are calculated from the published byte counts. Local storage must
allow additional room for filesystem allocation, indexes, logs, temporary
rsync files, and snapshots. Initial network transfer will be on the same order
as the selected payload, but cannot be equated exactly with these byte counts
because protocol overhead and transfer behavior are not quantified by Project
Gutenberg.

The official feeds directory currently lists the compressed complete RDF
catalog at approximately **121 MB**, the zipped version at approximately
**177 MB**, the compressed CSV catalog at approximately **5.3 MB**, and the
uncompressed CSV at approximately **20 MB**. The directory displays rounded
sizes, not exact byte counts. The RDF metadata is updated daily; the CSV is
updated weekly. [Feeds directory][feeds]; [Offline Catalogs][catalogs].

## Bounded TXT-only calculation

To quantify what a suffix-filtered main-collection copy would mean, the
official `main-filelist.csv.bz2` dated 2026-09-14 was transferred and processed
as metadata only. Its bzip2 integrity was checked before aggregation. The
calculation summed the file-list `size_bytes` field; it did not fetch or inspect
any ebook body. See the official [main-collection file list][main-filelist].

| File-list selection | Files | Listed bytes |
|---|---:|---:|
| Every path ending in `.txt` | 157,544 | 63,081,048,563 bytes (63.081 GB / 58.749 GiB) |
| Paths ending in `-0.txt` | 69,765 | about 28.598 GB |
| Paths ending in `-8.txt` | 36,902 | about 15.155 GB |
| Other `.txt` paths | 50,877 | about 19.327 GB |
| Text-like numeric zip names (`<id>.zip`, `<id>-0.zip`, or `<id>-8.zip`) | 66,234 | about 10.521 GB |

The three raw-text subgroups partition the 157,544 `.txt` paths. The decimal
GB values for the subgroups and zip group are rounded; the all-`.txt` byte sum
is exact for that dated listing. The zip figure is a filename-based upper-level
inventory, not a verified count of archive members: archive bodies were not
opened, and nonstandard text archive names may not be included.

These numbers are **not** a count or size of one current UTF-8 text per ebook:

- The main archive retains previous versions in directories named `old` or
  similar, and the file-list totals above include those paths. Project
  Gutenberg documents this version-retention practice in its
  [download-options guidance][record].
- Multiple raw encodings or variants can coexist for one ebook. The `-0.txt`
  group is a useful filename-shaped estimate, not authoritative proof that
  every selected file is the desired current UTF-8 edition. The `-8.txt` group
  is likewise a legacy-style filename group, not a charset guarantee.
- The `.txt` extension itself is deliberately generic. Project Gutenberg says
  it can contain ASCII, ISO-8859, Big-5, or Unicode, even though UTF-8 is now
  the preferred plain-text master format. [File Formats][formats].
- The suffix total also includes non-ebook text such as top-level indexes and
  project instructions, plus supplemental or unusually named text files inside
  ebook directories. “Other `.txt`” therefore cannot be treated as a clean
  set of canonical book texts.
- The text-like zip files generally duplicate a raw text representation in
  compressed form. Adding their 10.521 GB to the raw-text total would estimate
  traffic for keeping both representations, not additional unique books.

### Why a global rsync suffix filter is not the pilot selector

A global rsync rule can reliably reduce transfer by filename—for example, by
retaining directory traversal and including `*.txt` before excluding other
files. It cannot reliably express the semantic requirement “one current
UTF-8 plain-text file for each approved ebook.” A broad `*.txt` include admits
old versions, alternate encodings, indexes, instructions, and supplemental
text. Adding an `old` exclusion removes an important class of duplicates but
does not prove charset, ebook identity, category, or preferred status. Adding
`*.zip` captures unrelated archive formats unless the naming rule is narrowed,
and even a narrowed zip suffix does not prove its members without opening it.

For the bounded pilot, first select approved ebook IDs from a dated RDF catalog,
then take only the **exact file URI** whose RDF media type is
`text/plain; charset=utf-8`. Project Gutenberg states that the complete RDF is
updated daily, that the same metadata is available per ebook, and that the
records describe the available files. [Offline Catalogs][catalogs]. The
selection should also require the catalog category `Text`, apply the project's
rights gates, reject historical paths, and fail closed if zero or multiple
candidate files remain. Rsync should then transfer only that frozen exact-path
allowlist rather than rediscovering candidates from global suffix patterns.

This RDF-first method makes the suffix totals useful for capacity bounds while
keeping filename conventions out of the correctness boundary. The actual
pilot storage/network estimate is the sum of the RDF-selected paths for the
approved allowlist, not 63.081 GB.

## Three viable operating options

| Option | What is retained | Officially evidenced storage / first-transfer scale | Refresh model | Assessment for this pilot |
|---|---|---:|---|---|
| Full private mirror | Both `gutenberg` and `gutenberg-epub` modules | 2,433,656,153,085 bytes of source files; allow more than 2.434 TB for local overhead | Daily rsync checks; expect generated-format batch spikes | Supported, but far larger than required and duplicates many formats |
| Metadata-only | Complete RDF, or the smaller CSV when its fields suffice | About 121 MB compressed RDF, 177 MB zipped RDF, 5.3 MB compressed CSV, or 20 MB CSV | RDF daily; CSV weekly | Best discovery/index baseline; contains no literary text to extract |
| Bounded allowlist cache | Exact RDF-selected UTF-8 text paths for approved ebook IDs, plus the metadata snapshot | No fixed official total; exactly the sum of selected files plus local provenance/derived data | Deliberate per-item change checks or bounded approved refreshes | Recommended for the pilot; avoids the 63.081 GB suffix-filtered overcollection |

The allowlist cache cannot be given a defensible aggregate size until IDs,
formats, and image/audio exclusions are chosen. Ebook count is not a byte-size
proxy: individual entries may have several formats and widely different media.
Before acquisition, an implementation can use rsync listings or catalog file
metadata to record the selected paths and reported sizes without traversing the
ordinary website. This estimate should be frozen alongside the allowlist, then
checked against bytes actually received.

If a broader local archive later becomes necessary, two intermediate variants
remain supported by the official guide:

- mirror only the main collection (currently about 1.065 TB / 0.968 TiB), which
  aligns better with curated plain-text/HTML source work; or
- use rsync exclusions to omit audio, generated formats, or other unneeded file
  classes.

Project Gutenberg documents the filtering capability but does not publish a
current filtered-size total. Any claimed savings therefore need a fresh
dry-run or file-list calculation against the chosen rule set.

## Decision for the corpus pilot

Adopt **metadata-only discovery plus a bounded allowlist cache**. Do not create
a full private mirror yet. Reconsider a main-only or full mirror only when the
approved corpus scale makes repeated bounded acquisition more costly than
maintaining the relevant module, and only after provisioning capacity for
refresh spikes and safe `--del` behavior.

This decision addresses acquisition mechanics only. It does not establish that
an ebook, edition, translation, or excerpt is public domain in every target
jurisdiction, nor does it authorize publication.

[robot]: https://www.gutenberg.org/policy/robot_access.html
[mirror]: https://www.gutenberg.org/help/mirroring.html
[terms]: https://www.gutenberg.org/policy/terms_of_use.html
[linking]: https://www.gutenberg.org/policy/linking.html
[home]: https://www.gutenberg.org/
[mirror-metadata]: https://www.gutenberg.org/dirs/metadata.json
[main-filelist]: https://www.gutenberg.org/dirs/main-filelist.csv.bz2
[feeds]: https://www.gutenberg.org/cache/epub/feeds/
[catalogs]: https://www.gutenberg.org/ebooks/offline_catalogs.html
[formats]: https://www.gutenberg.org/help/file_formats.html
[record]: https://www.gutenberg.org/help/bibliographic_record.html

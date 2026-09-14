# UBTmini Project Gutenberg source-cache plan

## Status

This is an approved architecture plan, not a deployment record. No directory,
backup rule, service, timer, mirror, or ebook has been created on UBTmini for
this project.

## Chosen role

UBTmini will be a private acquisition cache for:

- dated Project Gutenberg RDF metadata;
- frozen 72-work allowlists and reported source sizes;
- exactly one approved `text/plain; charset=utf-8` source path per selected
  ebook; and
- acquisition logs and checksums.

It will not expose an HTTP, FTP, or rsync mirror to the public. The pilot will
not mirror every format or every `.txt` path.

## Verified host snapshot

Read-only checks on 2026-09-14 found:

| Mount | Source | Filesystem | Available bytes | Use | RAID state |
| --- | --- | --- | ---: | ---: | --- |
| `/srv/repositories` | `/dev/md0` | ext4 | 1,418,588,270,592 | 50% | RAID1 `[UU]` |
| `/srv/repositories-4t` | `/dev/md1` | ext4 | 2,318,502,522,880 | 38% | RAID1 `[UU]` |

UBTmini has rsync 3.2.7, wget 1.21.4, curl 8.5.0, four logical CPUs, and about
2.8 GiB of currently available memory. These values are a dated observation and
must be rechecked before deployment.

The active `ubtmini-repo-backup.service` copies all of
`/srv/repositories/` to `/srv/repositories-4t/` each day with rsync and currently
has no mirror exclusion. Putting a reproducible cache inside that source tree
without changing the rule would duplicate it onto the backup array and add
millions of unnecessary scans if the cache later grew to a suffix-filtered
mirror.

## Planned layout

```text
/srv/repositories/.mirrors/gutenberg/
  metadata/
  allowlists/
  source-cache/
  logs/
```

The directory remains on the healthy primary RAID1. Because source cache bytes
are reproducible and their hashes and allowlists are retained in Git, the cache
directory should be excluded from the repository backup. Metadata snapshots
needed as permanent evidence must either be committed when licensing permits or
copied to a separately defined evidence-backup location; exclusion must not
silently discard the only provenance copy.

## Deployment gates

1. Recheck host identity, `/dev/md0` mount identity, free bytes, free inodes,
   RAID `[UU]` state, and backup-service status.
2. Estimate the exact 72-file transfer from the dated RDF-selected allowlist and
   reject deployment if it violates the 100 MiB pilot cap.
3. Add a narrowly scoped `/.mirrors/` exclusion to the repository backup and
   verify with an rsync dry run that ordinary repository data remains covered.
4. Create the cache directories with a dedicated unprivileged service account
   or project group; do not run network parsing as root.
5. Fetch metadata from an approved official endpoint and verify its timestamp
   and checksum before selection.
6. Freeze the exact source allowlist, sizes, hashes, and rights-screen status
   before transferring any ebook files.
7. Transfer with no concurrency and conservative pacing, then verify received
   byte counts and SHA-256 values.
8. Run a second backup dry run and a normal backup after deployment to prove the
   cache is excluded and unrelated repository data is still protected.

Any failed mount, RAID, free-space, rights, checksum, or backup check stops the
deployment. No `--delete` operation may target a path that also contains
manifests, evidence, derived data, or unrelated files.

## Scale boundary

The 2026-09-14 official main file list contained 157,544 `.txt` paths totaling
63,081,048,563 bytes. This broad set fits current raw capacity but includes old
versions, alternate encodings, and non-book text, and would be duplicated by the
current backup job. It is not approved for deployment.

Reconsider a larger filtered private mirror only after the pilot demonstrates
that repeated allowlist acquisition costs more than maintaining it, and after a
dedicated storage and backup policy is approved.

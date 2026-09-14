# Gutenberg Pilot Design Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce the official-source research and approved design documents required before the Literary Time Corpus pilot may ingest source texts.

**Architecture:** Keep provider-specific evidence in one research report and split durable project policy into pilot scope, data semantics, rights, and evaluation documents. This batch is documentation-only: it does not acquire ebooks, implement an extractor, or publish excerpts.

**Tech Stack:** Markdown, official Project Gutenberg documentation, Git

---

### Task 1: Research Project Gutenberg source policy

**Files:**
- Create: `docs/research/gutenberg-source-policy.md`

- [ ] **Step 1: Review primary sources**

Use Project Gutenberg's official license, permission, robot-access, offline
catalog, RDF, and mirror documentation. Record the access method, metadata
limitations, file-selection policy, trademark and boilerplate implications, and
non-US jurisdiction warning.

- [ ] **Step 2: Write the cited report**

Every operational or rights claim must link directly to the official page that
supports it. Separate source facts from project recommendations and list any
remaining questions without converting uncertainty into permission.

### Task 2: Define the bounded pilot

**Files:**
- Create: `docs/pilot-design.md`

- [ ] **Step 1: Specify scope and sampling**

Define the development and frozen held-out sets, stratification dimensions,
author concentration limits, acquisition cap, review cap, and stop conditions.

- [ ] **Step 2: Specify stage gates**

Make source selection, local acquisition, extraction, evaluation, and any later
release separate approval stages. State explicitly that this design batch does
not approve source ingestion or excerpt publication.

### Task 3: Define traceable data semantics

**Files:**
- Create: `docs/data-model.md`

- [ ] **Step 1: Define records and identities**

Specify work, source snapshot, candidate, review, and release-record semantics,
including deterministic IDs, SHA-256 hashes, UTF-8 byte offsets, controlled
vocabularies, and invariants for publishable exact-minute records.

- [ ] **Step 2: Define artifact boundaries**

Separate local raw sources, reproducible metadata, candidate output, review
decisions, and public release data so that raw ebooks cannot be committed by
accident.

### Task 4: Define rights and evaluation policies

**Files:**
- Create: `docs/rights-policy.md`
- Create: `docs/evaluation-protocol.md`

- [ ] **Step 1: Define the target-use profile**

Describe `zi5-public-corpus-v1`, evidence types, jurisdiction recording,
provider-name handling, decision vocabulary, and the conditions that block a
record from release.

- [ ] **Step 2: Define reproducible evaluation**

Specify candidate precision, independently annotated recall windows, exact-
minute coverage, review-time measures, duplicate concentration, double-review
sampling, confidence intervals, and workload caps without declaring a coverage
success threshold before the pilot measurement.

### Task 5: Verify and publish the design batch

**Files:**
- Modify: `README.md`
- Add all files created by Tasks 1 through 4.

- [ ] **Step 1: Link the design documents from the README**

Add a documentation section that points to the research report and four policy
documents without suggesting that ingestion or publication has started.

- [ ] **Step 2: Run documentation checks**

Run:

```bash
git diff --check
if rg -n --glob '!docs/superpowers/plans/**' "TBD|TODO|exact-24h|verified-for-target-use" README.md DATA_RIGHTS.md docs; then exit 1; fi
ruby -e 'Dir["**/*.md"].each { |f| File.read(f).scan(/\[[^\]]+\]\((?!https?:\/\/)([^)#]+)(?:#[^)]+)?\)/).flatten.each { |p| q=File.expand_path(p,File.dirname(f)); abort("broken link: #{f} -> #{p}") unless File.exist?(q) } }'
```

Expected: all commands exit successfully and print no errors.

- [ ] **Step 3: Review scope**

Run:

```bash
git status --short
find . -type f -not -path './.git/*' | sort
```

Expected: only Markdown documentation and the existing repository metadata are
present; there are no ebooks, corpus records, scripts, or generated data.

- [ ] **Step 4: Commit and push**

Run:

```bash
git add README.md docs
git commit -m "docs: define Gutenberg pilot"
git push origin main
```

Expected: the new commit is present on `origin/main` and the local worktree is
clean.

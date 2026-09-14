# Mirror and Jurisdiction Policy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this documentation change. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Record the approved private-cache acquisition model and require both United States and China-mainland rights assessments.

**Architecture:** Keep official-source evidence in research notes, durable publication rules in project policy, and host-specific operational safeguards in a separate UBTmini plan. This change documents decisions only and performs no host mutation or ebook acquisition.

**Tech Stack:** Markdown, Git

---

### Task 1: Publish the evidence

**Files:**
- Create: `docs/research/gutenberg-private-mirror.md`
- Create: `docs/research/china-public-domain-policy.md`

- [ ] Verify that every legal and provider claim links to a primary official
  source and that no ebook content is included.

### Task 2: Update project policy

**Files:**
- Modify: `README.md`
- Modify: `DATA_RIGHTS.md`
- Modify: `docs/project-brief.md`
- Modify: `docs/pilot-design.md`
- Modify: `docs/data-model.md`
- Modify: `docs/rights-policy.md`
- Modify: `docs/evaluation-protocol.md`

- [ ] Replace the unresolved jurisdiction gate with separate required `US` and
  `CN-mainland` assessments and make eligibility require both.
- [ ] Replace suffix-wide TXT mirroring with RDF-selected exact UTF-8 paths for
  the frozen allowlist.

### Task 3: Record the host plan

**Files:**
- Create: `docs/operations/ubtmini-source-cache-plan.md`

- [ ] Record the dated read-only host evidence, intended private-cache layout,
  existing backup conflict, deployment gates, and explicit non-deployment
  status.

### Task 4: Verify and publish

- [ ] Run `git diff --check`, relative-link checks, JSON example parsing, and a
  scope scan proving that no ebook or executable file is added.
- [ ] Commit with `docs: define mirror and jurisdiction policy` and push to
  `origin/main`.

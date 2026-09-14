# Initial Repository Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish a documentation-only initial version of Literary Time Corpus to the empty public GitHub repository.

**Architecture:** Keep the root focused on discovery and licensing, with the canonical scope in `docs/project-brief.md`. Separate MIT-licensed project work from third-party literary rights through an explicit data-rights policy, and publish no corpus records or source texts in this change.

**Tech Stack:** Markdown, Git, GitHub

---

### Task 1: Create the public project surface

**Files:**
- Create: `README.md`
- Create: `LICENSE`
- Create: `DATA_RIGHTS.md`
- Create: `.gitignore`

- [ ] **Step 1: Add the README and licensing files**

Create the four files with the approved project description, MIT license text,
data-rights separation, and macOS metadata exclusion.

- [ ] **Step 2: Verify the license boundary**

Run:

```bash
rg -n "MIT|does not|third-party|literary" README.md DATA_RIGHTS.md LICENSE
```

Expected: the MIT grant is present and both public-facing documents state that
it does not automatically license third-party literary text.

### Task 2: Publish the approved project brief

**Files:**
- Create: `docs/project-brief.md`
- Create: `docs/superpowers/specs/2026-09-14-initial-repository-design.md`
- Create: `docs/superpowers/plans/2026-09-14-initial-repository.md`

- [ ] **Step 1: Add the canonical brief**

Document the approved three-class precision model, unique-minute publication
invariant, target-use profile, controlled rights vocabulary, traceable record
fields, held-out evaluation method, and non-goals.

- [ ] **Step 2: Check for incomplete requirements**

Run:

```bash
rg -n --glob '!docs/superpowers/plans/**' "TBD|TODO|exact-24h|verified-for-target-use" README.md DATA_RIGHTS.md docs
```

Expected: no matches.

- [ ] **Step 3: Verify repository contents and links**

Run:

```bash
git diff --check
test -f README.md && test -f LICENSE && test -f DATA_RIGHTS.md && test -f docs/project-brief.md
```

Expected: both commands exit successfully with no output.

### Task 3: Commit and publish

**Files:**
- Add all files created by Tasks 1 and 2.

- [ ] **Step 1: Review the exact change**

Run:

```bash
git status --short
git diff --stat
```

Expected: only the seven intended initialization files are present.

- [ ] **Step 2: Create the initial commit**

Run:

```bash
git add .gitignore README.md LICENSE DATA_RIGHTS.md docs
git commit -m "chore: initialize literary time corpus"
```

Expected: one root commit on `main` containing only the intended files.

- [ ] **Step 3: Push the initialized repository**

Run:

```bash
git push -u origin main
```

Expected: GitHub accepts the new `main` branch and local `main` tracks
`origin/main`.

- [ ] **Step 4: Verify the published state**

Run:

```bash
git status --short --branch
git rev-parse HEAD
git ls-remote origin refs/heads/main
```

Expected: the worktree is clean, `main` tracks `origin/main`, and both commit
identifiers match.

# Gate 2 synthetic pipeline implementation plan

> **Execution:** Implement each task as a separate vertical TDD slice. Tests may
> observe only the installed `ltc` command, its exit status, stdout/stderr, and
> JSON/JSONL files. They must not import package internals.

**Goal:** Provide an offline, deterministic command-line pipeline that proves
the Gate 2 invariants using synthetic literary text only.

**Non-goals:** This plan does not download ebooks, select Project Gutenberg
works, configure UBTmini, process real literary text, or publish corpus data.

**Architecture:** A Python 3.11 package exposes one `ltc` console script and four
subcommands. Small internal modules own normalization, extraction, release
validation, reporting, stable serialization, hashing, and structured errors.
All runtime behavior uses the Python standard library. `pytest` is the only
development dependency.

**Public error contract:** A successful command exits `0`. Invalid input or a
failed invariant exits `2`, writes exactly one JSON object to stderr with
`error.code`, `error.message`, and optional `error.details`, and does not create
or modify the requested output on failure. Unexpected internal failures exit
`1` using the same envelope with code `internal-error`.

All parsed JSON records first pass a shared recursive UTF-8-encodability guard
over string keys and values, including unknown nested fields, before domain
validation or output serialization.

## Task 1: Package shell and deterministic normalization

**Files:**

- Create `pyproject.toml`
- Create `src/literary_time_corpus/__init__.py`
- Create `src/literary_time_corpus/__main__.py`
- Create `src/literary_time_corpus/cli.py`
- Create `src/literary_time_corpus/io.py`
- Create `src/literary_time_corpus/normalize.py`
- Create `tests/conftest.py`
- Create `tests/fixtures/normalize/valid.txt`
- Create `tests/fixtures/normalize/missing-start.txt`
- Create `tests/test_normalize_cli.py`
- Modify `.gitignore`

**Step 1: Write failing CLI tests**

Run `uv run pytest tests/test_normalize_cli.py -q`. The tests must initially
fail because `ltc` is absent. Cover:

- `ltc --help` lists the four approved command names;
- a fixture containing one unique Project Gutenberg-style START and END marker
  produces a JSON document with `schemaVersion`, `sourceId`, full source SHA-256,
  analysis SHA-256, normalizer version, unchanged literary `analysisText`, and
  UTF-8 byte `bodyStartByte`/`bodyEndByte` selecting that body from the decoded
  source;
- running twice produces byte-identical output;
- a missing or duplicate marker exits `2`, emits the structured error contract,
  and creates no output; and
- a non-UTF-8 input fails closed rather than replacing bytes.

Use synthetic text containing multibyte UTF-8 characters before and inside the
body so offsets cannot accidentally be character indexes.

**Step 2: Implement the minimal command**

Define `ltc normalize --input PATH --output PATH`. Read strict UTF-8 bytes,
compute the untouched source hash, locate exactly one complete marker pair, and
retain the bytes between the newline after START and the newline before END.
Do not trim, normalize line endings, modernize spelling, or alter whitespace.
Set `sourceId` to `synthetic_<first 12 source hash hex digits>`. Write canonical
UTF-8 JSON with sorted keys, compact separators, and a trailing newline through
an atomic temporary-file replacement.

Reject a retained body containing only Unicode whitespace, then validate the
complete generated normalized record through the shared validator before
writing it.

**Step 3: Verify and commit**

Run:

```bash
uv run pytest tests/test_normalize_cli.py -q
uv run ltc normalize --input tests/fixtures/normalize/valid.txt --output /tmp/ltc-normalized.json
git diff --check
git add pyproject.toml src tests .gitignore
git commit -m "feat: add deterministic normalization CLI"
```

Expected: all normalize tests pass, the manual command exits `0`, and the commit
contains no generated `/tmp` artifact.

## Task 2: Exact-time candidate extraction

**Files:**

- Create `src/literary_time_corpus/extract.py`
- Modify `src/literary_time_corpus/cli.py`
- Create `tests/fixtures/extract/times.txt`
- Create `tests/test_extract_cli.py`

**Step 1: Write failing black-box tests**

Normalize the synthetic fixture through `ltc normalize`, then run
`uv run pytest tests/test_extract_cli.py -q`. Tests must fail because `extract`
is not implemented. Cover these initial rule families:

- numeric 12-hour times with periods or case variants, such as `1:17 a.m.`;
- numeric 24-hour times such as `13:15`;
- written minutes past/to the hour, such as `twenty minutes past four`;
- `quarter past`, `quarter to`, and `half past`;
- `noon` and `midnight`;
- ambiguous bare 12-hour clock times without AM/PM or resolving context; and
- approximate expressions such as `about five o'clock`.

Also prove that ISO-style dates, currency amounts, chapter/verse-like numeric
pairs, and durations such as `1:30 hours` do not become releaseable clock-time
candidates. Assert only CLI-visible JSONL fields and behavior.

**Step 2: Implement extraction**

Define `ltc extract --input NORMALIZED_JSON --output CANDIDATES_JSONL`.
Validate the normalized document hashes before extraction. Emit candidate
objects ordered by `(matchStartByte, matchEndByte, candidateId)`, with:

- deterministic `candidateId` using the NUL-separated formula in
  `docs/data-model.md`;
- `sourceId`, source and analysis hashes, extraction/normalization versions;
- rule family and rule ID;
- exact `matchedText`, UTF-8 byte offsets, and an unchanged bounded context;
- `normalizedTimes` and one controlled precision value;
- status plus exclusion/warning reason codes; and
- `quoteBefore`, `quoteTime`, and `quoteAfter` whose concatenation reproduces
  the emitted excerpt and whose `quoteTime` equals `matchedText`.

Use bounded, explicit regular expressions and lookup tables for number words.
Do not infer a missing AM/PM from narrative context in Gate 2. Bare 12-hour
times therefore remain `exact-minute-ambiguous` with both possible HH:MM values.
Approximation markers produce `approximate`. False-positive patterns may either
be omitted or emitted as `automatically-excluded`, but tests require that none
is releaseable.

Require canonical `00:MM` for a zero-hour 24-hour expression; do not emit
single-digit `0:MM`. Validate every generated candidate with the shared
candidate validator before writing any JSONL output.

**Step 3: Verify and commit**

Run:

```bash
uv run pytest tests/test_normalize_cli.py tests/test_extract_cli.py -q
git diff --check
git add src tests
git commit -m "feat: extract exact-time candidates"
```

Expected: normalization remains green, every tested expression has stable byte
offsets and IDs, and repeated extraction is byte-identical.

## Task 3: Fail-closed release validation

**Files:**

- Create `src/literary_time_corpus/validate.py`
- Modify `src/literary_time_corpus/cli.py`
- Create `tests/fixtures/validate/analysis.json`
- Create `tests/fixtures/validate/candidate.json`
- Create `tests/fixtures/validate/review.json`
- Create `tests/fixtures/validate/rights.json`
- Create `tests/test_validate_cli.py`

**Step 1: Write failing release-gate tests**

Run `uv run pytest tests/test_validate_cli.py -q`. Tests must fail because the
command is absent. Define the public interface:

```bash
ltc validate \
  --analysis NORMALIZED_JSON \
  --candidate CANDIDATE_JSON \
  --review REVIEW_JSON \
  --rights RIGHTS_JSON \
  --output RELEASE_JSON
```

The happy path must emit one deterministic release record. Parameterized
negative cases must each exit `2` and not create or modify the output for:
non-resolved precision, zero or multiple normalized minutes, malformed HH:MM,
mismatched candidate/review identity, non-accepted review, changed
human-confirmed time or excerpt, inconsistent quote segmentation, invalid
offsets or hashes, missing jurisdiction, `restricted`/`uncertain` work status,
non-eligible edition status,
non-eligible aggregate decision, unresolved warnings, and target-use profile
other than `zi5-public-corpus-v1`.

**Step 2: Implement the release projection**

Validate all nine invariants in `docs/data-model.md`, including recomputing the
normalized analysis hash and selecting the candidate's excerpt and match from
the exact UTF-8 byte spans in `--analysis`. Require one assessment
each for `US` and `CN-mainland`, each with `workStatus=not-restricted` and
`editionStatus=eligible`, plus aggregate `decision=eligible`. Copy only the
approved provenance, attribution, exact excerpt segmentation, minute, rights
decision, policy/profile, and version fields into the release record. Never
silently repair inputs. Collect deterministic reason codes in
`error.details.violations` so reviewers can act on all observed failures.

The implemented hardening uses one normalized-record validator in both
`extract` and `validate`, and one complete candidate validator in both `report`
and `validate`. Release validation consumes those results instead of
reimplementing record-shape, hash, version, segmentation, or identity checks;
it adds only snapshot linkage, review/rights, provenance, and release-specific
invariants.

**Step 3: Verify and commit**

Run:

```bash
uv run pytest tests/test_validate_cli.py -q
uv run pytest -q
git diff --check
git add src tests
git commit -m "feat: enforce release validation gate"
```

Expected: all release-gate failures are machine-readable and no failed command
leaves a partial release file.

## Task 4: Reproducible Gate 2 report

**Files:**

- Create `src/literary_time_corpus/report.py`
- Modify `src/literary_time_corpus/cli.py`
- Create `tests/fixtures/report/candidates.jsonl`
- Create `tests/test_report_cli.py`

**Step 1: Write failing report tests**

Run `uv run pytest tests/test_report_cli.py -q`. Tests must fail because
`report` is absent. Cover deterministic counts for total candidates, statuses,
precision classes, rule families, exclusion/warning reason codes, unique
resolved minutes, duplicate concentration by minute, and input SHA-256. Confirm
that reordered input rows produce the same metrics but a different input hash,
and that malformed JSONL or inconsistent schema versions fails closed.

**Step 2: Implement reporting**

Define `ltc report --input CANDIDATES_JSONL --output REPORT_JSON`. Stream and
validate JSONL, count controlled values, sort every emitted map/list, and write
canonical JSON. Include `schemaVersion`, report version, candidate schema
version, input byte SHA-256, candidate count, resolved minute count, coverage
fraction over 1,440 minutes, frequency maps, and the top duplicate minutes with
a documented deterministic tie-break. Do not include wall-clock timestamps.
Treat a valid empty extraction as a deterministic zero-metrics report with the
current candidate schema version and empty-input SHA-256; do not relax parsing
of malformed nonempty JSONL.

**Step 3: Verify and commit**

Run:

```bash
uv run pytest tests/test_report_cli.py -q
uv run pytest -q
git diff --check
git add src tests
git commit -m "feat: add reproducible candidate reports"
```

Expected: all CLI suites pass and reports are byte-identical for identical
inputs.

## Task 5: Repository boundary checks and user documentation

**Files:**

- Create `tests/test_repository_policy.py`
- Modify `.gitignore`
- Modify `README.md`
- Modify `docs/data-model.md`
- Modify `docs/pilot-design.md`

**Step 1: Write failing repository-policy tests**

Run `uv run pytest tests/test_repository_policy.py -q`. Add black-box repository
checks that reject tracked content under `.local/`, likely ebook source files in
`manifests/`, `artifacts/`, or `releases/`, and unapproved excerpt artifacts in
`releases/`. The checks may inspect `git ls-files`, but must not assume a clean
working tree.

Because Gate 3 remains closed, the implemented policy is deny-by-default for
all regular data files under `manifests/`, `artifacts/`, and `releases/`. Only
exact empty root `.gitkeep` files and fixed root `README.md` placeholders may be
tracked. Gate 3 must introduce reviewed schema/path allowlists before any
payload is committed; file extensions alone never open the boundary.

**Step 2: Complete the boundary and docs**

Ignore `.local/`, Python caches, virtual environments, and generated build/test
state. Document installation with `uv sync`, all four CLI examples, the
synthetic-only Gate 2 boundary, schemas/versions actually emitted by the code,
the structured error contract, and the fact that passing tests authorizes
neither acquisition nor publication. Update Gate 2 status only to implemented
and locally verified; leave Gates 3 and 4 untouched.

**Step 3: Full verification**

Run:

```bash
uv sync
uv run pytest -q
uv run ltc --help
git diff --check
git status --short
```

Then inspect the diff for secrets, downloaded books, provider boilerplate, real
literary excerpts, host-specific UBTmini configuration, and generated artifacts.

**Step 4: Commit**

```bash
git add .gitignore README.md docs tests pyproject.toml src uv.lock
git commit -m "docs: document Gate 2 pipeline"
```

Expected: the branch contains only code, documentation, and synthetic fixtures.

## Task 6: Independent final review and branch handoff

**Files:** No planned source changes; review fixes, if any, receive their own
test-first commits.

**Step 1: Spec review**

Compare the branch against `docs/project-brief.md`, `docs/pilot-design.md`,
`docs/data-model.md`, `docs/rights-policy.md`, and this plan. Verify that all
Gate 2 evidence is present and no Gate 3 action occurred.

**Step 2: Code-quality and security review**

Review parsing bounds, Unicode byte offsets, hash verification, atomic writes,
path behavior, deterministic serialization, error redaction, and release-gate
fail-closed behavior. Any finding must name a reproducer or exact violated
requirement.

**Step 3: Final evidence**

Run from a clean checkout of the branch:

```bash
uv sync --locked
uv run pytest -q
uv run ltc --help
git diff --check main...HEAD
git status --short --branch
```

Record the exact commit SHA and test counts. Do not push or merge until the user
chooses the branch disposition.

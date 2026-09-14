# Public TXT Scanner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a source-agnostic `ltc scan` command that turns one local UTF-8 TXT file into a deterministic, reviewable five-file analysis directory.

**Architecture:** Refactor normalization into a provider-neutral in-memory operation, then make `scan` orchestrate that operation, the existing extractor and reporter, a Markdown renderer, and a run-manifest builder without subprocesses or duplicated parsing logic. Generate and validate everything in a same-parent temporary directory before a guarded directory transaction exposes the result.

**Tech Stack:** Python 3.11 standard library at runtime, `argparse`, canonical JSON/JSONL, SHA-256, `pytest` black-box CLI tests, Hatchling wheel packaging, and `uv` for development only.

---

## File structure

- Modify `src/literary_time_corpus/normalized.py`: accept the two approved normalization transformation methods and provider-neutral local source identities.
- Modify `src/literary_time_corpus/normalize.py`: expose an in-memory provider-neutral normalizer and make the file command a thin adapter.
- Modify `src/literary_time_corpus/extract.py`: accept optional scan metadata without changing candidate identity.
- Modify `src/literary_time_corpus/candidate.py`: validate the optional versioned work-metadata object.
- Create `src/literary_time_corpus/review.py`: render deterministic Markdown from validated candidates.
- Create `src/literary_time_corpus/scan.py`: validate scan options, orchestrate artifacts, build `run.json`, and publish the directory transactionally.
- Modify `src/literary_time_corpus/cli.py`: expose `scan` and translate its domain errors into the existing JSON error envelope.
- Create `tests/test_scan_cli.py`: black-box scan behavior, metadata, artifacts, determinism, and error-contract tests.
- Create `tests/test_scan_transaction_cli.py`: black-box existing-directory, `--force`, rollback, alias, and final-component replacement tests.
- Create `tests/test_wheel_install.py`: build and install the wheel in a clean virtual environment, then run `ltc scan` without `uv` or the source tree.
- Modify `tests/test_normalize_cli.py`: migrate the low-level command to full-file default and literal marker options.
- Modify `tests/test_extract_cli.py`: cover optional scan metadata and the retained lower-level behavior.
- Modify `tests/test_repository_policy.py`: approve only the newly reviewed Python/test/doc paths; do not add source fixtures.
- Modify `README.md`: make `ltc scan` the primary public workflow and state the TXT-only, provider-neutral and analysis-only boundaries.
- Modify `docs/data-model.md`: define `scan-run-v1`, optional candidate work metadata, and local source identity.
- Modify `docs/pilot-design.md`: record that the reusable scanner is source-agnostic and does not authorize acquisition.

## Task 1: Provider-neutral normalization

**Files:**

- Modify: `src/literary_time_corpus/normalized.py`
- Modify: `src/literary_time_corpus/normalize.py`
- Modify: `src/literary_time_corpus/cli.py`
- Modify: `tests/test_normalize_cli.py`
- Modify: `tests/fixtures/validate/analysis.json`
- Modify: `tests/fixtures/validate/candidate.json`
- Modify: `tests/fixtures/validate/review.json`
- Modify: `tests/test_repository_policy.py`

- [ ] **Step 1: Add failing full-file and literal-marker CLI tests**

Add black-box cases that create all inputs under `tmp_path`; do not add a new
tracked text fixture. The happy path must prove exact bytes and the local ID:

```python
def test_normalize_defaults_to_the_complete_local_text(run_ltc, tmp_path):
    source = tmp_path / "novel.txt"
    output = tmp_path / "normalized.json"
    raw = "Préface 😀\nAt 13:15 the bell rang.\n".encode()
    source.write_bytes(raw)

    result = run_ltc("normalize", "--input", source, "--output", output)

    assert result.returncode == 0
    document = json.loads(output.read_text())
    digest = hashlib.sha256(raw).hexdigest()
    assert document["analysisText"] == raw.decode()
    assert document["sourceId"] == f"local_{digest[:12]}"
    assert document["bodyStartByte"] == 0
    assert document["bodyEndByte"] == len(raw)
    assert document["transformationLog"][0]["method"] == "full-file-selection"
```

Add a paired-marker case with multibyte content before and inside the body. Add
parameterized failures for only one option, missing markers, duplicate markers,
reversed markers, adjacent markers, empty file, whitespace-only body, invalid
UTF-8, and directory input. Assert exit `2`, one JSON stderr object, and
unchanged pre-existing output.

- [ ] **Step 2: Run the new focused tests and verify RED**

Run:

```bash
uv run pytest tests/test_normalize_cli.py -q
```

Expected: the new full-file test fails because the current normalizer requires
Project Gutenberg markers; marker-option parsing fails because the arguments do
not exist.

- [ ] **Step 3: Generalize the normalized-record contract**

In `normalized.py`, replace the single transformation/source-ID assumptions
with exact approved values:

```python
TRANSFORMATION_METHODS = {
    "full-file-selection",
    "literal-marker-body-selection",
}
SOURCE_ID_PATTERN = re.compile(r"local_[0-9a-f]{12}")
```

Require `sourceId == f"local_{sourceSha256[:12]}"`; require one transformation
whose method is in `TRANSFORMATION_METHODS`; retain the current exact body/log
offset checks. Keep `normalized-source-v1` and `normalize-v1` because this
pre-release migration defines their public source-agnostic contract before the
first package release.

- [ ] **Step 4: Implement one in-memory normalizer**

In `normalize.py`, remove the Provider-specific regular expressions and add:

```python
FULL_FILE_METHOD = "full-file-selection"
LITERAL_MARKER_METHOD = "literal-marker-body-selection"

def normalize_bytes(
    source: bytes,
    *,
    start_marker: str | None = None,
    end_marker: str | None = None,
) -> dict[str, object]:
    text = source.decode("utf-8", errors="strict")
    if (start_marker is None) != (end_marker is None):
        raise NormalizationError("invalid-markers", "both markers are required")
    if start_marker is None:
        body_start, body_end = 0, len(source)
        method = FULL_FILE_METHOD
    else:
        start_bytes = start_marker.encode("utf-8")
        end_bytes = end_marker.encode("utf-8")
        if source.count(start_bytes) != 1 or source.count(end_bytes) != 1:
            raise NormalizationError("invalid-markers", "markers must occur exactly once")
        body_start = source.index(start_bytes) + len(start_bytes)
        body_end = source.index(end_bytes)
        if source[body_start:body_start + 2] == b"\r\n":
            body_start += 2
        elif source[body_start:body_start + 1] == b"\n":
            body_start += 1
        if source[max(0, body_end - 2):body_end] == b"\r\n":
            body_end -= 2
        elif source[max(0, body_end - 1):body_end] == b"\n":
            body_end -= 1
        if body_end <= body_start:
            raise NormalizationError("invalid-markers", "markers select no body")
        method = LITERAL_MARKER_METHOD
    analysis = source[body_start:body_end]
    if not analysis.decode("utf-8").strip():
        raise NormalizationError("empty-body", "source body must contain text")
    # Build the existing canonical document with local_ source identity,
    # selected method and exact byte ranges, then call normalized_record_violations.
```

Catch `UnicodeDecodeError` and `UnicodeEncodeError` as controlled `invalid-utf8`
or `invalid-markers` errors without echoing source content.

Change `normalize_file` to accept the same keyword options, read bytes, call
`normalize_bytes`, and atomically write the returned document. Add
`--start-marker` and `--end-marker` to `ltc normalize` and pass them through.

Migrate the synthetic validation records from `synthetic_<hash-prefix>` to the
new `local_<hash-prefix>` identity. Recompute the candidate ID from the existing
NUL-separated formula, update the review's linked candidate ID, and replace the
three changed fixture hashes in `APPROVED_SYNTHETIC_FIXTURE_SHA256`. The fixture
source text and rights conclusions must not change.

- [ ] **Step 5: Verify Task 1**

Run:

```bash
uv run pytest tests/test_normalize_cli.py tests/test_extract_cli.py tests/test_validate_cli.py -q
uv run ltc normalize --input README.md --output /tmp/ltc-readme-normalized.json
git diff --check
```

Expected: all focused tests pass; the manual output has a `local_` source ID and
full-file transformation. Update existing synthetic expected IDs/hashes in
tests as required, but do not weaken any shared validator.

- [ ] **Step 6: Commit Task 1**

```bash
git add src/literary_time_corpus/normalized.py \
  src/literary_time_corpus/normalize.py \
  src/literary_time_corpus/cli.py \
  tests/test_normalize_cli.py tests/test_extract_cli.py tests/test_validate_cli.py \
  tests/fixtures/validate/analysis.json tests/fixtures/validate/candidate.json \
  tests/fixtures/validate/review.json tests/test_repository_policy.py
git commit -m "feat: normalize provider-neutral TXT inputs"
```

## Task 2: Scan command and work metadata

**Files:**

- Create: `src/literary_time_corpus/scan.py`
- Modify: `src/literary_time_corpus/cli.py`
- Modify: `src/literary_time_corpus/extract.py`
- Modify: `src/literary_time_corpus/candidate.py`
- Create: `tests/test_scan_cli.py`
- Modify: `tests/test_extract_cli.py`

- [ ] **Step 1: Write failing scan help and basic workflow tests**

Test the installed command only:

```python
def test_scan_creates_the_public_artifact_inventory(run_ltc, tmp_path):
    source = tmp_path / "my-novel.txt"
    destination = tmp_path / "scan"
    source.write_text("At 13:15 the café bell rang.\n", encoding="utf-8")

    result = run_ltc("scan", source, "--output", destination)

    assert result.returncode == 0
    assert {path.name for path in destination.iterdir()} == {
        "normalized.json", "candidates.jsonl", "report.json", "review.md", "run.json"
    }
    summary = json.loads(result.stdout)
    assert summary == {
        "candidateCount": 1,
        "outputName": "scan",
        "resolvedMinuteCount": 1,
        "status": "complete",
    }
```

Add tests for `ltc scan --help`, no-time input, optional paired markers, title
fallback from the filename stem, explicit title/author/source URL, and exact
preservation of multibyte source offsets. Assert that stderr is empty on
success and stdout is exactly one canonical JSON line.

- [ ] **Step 2: Run scan tests and verify RED**

Run:

```bash
uv run pytest tests/test_scan_cli.py -q
```

Expected: FAIL because `scan` is not a recognized command.

- [ ] **Step 3: Define validated optional work metadata**

In `candidate.py`, add:

```python
WORK_METADATA_SCHEMA_VERSION = "scan-work-metadata-v1"

def work_metadata_violations(value: object) -> list[str]:
    # Require exactly schemaVersion, title, author, sourceUrl, metadataComplete.
    # title/author are nonblank UTF-8 strings; sourceUrl is None or a string;
    # metadataComplete is exactly whether explicit title and author were supplied.
```

Extend `candidate_record_violations` so `workMetadata` may be absent for the
lower-level `extract` command, but when present it must pass this validator.

Change `extract_candidates` to accept
`work_metadata: dict[str, object] | None = None`; `_candidate` copies the same
validated immutable metadata object into each row. Candidate IDs remain based
only on source ID, analysis hash and match byte range.

- [ ] **Step 4: Implement scan option validation and initial orchestration**

Create `scan.py` with exact public constants and errors:

```python
SCAN_SCHEMA_VERSION = "scan-run-v1"
SCAN_VERSION = "scan-v1"

class ScanError(ValueError):
    def __init__(self, code: str, message: str, *, stage: str):
        super().__init__(message)
        self.code = code
        self.details = {"stage": stage}

def build_work_metadata(
    input_path: Path,
    *,
    title: str | None,
    author: str | None,
    source_url: str | None,
) -> dict[str, object]:
    # Reject blank explicit values. If source_url is present, require an
    # absolute http/https URL with hostname and no username/password.
    # Use input_path.stem and "unknown" only as documented fallbacks.
```

Implement `scan_to_staging` by calling `normalize_bytes`,
`extract_candidates(document, work_metadata)`, the shared candidate validator,
`write_json_atomic`, `write_jsonl_atomic`, and `build_report`. It may create
an initial deterministic `review.md` and `run.json` in this task so the basic
inventory test passes; Tasks 3 and 4 complete their full approved contracts.
It must not call `subprocess`.

Add parser arguments:

```python
scan.add_argument("input", type=Path)
scan.add_argument("--output", type=Path, required=True)
scan.add_argument("--title")
scan.add_argument("--author")
scan.add_argument("--source-url")
scan.add_argument("--start-marker")
scan.add_argument("--end-marker")
scan.add_argument("--force", action="store_true")
```

Map `ScanError` through the existing error envelope. For now, publish only to a
nonexistent destination; existing and `--force` behavior is completed in Task
4.

- [ ] **Step 5: Test metadata and source URL failures**

Add parameterized black-box cases for blank title, blank author, relative URL,
non-HTTP scheme, missing hostname, URL username, and URL password. Expected:
exit `2`, `error.code=invalid-scan-metadata`,
`error.details.stage=metadata`, no output directory, and no credential echoed
in stderr.

Run:

```bash
uv run pytest tests/test_scan_cli.py tests/test_extract_cli.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit Task 2**

```bash
git add src/literary_time_corpus/scan.py src/literary_time_corpus/cli.py \
  src/literary_time_corpus/extract.py src/literary_time_corpus/candidate.py \
  tests/test_scan_cli.py tests/test_extract_cli.py
git commit -m "feat: add public TXT scan workflow"
```

## Task 3: Deterministic Markdown review

**Files:**

- Create: `src/literary_time_corpus/review.py`
- Modify: `src/literary_time_corpus/scan.py`
- Modify: `tests/test_scan_cli.py`

- [ ] **Step 1: Add failing review rendering tests**

Create a synthetic temporary input containing one resolved expression, one
ambiguous expression, and one approximate expression. Assert `review.md`:

```python
review = (destination / "review.md").read_text(encoding="utf-8")
assert review.startswith("# Literary time candidate review\n")
assert review.index("## Exact-minute resolved") < review.index("## Exact-minute ambiguous")
assert review.index("## Exact-minute ambiguous") < review.index("## Approximate or excluded")
assert "Not approved for publication" in review
assert candidate_ids == re.findall(r"Candidate ID: `([0-9a-f]{64})`", review)
```

Build `candidate_ids` from `candidates.jsonl` in the same group order. Assert
the unchanged matched text/context, normalized alternatives, rule ID, warnings,
and exclusions are rendered. Add the no-candidate case with all three empty
sections and `Candidate count: 0`.

- [ ] **Step 2: Run and verify RED**

Run:

```bash
uv run pytest tests/test_scan_cli.py -k review -q
```

Expected: FAIL because Task 2's initial Markdown lacks the required groups.

- [ ] **Step 3: Implement the renderer**

In `review.py`, expose only one public operation:

```python
GROUPS = (
    ("resolved", "Exact-minute resolved"),
    ("ambiguous", "Exact-minute ambiguous"),
    ("excluded", "Approximate or excluded"),
)

def review_group(candidate: dict[str, object]) -> str:
    if candidate["status"] == "automatically-excluded" or candidate["precision"] == "approximate":
        return "excluded"
    if candidate["precision"] == "exact-minute-ambiguous":
        return "ambiguous"
    return "resolved"

def render_review_markdown(
    candidates: list[dict[str, object]],
    work_metadata: dict[str, object],
) -> bytes:
    # Validate every candidate first. Preserve candidate order inside each
    # group. Escape Markdown control characters in metadata/rule/reason text,
    # and render source context in fenced text blocks using a fence longer than
    # any backtick run in the content. Always return UTF-8 with one final newline.
```

Use a fixed header containing title, author, metadata completeness, candidate
count, and these exact notices:

```text
This file is a review view, not a review record.
Candidates are not approved for publication.
The user is responsible for permission to process the input text.
```

Do not add checkboxes or wall-clock timestamps.

- [ ] **Step 4: Add content-safety regressions**

Test titles/authors containing Markdown punctuation, context containing triple
backticks, and multibyte content. Assert one candidate occurrence per candidate
ID and no absolute path, username, hostname, or source URL credentials appear.

Run:

```bash
uv run pytest tests/test_scan_cli.py -k 'review or artifact_inventory' -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 3**

```bash
git add src/literary_time_corpus/review.py \
  src/literary_time_corpus/scan.py tests/test_scan_cli.py
git commit -m "feat: render candidate review Markdown"
```

## Task 4: Deterministic run manifest

**Files:**

- Modify: `src/literary_time_corpus/scan.py`
- Modify: `tests/test_scan_cli.py`
- Modify: `docs/data-model.md`

- [ ] **Step 1: Write failing run-manifest tests**

Assert the exact top-level shape:

```python
assert set(run) == {
    "artifactDigests",
    "bodySelection",
    "candidateCount",
    "input",
    "metadata",
    "resolvedMinuteCount",
    "schemaVersion",
    "status",
    "toolVersions",
}
assert run["schemaVersion"] == "scan-run-v1"
assert run["status"] == "complete"
assert run["input"] == {
    "basename": "my-novel.txt",
    "byteSize": len(source_bytes),
    "sha256": hashlib.sha256(source_bytes).hexdigest(),
}
```

Require `artifactDigests` to contain exactly `normalized.json`,
`candidates.jsonl`, `report.json`, and `review.md`, each with `byteSize` and
`sha256` matching the final bytes. Assert the exact tool-version map contains
`scan-v1`, `normalize-v1`, `extract-v1`, `report-v1`, and their schema versions.
Assert full-file body selection omits marker values; marker mode records both
literal values.

- [ ] **Step 2: Run and verify RED**

Run:

```bash
uv run pytest tests/test_scan_cli.py -k run_manifest -q
```

Expected: FAIL because the initial manifest does not bind every artifact.

- [ ] **Step 3: Implement and verify the manifest builder**

Add helpers in `scan.py`:

```python
def artifact_digest(path: Path) -> dict[str, object]:
    content = path.read_bytes()
    return {"byteSize": len(content), "sha256": hashlib.sha256(content).hexdigest()}

def build_run_manifest(
    *, source: bytes, input_basename: str, work_metadata: dict[str, object],
    start_marker: str | None, end_marker: str | None,
    candidates: list[dict[str, object]], report: dict[str, object],
    staging: Path,
) -> dict[str, object]:
    # Build only the exact documented fields and derive all counts from the
    # already validated candidate/report artifacts.
```

After writing `run.json`, re-read all five artifacts, verify its four recorded
digests, verify every JSON/JSONL record with the shared validators, verify the
report input SHA against `candidates.jsonl`, and verify the Markdown contains
every candidate ID exactly once. Raise
`ScanError("scan-verification-failed", ..., stage="verification")` on mismatch.

- [ ] **Step 4: Test determinism and privacy**

Scan identical bytes and options from two different parent directories. Assert
all five corresponding files are byte-identical. Recursively inspect parsed
JSON plus Markdown and assert neither absolute source path, working directory,
username, hostname, temp directory name, nor a wall-clock timestamp appears.

Run:

```bash
uv run pytest tests/test_scan_cli.py -k 'run_manifest or deterministic or privacy' -q
```

Expected: PASS.

- [ ] **Step 5: Document the exact schema and commit**

Add the exact `scan-run-v1` objects and field meanings to `docs/data-model.md`.
State that candidate `workMetadata` is optional only for the lower-level
extract command and required for scan output.

```bash
git add src/literary_time_corpus/scan.py tests/test_scan_cli.py docs/data-model.md
git commit -m "feat: bind scan artifacts with a run manifest"
```

## Task 5: Transactional directory publication

**Files:**

- Modify: `src/literary_time_corpus/scan.py`
- Create: `tests/test_scan_transaction_cli.py`

- [ ] **Step 1: Write failing refusal and force-replacement tests**

Cover these CLI-visible cases:

```python
def test_existing_output_is_preserved_without_force(run_ltc, tmp_path):
    source = tmp_path / "book.txt"
    output = tmp_path / "scan"
    source.write_text("At 13:15.", encoding="utf-8")
    output.mkdir()
    sentinel = output / "keep.txt"
    sentinel.write_text("old", encoding="utf-8")

    result = run_ltc("scan", source, "--output", output)

    assert result.returncode == 2
    assert sentinel.read_text() == "old"
```

Add a `--force` success case asserting the sentinel disappears and the exact
five-file inventory replaces it. Add failures for output symlink, output equal
to input, input inside output, missing output parent, output parent being a
file, output being a regular file, and a symlink-loop path. None may modify the
input, link target, existing directory, or unrelated sibling.

- [ ] **Step 2: Run and verify RED**

Run:

```bash
uv run pytest tests/test_scan_transaction_cli.py -q
```

Expected: the existing destination/`--force` tests fail because Task 2 does not
yet implement the guarded transaction.

- [ ] **Step 3: Implement the guarded same-parent transaction**

In `scan.py`, introduce a small immutable target snapshot:

```python
@dataclass(frozen=True)
class ExistingTarget:
    device: int
    inode: int

def snapshot_directory(path: Path) -> ExistingTarget:
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise ScanError("unsafe-output-path", "output must be a directory", stage="output")
    return ExistingTarget(info.st_dev, info.st_ino)
```

Use `tempfile.mkdtemp(prefix=f".{output.name}.scan-", dir=output.parent)` for
staging. Immediately before publication, compare `lstat()` with the captured
device/inode to reject a changed final component.

For a new target, `os.rename(staging, output)`. For `--force`:

1. rename the unchanged old directory to a random same-parent backup name;
2. rename the verified staging directory to the requested output name;
3. if step 2 fails, rename the backup back before raising;
4. after commit, remove the backup with `shutil.rmtree` without following
   symbolic links.

Never recursively remove the user-supplied output path directly. Never accept
`/`, a filesystem root, `.` after resolution, or an output containing the input
path. Error details may expose only `stage` and a retained backup basename.

- [ ] **Step 4: Add black-box generation-failure preservation tests**

Use an invalid UTF-8 source, invalid markers, and invalid metadata with an
existing output plus `--force`. Assert the old directory tree is byte-for-byte
unchanged and no `.scan-` or `.backup-` sibling remains.

Add a coordinated FIFO test: pause source reading, replace the final output
directory entry with a symlink before publication, resume input, and assert the
link target and moved original directory remain unchanged while scan exits `2`.
Keep all paths under `tmp_path` and bound subprocess waits with timeouts.

- [ ] **Step 5: Verify Task 5 and commit**

Run:

```bash
uv run pytest tests/test_scan_transaction_cli.py tests/test_scan_cli.py -q
uv run pytest -q
git diff --check
```

Expected: all tests pass and no temporary/backup directories remain.

```bash
git add src/literary_time_corpus/scan.py tests/test_scan_transaction_cli.py
git commit -m "feat: publish scan directories transactionally"
```

## Task 6: Packaging, documentation, and repository boundary

**Files:**

- Create: `tests/test_wheel_install.py`
- Modify: `tests/test_repository_policy.py`
- Modify: `README.md`
- Modify: `docs/pilot-design.md`
- Modify: `docs/data-model.md`
- Modify: `.gitignore`

- [ ] **Step 1: Add a failing clean-wheel test**

The test must build once into a temporary directory, create a clean venv, and
run the installed executable with an input outside the repository:

```python
subprocess.run(["uv", "build", "--wheel", "--out-dir", str(dist)], check=True)
subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)
subprocess.run([str(python), "-m", "pip", "install", "--no-deps", str(wheel)], check=True)
result = subprocess.run(
    [str(ltc), "scan", str(source), "--output", str(output)],
    cwd=tmp_path,
    env={"PATH": os.defpath},
    capture_output=True,
    text=True,
)
assert result.returncode == 0
assert {path.name for path in output.iterdir()} == EXPECTED_ARTIFACTS
```

Do not use `uv run` for the installed command. Assert the wheel contains only
the package modules and metadata, not tests, docs, fixtures, `.local`, scan
outputs, or source books.

- [ ] **Step 2: Run and verify RED or packaging gap**

Run:

```bash
uv run pytest tests/test_wheel_install.py -q
```

Expected before final packaging work: either FAIL on the new public command or
PASS only after proving the current package discovery already includes every
new module. Record the observed result; do not manufacture a failure.

- [ ] **Step 3: Update ignore and repository policies**

Add `scans/` to `.gitignore` while retaining `.local/`. Update the strict path
allowlist for the new Python/test/doc files. Do not add scan output or TXT
fixtures. Add a repository-policy test proving `scans/example/normalized.json`
is ignored and cannot be tracked under the approved policy.

- [ ] **Step 4: Write public-user documentation**

Make `ltc scan` the first README example. Document:

- Python 3.11+ installation from a future PyPI package and current source/wheel;
- minimum, metadata, marker, and `--force` examples;
- exact five outputs and which contain source text;
- JSON stdout/error scripting contracts;
- TXT-only UTF-8 and provider-neutral scope;
- analysis versus review versus release;
- the user-responsibility and MIT/data-rights boundary;
- no Gutenberg search/download and no Provider/format-converter API in v1; and
- advanced lower-level commands.

In `docs/pilot-design.md`, state that the public scanner can analyze
user-supplied eligible text but neither selects nor acquires the 72-work pilot.
Ensure `docs/data-model.md` and README use the exact same schema/version/property
names.

- [ ] **Step 5: Verify the packaged public workflow**

Run:

```bash
uv sync --locked
uv run pytest -q
uv run ltc scan --help
uv build --wheel
python3 -m compileall -q src
git diff --check
git status --short
```

Inspect the wheel file list and repository diff for absolute paths, secrets,
real literary text, generated scan directories, Provider code, host config, or
Gate 3/4 artifacts.

- [ ] **Step 6: Commit Task 6**

```bash
git add .gitignore README.md docs/data-model.md docs/pilot-design.md \
  tests/test_wheel_install.py tests/test_repository_policy.py pyproject.toml uv.lock
git commit -m "docs: publish the TXT scanner workflow"
```

## Task 7: Independent final acceptance

**Files:** No planned source changes. Any finding receives a focused failing
test and its own fix commit before this task is repeated.

- [ ] **Step 1: Spec review**

Compare the branch to
`docs/superpowers/specs/2026-09-14-public-txt-scanner-design.md`. Confirm every
CLI option, output field, failure behavior, rights disclaimer, and deferred item
is represented, and that no Provider/download/converter implementation exists.

- [ ] **Step 2: Code-quality and safety review**

Review the in-memory module reuse, candidate/normalized shared validators,
Markdown escaping, URL credential filtering, path alias checks, force rollback,
final-component race behavior, deterministic serialization, privacy fields,
and wheel contents. Findings must include a black-box reproducer or a direct
violation of the approved spec.

- [ ] **Step 3: Final clean verification**

Run:

```bash
uv sync --locked
uv run pytest -q
uv run ltc --help
uv run ltc scan --help
uv build --wheel
python3 -m compileall -q src
git diff --check main...HEAD
git status --short --branch
```

Run two scans from different directories using identical UTF-8 bytes and
metadata and compare all five output SHA-256 values. Run a no-time scan and a
failed `--force` scan against an existing directory. Record the exact commit,
test count, wheel name, artifact hashes, and tracked-data audit.

- [ ] **Step 4: Handoff without implicit publication**

Do not merge, push, publish to PyPI, acquire books, or deploy host configuration
until the user chooses the branch disposition and separately authorizes any
external publication action.

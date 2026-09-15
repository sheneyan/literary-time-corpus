# extract-v2 O'clock Rules Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Recognize numeric and written English o'clock expressions, exclude approximate forms, and remove named-time period false positives found by the five-book smoke test.

**Architecture:** Extend the existing ordered regular-expression pipeline in `extract.py`. Approximate o'clock matching runs first and occupies its span; exact o'clock matching then emits an AM/PM-ambiguous candidate. The named-time rule uses a narrow negative lookahead for `hour` and `hours`; no provider or language abstraction is added.

**Tech Stack:** Python 3.11, `re`, pytest, existing `ltc normalize`, `ltc extract`, and `ltc scan` commands

---

### Task 1: Add extract-v2 o'clock candidates

**Files:**
- Modify: `src/literary_time_corpus/extract.py`
- Modify: `src/literary_time_corpus/candidate.py`
- Modify: `tests/test_extract_cli.py`
- Modify: `tests/test_scan_cli.py`
- Modify: `tests/test_validate_cli.py`
- Modify: `tests/test_report_cli.py`
- Modify: `tests/test_repository_policy.py`
- Modify: `tests/fixtures/report/candidates.jsonl`
- Modify: `tests/fixtures/validate/candidate.json`

- [ ] **Step 1: Add a reusable synthetic-text extraction helper and failing rule test**

Add this helper to `tests/test_extract_cli.py`:

```python
def extract_text(run_ltc, tmp_path: Path, text: str) -> list[dict[str, object]]:
    source = tmp_path / "source.txt"
    normalized = tmp_path / "normalized.json"
    output = tmp_path / "candidates.jsonl"
    source.write_text(text, encoding="utf-8")
    normalized_result = run_ltc(
        "normalize", "--input", source, "--output", normalized
    )
    assert normalized_result.returncode == 0, normalized_result.stderr
    extract_result = run_ltc(
        "extract", "--input", normalized, "--output", output
    )
    assert extract_result.returncode == 0, extract_result.stderr
    return [
        json.loads(line)
        for line in output.read_text(encoding="utf-8").splitlines()
    ]
```

Add a test using synthetic prose only:

```python
def test_extract_supports_oclock_hours_and_approximate_precedence(
    run_ltc, tmp_path: Path
) -> None:
    rows = extract_text(
        run_ltc,
        tmp_path,
        "About 8 o'Clock, the synthetic bell was silent. "
        "At eleven o'Clock it rang. At 7 o’clock it rang again. "
        "Approximately twelve o’clock, the synthetic test ended.\n",
    )

    assert [row["matchedText"] for row in rows] == [
        "About 8 o'Clock",
        "eleven o'Clock",
        "7 o’clock",
        "Approximately twelve o’clock",
    ]
    first, eleven, seven, last = rows
    for approximate in (first, last):
        assert approximate["precision"] == "approximate"
        assert approximate["status"] == "automatically-excluded"
        assert approximate["normalizedTimes"] == []
        assert approximate["exclusionReasonCodes"] == [
            "approximate-expression"
        ]
        assert approximate["ruleId"] == "approx-about-oclock-v2"
    assert eleven["normalizedTimes"] == ["11:00", "23:00"]
    assert seven["normalizedTimes"] == ["07:00", "19:00"]
    for exact in (eleven, seven):
        assert exact["precision"] == "exact-minute-ambiguous"
        assert exact["warningReasonCodes"] == ["missing-meridiem"]
        assert exact["ruleId"] == "oclock-hour-v1"
        assert exact["extractionVersion"] == "extract-v2"
```

- [ ] **Step 2: Run the new test and verify RED**

Run:

```bash
uv run pytest -q tests/test_extract_cli.py::test_extract_supports_oclock_hours_and_approximate_precedence
```

Expected: failure because numeric approximate and general exact o'clock forms are not yet emitted.

- [ ] **Step 3: Implement the two ordered o'clock rules**

In `extract.py`, set `EXTRACTION_VERSION = "extract-v2"`, add a combined hour
token and parser, expand the approximate rule, and add the exact rule immediately
after it:

```python
OCLOCK_HOUR_PATTERN = rf"(?:0?[1-9]|1[0-2]|{HOUR_PATTERN})"


def _hour_value(token: str) -> int:
    lowered = token.lower()
    return HOUR_WORDS[lowered] if lowered in HOUR_WORDS else int(token)
```

```python
approximate = re.compile(
    rf"\b(?:about|approximately)\s+({OCLOCK_HOUR_PATTERN})"
    rf"\s+o['’]clock\b",
    re.IGNORECASE,
)
```

Keep its existing candidate shape but change the rule ID to
`approx-about-oclock-v2`. Then add:

```python
oclock_hour = re.compile(
    rf"\b({OCLOCK_HOUR_PATTERN})\s+o['’]clock\b", re.IGNORECASE
)

def build_oclock_hour(match: re.Match[str]) -> dict[str, Any]:
    hour = _hour_value(match.group(1))
    return _candidate(
        document,
        match,
        rule_family="oclock-hour",
        rule_id="oclock-hour-v1",
        normalized_times=_twelve_hour_values(hour, 0),
        precision="exact-minute-ambiguous",
        warnings=["missing-meridiem"],
    )

add_matches(oclock_hour, build_oclock_hour)
```

Set `EXTRACTION_VERSION = "extract-v2"` in `candidate.py` as well.

- [ ] **Step 4: Update current v2 expectations and pinned fixture hashes**

Change current executable-contract expectations from `extract-v1` to
`extract-v2` in `tests/test_extract_cli.py`, `tests/test_scan_cli.py`,
`tests/test_validate_cli.py`, `tests/fixtures/report/candidates.jsonl`, and
`tests/fixtures/validate/candidate.json`. In the report fixture, change
`approx-about-oclock-v1` to `approx-about-oclock-v2`; named-time rule IDs are
updated in Task 2.

After the Task 1 fixture edits, set:

```python
# tests/test_report_cli.py
FIXTURE_SHA256 = "cc58f58af344a7567ba5639a6ba7e1a020b486cd333ae9836e4f0ee45947f46d"
```

and update the two matching entries in
`APPROVED_SYNTHETIC_FIXTURE_SHA256`:

```python
"tests/fixtures/report/candidates.jsonl":
    "cc58f58af344a7567ba5639a6ba7e1a020b486cd333ae9836e4f0ee45947f46d"
"tests/fixtures/validate/candidate.json":
    "9fecf5149804933fcfc8e0be6a2a8b453e96d69b18debab79ef69c524eb02b9e"
```

- [ ] **Step 5: Verify o'clock behavior and the existing suite**

Run:

```bash
uv run pytest -q tests/test_extract_cli.py tests/test_scan_cli.py \
  tests/test_validate_cli.py tests/test_report_cli.py \
  tests/test_repository_policy.py
```

Expected: all focused tests pass. If a pinned hash differs, stop and inspect the
fixture diff; do not accept an unexplained hash.

- [ ] **Step 6: Commit Task 1**

```bash
git add src/literary_time_corpus/extract.py \
  src/literary_time_corpus/candidate.py tests/test_extract_cli.py \
  tests/test_scan_cli.py tests/test_validate_cli.py tests/test_report_cli.py \
  tests/test_repository_policy.py tests/fixtures/report/candidates.jsonl \
  tests/fixtures/validate/candidate.json
git commit -m "feat: extract oclock hour candidates"
```

### Task 2: Filter named-time period phrases

**Files:**
- Modify: `src/literary_time_corpus/extract.py`
- Modify: `tests/test_extract_cli.py`
- Modify: `tests/fixtures/report/candidates.jsonl`
- Modify: `tests/test_report_cli.py`
- Modify: `tests/test_repository_policy.py`

- [ ] **Step 1: Add the failing named-time context test**

```python
def test_extract_ignores_named_times_used_as_hour_periods(
    run_ltc, tmp_path: Path
) -> None:
    rows = extract_text(
        run_ltc,
        tmp_path,
        "At noon the synthetic clock rang. During the noon hours it rested. "
        "In the midnight hour it stirred. At midnight it rang again.\n",
    )

    assert [row["matchedText"].lower() for row in rows] == [
        "noon",
        "midnight",
    ]
    assert [row["normalizedTimes"] for row in rows] == [
        ["12:00"],
        ["00:00"],
    ]
    assert all(row["ruleId"] == "named-noon-midnight-v2" for row in rows)
```

- [ ] **Step 2: Run the new test and verify RED**

Run:

```bash
uv run pytest -q tests/test_extract_cli.py::test_extract_ignores_named_times_used_as_hour_periods
```

Expected: four candidates are emitted instead of two.

- [ ] **Step 3: Narrow the named-time pattern**

Replace the named-time pattern and rule ID with:

```python
named = re.compile(
    r"\b(noon|midnight)\b(?!\s+hours?\b)", re.IGNORECASE
)
```

```python
rule_id="named-noon-midnight-v2"
```

- [ ] **Step 4: Update the report fixture and its exact hashes**

Change both `named-noon-midnight-v1` rows in
`tests/fixtures/report/candidates.jsonl` to `named-noon-midnight-v2`. The final
fixture SHA-256 must be:

```text
6701450094913a5194dfd644d6b3237d0fa46b85ea675c4a26a8c3c1995c2d0e
```

Update `FIXTURE_SHA256` in `tests/test_report_cli.py` and the matching report
fixture entry in `APPROVED_SYNTHETIC_FIXTURE_SHA256` to this final value. Verify
it rather than changing it blindly:

```bash
shasum -a 256 tests/fixtures/report/candidates.jsonl
```

- [ ] **Step 5: Run focused and full tests**

```bash
uv run pytest -q tests/test_extract_cli.py tests/test_report_cli.py \
  tests/test_repository_policy.py
uv run pytest -q
python3 -m compileall -q src
git diff --check
```

Expected: the complete suite passes, compileall is silent, and diff check is
clean.

- [ ] **Step 6: Commit Task 2**

```bash
git add src/literary_time_corpus/extract.py tests/test_extract_cli.py \
  tests/fixtures/report/candidates.jsonl tests/test_report_cli.py \
  tests/test_repository_policy.py
git commit -m "fix: filter named-time period phrases"
```

### Task 3: Document v2 and rerun the five local books

**Files:**
- Modify: `README.md`
- Modify: `docs/data-model.md`
- Local ignored output: `scans/gutenberg-smoke-extract-v2-2026-09-15/`

- [ ] **Step 1: Update current executable-contract documentation**

Change the current time-candidate version rows in `README.md` and
`docs/data-model.md` to:

```markdown
`extractionVersion=extract-v2`
```

Do not rewrite historical implementation plans that describe the earlier v1
milestone.

- [ ] **Step 2: Verify documentation and commit**

```bash
uv run pytest -q tests/test_repository_policy.py
git diff --check
git add README.md docs/data-model.md
git commit -m "docs: record extract-v2 contract"
```

- [ ] **Step 3: Scan the five user-supplied books into a new ignored batch**

Run from the repository root:

```bash
batch=scans/gutenberg-smoke-extract-v2-2026-09-15
test ! -e "$batch"
mkdir -p "$batch"
for id in 4852 46721 37539 33553 26621; do
  input="/Users/sheneyan/Downloads/pg${id}.txt"
  title=$(sed -n 's/^Title: //p' "$input" | head -1 | tr -d '\r')
  author=$(sed -n 's/^Author: //p' "$input" | head -1 | tr -d '\r')
  start_marker=$(rg -m1 '^\*\*\* START OF (THE|THIS) PROJECT GUTENBERG EBOOK ' "$input" | tr -d '\r')
  end_marker=$(rg -m1 '^\*\*\* END OF (THE|THIS) PROJECT GUTENBERG EBOOK ' "$input" | tr -d '\r')
  uv run ltc scan "$input" \
    --output "$batch/pg${id}" \
    --title "$title" \
    --author "$author" \
    --source-url "https://www.gutenberg.org/ebooks/${id}" \
    --start-marker "$start_marker" \
    --end-marker "$end_marker"
done
```

Expected scan summaries:

```text
pg4852  candidateCount=0 resolvedMinuteCount=0
pg46721 candidateCount=0 resolvedMinuteCount=0
pg37539 candidateCount=0 resolvedMinuteCount=0
pg33553 candidateCount=0 resolvedMinuteCount=0
pg26621 candidateCount=2 resolvedMinuteCount=0
```

- [ ] **Step 4: Verify pg26621 classifications and repository privacy**

Inspect `candidates.jsonl` and require:

```text
About 8 o'Clock     approximate, automatically-excluded, no normalized time
eleven o'Clock      exact-minute-ambiguous, normalized to 11:00 and 23:00
```

Then run:

```bash
test -z "$(git status --porcelain)"
git check-ignore -q "$batch/pg26621/candidates.jsonl"
uv run pytest -q
git diff --check main...HEAD
```

Expected: the local scan remains ignored, the complete suite passes, and the
branch diff is clean. Do not commit source books or scan outputs.

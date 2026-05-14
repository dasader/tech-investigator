# A3 Per-Source Search Concurrency Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the blanket `Semaphore(1)` in `search_node` with a per-source concurrency limit so Scopus and OpenAlex searches run in parallel up to their rate-limit budgets.

**Architecture:** Add a module-level `CONCURRENCY` dict and a pure `_concurrency_for(source)` helper to `pipeline.py`. `search_node` sizes its `asyncio.Semaphore` from the helper using `state["search_source"]`. The helper is unit-tested directly; `search_node`'s one-line wiring is left to code review.

**Tech Stack:** Python 3.x, FastAPI, Celery, asyncio, pytest. Spec: `docs/superpowers/specs/2026-05-14-a3-per-source-concurrency-design.md`.

**Test invocation:** Inside the api container (working directory `/app/backend`), so pytest paths are `tests/...` NOT `backend/tests/...`. Always run via `docker compose exec api pytest tests/...`.

**Commit strategy:** All code + test changes land as a single commit in Task 1. Task 2 is a separate docs commit.

---

## Pre-flight

### Task 0: Branch setup

**Files:** none

- [ ] **Step 0.1: Verify clean repo state on master**

Run: `git status --short | grep -v '\.pyc' | grep -v dockerbuild.bat`
Expected: empty output (only pre-existing `.pyc` and `dockerbuild.bat` working-tree noise).

- [ ] **Step 0.2: Create implementation branch**

Run: `git checkout -b chore/a3-per-source-concurrency`
Expected: `Switched to a new branch 'chore/a3-per-source-concurrency'`

- [ ] **Step 0.3: Confirm Docker api container is up**

Run: `docker compose ps`
Expected: `api`, `db`, `redis` in `running` state. If not, `docker compose up -d` and wait for healthchecks.

- [ ] **Step 0.4: Capture baseline test count**

Run: `docker compose exec api pytest tests/ 2>&1 | tail -3`
Expected: `39 passed`. The final regression after Task 1 must show `44 passed`.

---

## Task 1: Per-source concurrency in `pipeline.py`

**Files:**
- Create: `backend/tests/test_pipeline.py`
- Modify: `backend/app/agents/pipeline.py` (add `CONCURRENCY` dict + `_concurrency_for` helper; one-line change in `search_node`)

- [ ] **Step 1.1: Write the failing test file**

Create `backend/tests/test_pipeline.py`:

```python
import pytest
from app.agents.pipeline import _concurrency_for, CONCURRENCY

pytestmark = pytest.mark.no_db


def test_concurrency_semantic_scholar_is_serial():
    assert _concurrency_for("semantic_scholar") == 1


def test_concurrency_scopus():
    assert _concurrency_for("scopus") == 5


def test_concurrency_openalex():
    assert _concurrency_for("openalex") == 10


def test_concurrency_unknown_source_falls_back_to_serial():
    assert _concurrency_for("some_future_source") == 1


def test_concurrency_dict_covers_all_known_sources():
    # search_source의 Literal 후보와 CONCURRENCY 키가 어긋나지 않도록 가드
    assert set(CONCURRENCY) == {"semantic_scholar", "scopus", "openalex"}
```

- [ ] **Step 1.2: Run the test to confirm it fails**

Run: `docker compose exec api pytest tests/test_pipeline.py -v`
Expected: collection error — `ImportError: cannot import name '_concurrency_for' from 'app.agents.pipeline'`.

- [ ] **Step 1.3: Add `CONCURRENCY` dict and `_concurrency_for` helper to `pipeline.py`**

Edit `backend/app/agents/pipeline.py`. Find the existing `_update_job` function:

```python
def _update_job(db: Session, job_id: int, progress_pct: float, current_step: str):
    job = db.query(Job).filter(Job.id == job_id).first()
    if job:
        job.progress_pct = progress_pct
        job.current_step = current_step
        db.commit()
```

Insert the following two definitions immediately ABOVE `_update_job` (i.e. right after the `PipelineState` TypedDict class, before `_update_job`):

```python
# 외부 API rate limit에 맞춘 source별 검색 동시성.
# Semantic Scholar: 무키 ~1 req/s, Scopus: ~9 req/s, OpenAlex: ~100 req/s.
CONCURRENCY = {"semantic_scholar": 1, "scopus": 5, "openalex": 10}


def _concurrency_for(source: str) -> int:
    return CONCURRENCY.get(source, 1)


```

- [ ] **Step 1.4: Run the test to confirm it passes**

Run: `docker compose exec api pytest tests/test_pipeline.py -v`
Expected: 5 passed.

- [ ] **Step 1.5: Wire `search_node` to use the helper**

Edit `backend/app/agents/pipeline.py`. Find this line inside `search_node`:

```python
    semaphore = asyncio.Semaphore(1)
```

Replace it with:

```python
    semaphore = asyncio.Semaphore(_concurrency_for(state["search_source"]))
```

This is the only change in `search_node` — the rest of the function (`tasks` list comprehension, `asyncio.gather`, result mapping) is untouched.

- [ ] **Step 1.6: Syntax-check the module**

Run: `docker compose exec api python -c "from app.agents.pipeline import search_node, _concurrency_for, CONCURRENCY; print('imports ok')"`
Expected: `imports ok` (no SyntaxError/ImportError).

- [ ] **Step 1.7: Full regression sweep**

Run: `docker compose exec api pytest tests/ -v 2>&1 | tail -5`
Expected: **44 passed** (39 baseline + 5 new from `test_pipeline.py`). If any test fails, STOP and diagnose.

- [ ] **Step 1.8: Confirm working tree contains only this task's files**

Run: `git status --short | grep -v '\.pyc' | grep -v dockerbuild.bat`
Expected: exactly these 2 lines:
```
 M backend/app/agents/pipeline.py
?? backend/tests/test_pipeline.py
```

- [ ] **Step 1.9: Commit**

```bash
git add backend/app/agents/pipeline.py backend/tests/test_pipeline.py
git commit -m "perf(pipeline): per-source search concurrency

search_node serialized every search source through Semaphore(1).
Semantic Scholar's keyless ~1 req/s limit makes that reasonable for S2,
but Scopus (~9 req/s) and OpenAlex (~100 req/s) were needlessly slow.
Add a CONCURRENCY dict and _concurrency_for helper so each source gets
a semaphore sized to its rate budget (semantic_scholar: 1, scopus: 5,
openalex: 10). The per-attempt inter_attempt_sleep stays in place and,
combined with the bounded semaphore, keeps burst rate within limits."
```

- [ ] **Step 1.10: Verify the commit**

Run: `git show HEAD --stat`
Expected: 2 files changed — `backend/app/agents/pipeline.py`, `backend/tests/test_pipeline.py`.

---

## Task 2: Update follow-up document

**Files:**
- Modify: `docs/260513-further-jobs.md`

- [ ] **Step 2.1: Mark A3 as done in the status banner**

Edit `docs/260513-further-jobs.md`. Find the existing line under `## A. Skipped from ...`:

```markdown
> **Status (2026-05-14):** A1, A2, A4 완료 — A2는 `chore/a2-shared-httpx-client` 브랜치. A3은 미해결.
```

Replace with:

```markdown
> **Status (2026-05-14):** A1-A4 전부 완료. A3은 `chore/a3-per-source-concurrency` 브랜치. 본 문서의 모든 항목(A1-A4 + B1) 처리 완료.
```

- [ ] **Step 2.2: Commit the status update**

```bash
git add docs/260513-further-jobs.md
git commit -m "docs: mark A3 done — all further-jobs items complete"
```

- [ ] **Step 2.3: Final verification**

Run: `git log --oneline master..HEAD`
Expected: exactly 2 commits — `perf(pipeline): per-source search concurrency` and `docs: mark A3 done — all further-jobs items complete`.

Run: `docker compose exec api pytest tests/ -v 2>&1 | tail -3`
Expected: 44 passed.

---

## Notes for the executing engineer

- **Working directory**: `C:\Users\ilhwa\Downloads\_cursors\17_Spec-investigation`. pytest runs inside the api container — use `tests/...` not `backend/tests/...`.
- **Pre-existing noise**: `git status` shows modified `.pyc` files and untracked `dockerbuild.bat`. Never stage them — Step 1.8 explicitly filters them out.
- **Why no `search_node` test**: `search_node` depends on `db` (via `_update_job`) and the size of an `asyncio.Semaphore` is not externally observable without touching its private `._value`. The pure `_concurrency_for` helper carries the testable logic; the one-line wiring in `search_node` is a code-review concern. Do not add a brittle `search_node` integration test.
- **Pyright noise**: The host's Pyright will report false-positive `app.agents.* could not be resolved` and pre-existing `pipeline.py` attribute-access warnings. Ignore — only pytest output is authoritative.
- **Scope discipline**: Do NOT touch `extract_node`'s `Semaphore(10)` — A3 is search-stage only. Do NOT expose concurrency via `config.py`. Do NOT change `inter_attempt_sleep`.

# LLM Browser Driver — Comprehensive Product Requirements Document

**Status:** Active — Post M1/M2, Pre-M3
**Created:** 2026-05-21
**Source:** `spikes/browser-use-augment/` in Hauliage repo (2026-04 to 2026-05)
**Goal:** Production-ready, CI-deployable, open-source LLM browser testing tool

---

## 1. Executive Summary

LLM Browser Driver is a standalone, open-source Python library that enables autonomous AI-driven web testing and exploration. It combines Playwright's browser automation with an LLM's ability to understand and navigate pages without hardcoded selectors.

**Key differentiator:** Zero selector maintenance. The LLM discovers elements the way a human does — by labels, text content, and structure — so UI refactors don't break tests.

**Current state (M1–M2 complete):**
- Core interaction loop with 8 action types and anti-fragile selector matching
- Screenshot capture with interval and on-failure modes
- Multi-format reporting (JSON, Markdown, HTML with screenshot thumbnails, JUnit XML)
- Run versioning with `run-{timestamp}/` hierarchy and central dashboard
- `serve` command for local HTTP viewing
- 128 unit tests passing, `pip install` support, full CLI (explore/batch/serve)

**Next phase:** Productionize for CI/CD — robust output, spec-driven testing, structured observability, open-source ecosystem, LangChain/LangGraph agent patterns, and per-commit testing that gives teams confidence to adopt this as a primary test layer.

---

## 2. Problem Statement

Static E2E test suites face three fundamental problems:

1. **Selector brittleness** — DOM changes (class name swaps, ID rewrites, component restructuring) break test selectors. Teams spend more time fixing tests than finding bugs.
2. **Exponential growth** — Every new feature, state, or edge case multiplies the number of test scenarios to maintain.
3. **Missing exploratory depth** — Deterministic tests validate known paths. They don't discover unknown bugs like broken navigation, unexpected state transitions, or missing error states.

Manual exploratory testing solves (3) but doesn't scale. LLM Browser Driver brings human-level exploration into an automated, repeatable, scriptable pipeline that runs on every commit.

---

## 3. Product Capabilities

### C1: Autonomous Interactive Testing (Core) — ✅ DONE

An LLM drives a Playwright browser session in a closed loop:

1. **State capture** — Extract comprehensive page state (elements, text, forms, accessibility tree, console errors, HTML snippet)
2. **LLM reasoning** — Given page state + goal + action history, the LLM decides the next action
3. **Action execution** — Driver executes the action (click, fill, select, navigate, scroll, evaluate, wait, go_back, done)
4. **Screenshot capture** — Per-iteration screenshots at configurable intervals, plus failure screenshots
5. **Loop** — Repeat until goal achieved or max iterations reached

**Actions supported:**

| Action | Parameters | Selection Strategy |
|--------|-----------|-------------------|
| `click` | `element` | ID match → button text → link href → fuzzy fallback |
| `fill` | `field`, `value` | Name → placeholder → ID → aria-label → label[for] text |
| `select` | `field`, `option` | Select name match → option text match |
| `navigate` | `url` | Full URL navigation |
| `scroll` | `direction`, `distance` | `window.scrollBy` |
| `wait` | `condition` | `networkidle`, `load`, or custom timeout |
| `evaluate` | `script` | Arbitrary JS with auto-rewriting of `console.log` |
| `go_back` | — | Browser history |
| `done` | `summary` | Terminate and report |

**Selection strategy detail:** The driver never uses CSS class selectors or XPath. Every action is matched by semantically stable identifiers:

- Clicks: element `id` attribute (primary), button/link visible text (secondary)
- Fills: input `name`, `placeholder`, `id`, `aria-label`, associated `<label[for]>` text (all checked, first match wins)
- This is the core anti-fragility property — as long as the page is accessible, tests still work.

### C2: Reporting & Visual Dashboard — ✅ DONE

Multi-format output with run versioning and visual evidence:

**Formats:**
- **JSON** — machine-readable, machine-parsable
- **Markdown** — human-readable summary table
- **HTML** — rich dark-themed report with screenshot thumbnail column
- **JUnit XML** — CI/CD integration (CircleCI, GitHub Actions, Jenkins)

**Run versioning:**
- Each execution creates `run-{timestamp}-{test-label}/` under `results/`
- All formats + screenshots + report.json stored in run directory
- Central `results/index.html` dashboard listing all runs with pass/fail stats, step counts, and screenshot badges
- Dashboard auto-updates on each new run
- `llm-browser-driver serve --directory results/` launches local HTTP server with browser auto-open

**Directory structure:**
```
results/
├── index.html                  # Central dashboard
├── run-2026-05-21T10-00-00-login/
│   ├── report.json
│   ├── report.html
│   ├── report.md
│   ├── report.xml
│   └── screenshots/
│       ├── step-1.png
│       ├── step-2.png
│       └── step-5-failure.png
└── run-2026-05-21T11-00-00-signup/
    └── ...
```

### C3: CI/CD Pipeline — NEW

This is the critical missing piece for production adoption. The tool must produce deterministic, machine-readable output that integrates into CI pipelines and persists results for comparison across commits.

#### C3.1: Per-Commit Testing Contract

Every `git commit` triggers a run that produces:

```bash
llm-browser-driver batch \
    --tests tests/e2e/regression-tests.json \
    --output ci-results/$(git rev-parse --short HEAD)/$(date -u +%Y%m%dT%H%M%S) \
    --model qwen3 \
    --llm-api "$LLM_API_URL" \
    --report-formats json,junit \
    --screenshot-dir ci-results/$(git rev-parse --short HEAD)/$(date -u +%Y%m%dT%H%M%S)/screenshots
```

**Output contract:**
- `report.json` — full structured result with action history, console errors, findings
- `report.xml` — JUnit XML for CI test result display
- `CI_STATUS` — exit code 0 = all passed, 1 = any failure (for CI gate)
- `manifest.json` — metadata: commit SHA, timestamp, model used, test count, pass/fail counts

#### C3.2: CI/CD Integration

**GitHub Actions workflow:**
```yaml
name: LLM Browser Tests
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  browser-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: pip install llm-browser-driver
      - run: |
          llm-browser-driver batch \
            --tests e2e/regression-tests.json \
            --output ci-results/ \
            --report-formats json,junit \
            --llm-api "${{ secrets.LLM_API_URL }}"
      - name: Upload test results
        uses: actions/upload-artifact@v4
        with:
          name: browser-test-results
          path: ci-results/
```

**CircleCI config:**
```yaml
version: 2.1
jobs:
  browser-test:
    docker:
      - image: cimg/python:3.12
    steps:
      - checkout
      - run: pip install llm-browser-driver playwright
      - run: |
          llm-browser-driver batch \
            --tests e2e/regression-tests.json \
            --report-formats junit
      - store_test_results:
          path: ci-results
```

#### C3.3: Results Storage & Comparison

**Storage backend (S3-compatible):**
- Upload `report.json`, `report.xml`, and screenshots to `s3://test-results-bucket/{project}/{commit-sha}/{timestamp}/`
- Maintain `s3://test-results-bucket/{project}/latest/` symlink to most recent run
- Track `s3://test-results-bucket/{project}/manifests/{commit-sha}.json` for diffing

**Diff capability:**
```python
from llm_browser_driver.diff import compare_runs

old = load_run("ci-results/old-commit/")
new = load_run("ci-results/new-commit/")

diff = compare_runs(old, new)
# → {
#     "regressions": [...],  # tests that failed in new but passed in old
#     "improvements": [...],  # tests that passed in new but failed in old
#     "new_findings": [...],  # findings in new run not in old
#     "confidence_score": 0.92  # 0-1, higher = more similar/safer
# }
```

**Commit message bot (future):** On PR merge, comment with:
> "✅ 12/12 browser tests passed. No regressions vs main. 2 new findings: form validation missing on signup, 404 on /api/v1/jobs."

### C4: Spec-Driven Testing — NEW

Given an API spec, automatically generate and run UI tests. This is what makes the tool valuable for integration testing, not just exploration.

#### C4.1: OpenAPI Spec Parser

Parse `openapi.yaml` to extract:
- Endpoints (paths + methods)
- Request body schemas (required fields, types, enums)
- Response schemas (for validation)
- Parameter documentation

#### C4.2: Endpoint-to-Page Mapping

```yaml
# driver-config.yaml
endpoint_mappings:
  POST /api/v1/jobs:
    page: /post-a-job
    description: "Create job form"
  POST /api/v1/auth/signin:
    page: /signin
    description: "Sign in form"
  POST /api/v1/auth/signup:
    page: /signup
    description: "Registration form"
  GET /api/v1/jobs:
    page: /jobs
    description: "Job listing page"
```

Users provide a mapping file (YAML or JSON) that connects API endpoints to frontend pages. The mapping is the user's responsibility — the tool doesn't auto-discover this.

#### C4.3: Spec-Driven Test Generation

For each endpoint, generate a test goal:
```
"Test that POST /api/v1/auth/signin creates a signin form with:
 email (required, type=email), password (required, type=password),
 and a Sign In button. Submit with valid credentials and verify
 redirect to /dashboard. Submit with invalid credentials and verify
 error message displayed."
```

The LLM explores the mapped page, validates form fields exist, submits with test data, and checks the response.

#### C4.4: Test Data Strategy

Use deterministic test data for CI, synthetic for exploration:
```yaml
test_data:
  POST /api/v1/auth/signin:
    email: "ci-test@example.com"
    password: "TestP@ss123!"
  POST /api/v1/jobs:
    title: "Test Job"
    location: "Remote"
```

### C5: Structured Logging & Observability — NEW

For debugging and auditing, every run produces structured logs.

#### C5.1: Structured JSON Logging

```python
import logging
import json

handler = logging.StreamHandler()
handler.setFormatter(
    logging.Formatter('%(message)s')  # json.dumps in the formatter
)
logger = logging.getLogger("llm_browser_driver")
logger.addHandler(handler)
```

Each log entry is a JSON object:
```json
{
  "ts": "2026-05-21T10:00:00.123Z",
  "level": "INFO",
  "event": "action_executed",
  "step": 5,
  "action": "click",
  "target": "#login-btn",
  "success": true,
  "duration_ms": 423,
  "url_after": "http://localhost:3000/dashboard"
}
```

#### C5.2: Tracing Support (OpenTelemetry)

Optional OTel integration for distributed tracing:
```python
from llm_browser_driver.tracing import setup_tracing

setup_tracing(service_name="llm-browser-driver")

# Every LLM call, action execution, and state extraction
# gets a span. Useful for:
# - Profiling which steps are slowest
# - Identifying LLM hallucination patterns
# - Cost tracking (tokens per run)
```

Span types:
- `llm_browser_driver.step` — full loop iteration
- `llm_browser_driver.state_extract` — DOM/a11y extraction
- `llm_browser_driver.llm_call` — chat completion request
- `llm_browser_driver.action` — Playwright action execution
- `llm_browser_driver.screenshot` — screenshot capture

### C6: Open-Source Ecosystem — NEW

For wide adoption, the project needs more than code — it needs documentation, examples, community tooling, and a clear contribution path.

#### C6.1: Documentation

- **README.md** — Quickstart (5-minute setup), install, first run, CLI reference
- **docs/usage/library-mode.md** — Python API examples
- **docs/usage/cli-reference.md** — Full CLI docs with flags and examples
- **docs/guides/exploratory-testing.md** — How to write good exploration goals
- **docs/guides/spec-driven-testing.md** — How to set up OpenAPI mapping
- **docs/guides/ci-cd-integration.md** — GitHub Actions, CircleCI examples
- **docs/troubleshooting.md** — Common errors, Qwen3 quirks, timeout tuning
- **docs/api/llm_browser_driver.md** — Auto-generated API docs (pdoc or mkdocstrings)
- **docs/CONTRIBUTING.md** — How to contribute, coding standards, PR process

#### C6.2: Example Repository

`examples/` directory with runnable examples:
```
examples/
├── explore_login.py            # Basic exploratory test
├── spec_driven.py              # OpenAPI-driven testing
├── ci_pipeline.py              # CI-integrated batch test
├── auth_with_storage.py        # Auth file loading
├── multi_page.py               # Multi-page exploration
└── custom_llm.py               # Custom LLM provider example
```

#### C6.3: Project Health

- **License:** MIT
- **CI:** GitHub Actions — lint, type check, tests, coverage report
- **Code coverage target:** ≥ 80%
- **Changelog:** Keep `CHANGELOG.md` with release notes
- **Issue templates:** Bug report, feature request, usage question
- **Discussion forum:** GitHub Discussions for Q&A

### C7: Advanced Agent Patterns — NEW (Borrowing from browser-use)

#### C7.1: LangChain Tool Calling (Borrow from browser-use)

browser-use uses LangChain's structured tool calling, which is more reliable than our regex-based JSON parser. Consider integrating:

```python
from langchain.tools import tool

@tool
def click(element: str) -> str:
    """Click an element by its identifier."""
    ...

@tool
def fill(field: str, value: str) -> str:
    """Fill a form field."""
    ...

# Instead of regex JSON parsing, use LangChain's tool output
# validation. This is more robust for complex LLMs.
```

**Decision:** Add as an *optional* dependency. Users who want tool calling can `pip install llm-browser-driver[langchain]`. Default stays with our lightweight JSON parser (zero non-core dependencies beyond OpenAI SDK + Playwright).

#### C7.2: LangGraph State Machine (Borrow from browser-use)

browser-use uses LangGraph for state management in the agent loop. This gives us:
- Explicit state nodes (capture_state → llm_decision → execute_action → check_done)
- Conditional edges (retry on failure, skip on success)
- Checkpointing (pause/resume mid-run)
- Human-in-the-loop (approve risky actions)

```python
from langgraph.graph import StateGraph, END

class AgentState(TypedDict):
    step: int
    action_history: list
    page_state: dict
    console_errors: list
    findings: list

workflow = StateGraph(AgentState)
workflow.add_node("capture", capture_state)
workflow.add_node("reason", llm_reason)
workflow.add_node("act", execute_action)
workflow.add_conditional_edges("act", should_continue, {"continue": "capture", "end": END})
```

**Decision:** Defer to a later milestone. The current simple loop works. LangGraph adds complexity but gives checkpointing and human-in-the-loop. Evaluate after spec-driven testing is working.

#### C7.3: Retry & Recovery Patterns (Steal from browser-use)

browser-use has a retry mechanism when actions fail:
- If an action fails, retry up to N times with different selection strategies
- If all retries fail, log the failure and continue to next step
- Track retry counts for confidence scoring

```python
def execute_with_retry(self, action, max_retries=3):
    for attempt in range(max_retries):
        success, result = self.execute_action(action)
        if success:
            return True, result
        # On failure: try alternative selector, wait, then retry
        self._fallback_selector(action, attempt)
        time.sleep(0.5 * (attempt + 1))  # exponential backoff
    return False, f"Failed after {max_retries} retries"
```

### C8: Parallel Execution — NEW

For CI speed, run multiple test goals concurrently.

```python
from llm_browser_driver.parallel import run_parallel

results = run_parallel(
    tests=[
        {"url": "...", "goal": "Test login"},
        {"url": "...", "goal": "Test registration"},
        {"url": "...", "goal": "Test password reset"},
    ],
    max_concurrent=3,  # limited to avoid overloading LLM API
    browser_per_worker=True,  # each worker gets its own browser
)
```

**Trade-off:** Concurrent Playwright browsers consume memory. Default max_concurrent=3 is safe for CI runners with 2GB RAM.

---

## 4. Architecture

### Updated Module Structure

```
llm-browser-driver/
├── src/
│   └── llm_browser_driver/
│       ├── __init__.py          # Public API: BrowserDriver, run_driver()
│       ├── agent.py             # Core interaction loop (loop driver + TestResult)
│       ├── selector.py          # Anti-fragile element matching
│       ├── actions.py           # Action executor (click, fill, etc.)
│       ├── state.py             # Page state extraction
│       ├── llm_client.py        # LLM abstraction (OpenAI SDK)
│       ├── report.py            # Report generators + dashboard
│       ├── diff.py              # Compare two runs (new)
│       ├── logging.py           # Structured JSON logging (new)
│       └── parallel.py          # Concurrent execution (new)
│       └── spec_parser.py       # OpenAPI spec parser (future)
│       └── tracing.py           # OpenTelemetry integration (future)
│
├── tests/
│   ├── unit/                    # Unit tests (128 passing)
│   ├── integration/             # Integration tests (mock server) (new)
│   └── fixtures/                # Sample HTML pages, OpenAPI specs (new)
│
├── examples/                    # Runnable examples (new)
├── pyproject.toml               # Package metadata, dependencies
├── README.md                    # User documentation
├── CONTRIBUTING.md              # Contributing guide
├── CHANGELOG.md                 # Release notes (new)
├── LICENSE                      # MIT license (new)
└── docs/
    ├── PRD.md                   # This document
    ├── usage/
    │   ├── library-mode.md      # Python API
    │   ├── cli-reference.md     # CLI docs
    │   ├── exploratory-testing.md
    │   ├── spec-driven-testing.md
    │   ├── ci-cd-integration.md
    │   └── troubleshooting.md
    ├── api/                     # Auto-generated API docs
    └── guides/
        └── ...
```

### CI/CD Pipeline Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  git push to main / PR                                       │
│                              │                               │
│                              ▼                               │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐   │
│  │ Lint + Type  │    │ Unit Tests   │    │ E2E Tests    │   │
│  │ (ruff, mypy) │    │ (pytest)     │    │ (Playwright) │   │
│  └──────────────┘    └──────────────┘    └──────┬───────┘   │
│                                                 │           │
│                            ┌────────────────────┘           │
│                            ▼                                │
│                  ┌─────────────────┐                        │
│                  │ LLM Browser Run │                        │
│                  │ batch tests     │                        │
│                  └────────┬────────┘                        │
│                           │                                 │
│              ┌────────────┼────────────┐                   │
│              ▼            ▼            ▼                   │
│        report.json   report.xml   screenshots/             │
│              │            │            │                   │
│              └────────────┼────────────┘                   │
│                           ▼                                │
│              ┌─────────────────────┐                       │
│              │ Upload to S3        │                       │
│              │ ci-results-bucket/  │                       │
│              └─────────────────────┘                       │
│                           │                                │
│              ┌────────────┼────────────┐                   │
│              ▼            ▼            ▼                   │
│        GitHub PR    Diff Report    Slack Alert             │
│        comment    on regression    on failure              │
└─────────────────────────────────────────────────────────────┘
```

---

## 5. Configuration System

### Environment Variables

```bash
# Required
LLM_BROWSER_DRIVER__LLM_API_URL=http://localhost:8000/v1
LLM_BROWSER_DRIVER__LLM_MODEL=qwen3

# Optional
LLM_BROWSER_DRIVER__MAX_TOKENS=2048
LLM_BROWSER_DRIVER__TEMPERATURE=0.3
LLM_BROWSER_DRIVER__MAX_ITERATIONS=30
LLM_BROWSER_DRIVER__TIMEOUT=300
LLM_BROWSER_DRIVER__STREAMING=false
LLM_BROWSER_DRIVER__HEADLESS=true
LLM_BROWSER_DRIVER__SCREENSHOT_INTERVAL=5
LLM_BROWSER_DRIVER__SCREENSHOT_ON_FAILURE=true
LLM_BROWSER_DRIVER__OUTPUT_DIR=results/
LLM_BROWSER_DRIVER__LOG_LEVEL=info  # debug | info | warning | error
```

### YAML Configuration

```yaml
# driver-config.yaml
llm:
  api_url: http://localhost:8000/v1
  model: qwen3
  max_tokens: 2048
  temperature: 0.3
  timeout: 300
  streaming: false
  # Optional: structured logging
  structured_log: true
  # Optional: OpenTelemetry tracing
  tracing:
    enabled: false
    service_name: llm-browser-driver
    endpoint: http://otel-collector:4318

browser:
  headless: true
  viewport:
    width: 1280
    height: 720
  timeout: 30000

agent:
  max_iterations: 30
  max_failures: 3
  retry_attempts: 3
  system_prompt: |
    You are an exploratory QA tester. Your goal is to find bugs.

report:
  formats:
    - json
    - markdown
    - html
    - junit
  output_dir: ./results
  include_screenshots: true

logging:
  level: info
  format: json
  output: stdout  # stdout | file | both
  file: logs/llm-browser-driver.log

parallel:
  max_concurrent: 3
  browser_per_worker: true
```

---

## 6. Milestones

### M0: Core + Reporting — ✅ DONE

What's been built and tested:
- [x] `llm_browser_driver/` module with 6 core modules (agent, selector, actions, state, llm_client, report)
- [x] Anti-fragile element matching (id → text → aria-label → label)
- [x] 8 action types + LLM loop driver
- [x] Screenshot capture (interval + on-failure)
- [x] Report generators (JSON, Markdown, HTML, JUnit XML)
- [x] HTML report with screenshot thumbnail column + CSS
- [x] Run versioning (`run-{timestamp}/` hierarchy)
- [x] Dashboard (`results/index.html`) listing all runs
- [x] `serve` command (local HTTP server with auto-open)
- [x] CLI (explore/batch/serve subcommands)
- [x] 128 unit tests, all passing
- [x] `pip install` support (pyproject.toml)

### M3: Spec-Driven Testing — NEXT

- [ ] OpenAPI spec parser (YAML → endpoint list + field schemas)
- [ ] Endpoint-to-page mapping (YAML config: `POST /api/v1/jobs: /post-a-job`)
- [ ] Test goal generation from spec (auto-generate exploration goals)
- [ ] Spec-driven test runner (`llm-browser-driver spec --spec openapi.yaml`)
- [ ] Report with endpoint-level pass/fail summary
- [ ] Integration tests against sample OpenAPI spec

**Success criteria:** Given an OpenAPI spec + frontend URL, produces a full report with per-endpoint pass/fail status.

### M4: CI/CD Integration — NEXT

- [ ] `manifest.json` generation (commit SHA, timestamp, model, stats)
- [ ] S3 upload utility (`upload_results_to_s3(...)`)
- [ ] Run diff tool (`llm_browser_driver.diff.compare_runs(old, new)`)
- [ ] GitHub Actions workflow example
- [ ] CircleCI config example
- [ ] Per-commit contract documentation
- [ ] Regression detection alerts

**Success criteria:** Running `llm-browser-driver batch --output ci-results/` produces uploadable, comparable artifacts that integrate into CI pipelines.

### M5: Observability & Advanced Patterns — FUTURE

- [ ] Structured JSON logging (`llm_browser_driver.logging`)
- [ ] OpenTelemetry tracing integration (`llm_browser_driver.tracing`)
- [ ] LangChain tool calling (optional `pip install llm-browser-driver[langchain]`)
- [ ] LangGraph state machine (deferred — evaluate after M3)
- [ ] Retry & recovery patterns (fallback selectors, exponential backoff)
- [ ] Parallel execution engine (`llm_browser_driver.parallel`)

### M6: Open-Source Readiness — OVERLAPPING WITH M3-M4

- [ ] README.md with quickstart, install, first run
- [ ] `examples/` directory with 5 runnable examples
- [ ] `docs/usage/` documentation (library, CLI, CI/CD)
- [ ] `CONTRIBUTING.md` — coding standards, PR process
- [ ] `CHANGELOG.md` — release notes
- [ ] MIT license
- [ ] GitHub issue templates (bug, feature, question)
- [ ] GitHub Discussions setup
- [ ] Pre-commit hooks (ruff + mypy)

---

## 7. Non-Functional Requirements

### Performance

| Metric | Target | Notes |
|--------|--------|-------|
| LLM call latency | < 30s (configurable timeout) | Per iteration |
| State extraction | < 2s per page | DOM + a11y tree |
| Screenshot capture | < 2s per screenshot | Full page |
| Memory per browser | < 500MB | Headless Chromium |
| Memory for parallel (3 workers) | < 1.5GB | 3 browser instances |
| Report generation | < 1s | For runs up to 500 steps |

### Compatibility

- Python 3.12+
- Playwright 1.40+
- Any OpenAI-compatible LLM endpoint (`/v1/chat/completions`)
- Linux, macOS, Windows (headless Chrome)
- CI runners: GitHub Actions (Ubuntu), CircleCI, GitLab CI, Jenkins

### Quality

- Unit test coverage: ≥ 80% on `llm_browser_driver/`
- Current: 128 unit tests, all passing
- Integration tests: one per action type, against mock HTML pages
- Regression test suite: reusable HTML fixtures that test selector matching

### Security

- LLM API key: env vars or config file only (never hardcoded)
- No automatic data exfiltration (LLM calls go to configured endpoint only)
- No persistent storage without explicit opt-in
- Screenshots: user-controlled directory, never uploaded without consent

### Reliability

- Retry on transient LLM errors (429, 503) — configurable max retries
- Graceful degradation: if action fails, log and continue (don't abort)
- Timeout handling: each action and LLM call has configurable timeout
- Browser crashes: Playwright auto-restart on connection loss

---

## 8. Success Metrics

| Metric | Target | How Measured |
|--------|--------|-------------|
| Selector match success rate | ≥ 95% | % of actions that find their target element |
| Action execution success rate | ≥ 90% | % of actions that complete without error |
| Spec test coverage | ≥ 90% | % of OpenAPI endpoints with matching UI pages |
| Time to first action | < 10s | Wall clock from start to first action result |
| Memory usage | < 500MB per browser | RSS during typical session |
| CI integration time | < 30 min | Time to set up GitHub Actions pipeline |
| Test reliability | ≥ 85% pass rate | % of runs that complete without LLM timeout |
| Screenshot capture rate | ≥ 98% | % of scheduled screenshots that succeed |

---

## 9. Comparison: What We Borrow from browser-use

| Feature | browser-use | Our Approach | Decision |
|---------|------------|--------------|----------|
| **Output parsing** | LangChain tool calling | JSON regex parser | Keep JSON parser for now; add LangChain as optional |
| **Retry logic** | Built-in retry with fallback selectors | None yet | Implement in M5 |
| **State management** | LangGraph state machine | Simple loop | Defer to M5; current loop works |
| **Parallel execution** | Multi-agent (LangGraph) | Simple concurrency | Implement in M5 |
| **Documentation** | Excellent docs, examples | None yet | Implement in M6 |
| **CI/CD** | Not the focus | Primary focus | Our differentiator |
| **Reporting** | None | Rich HTML + dashboard + serve | Our differentiator |
| **Screenshot capture** | Not built-in | Built-in with intervals | Keep as-is |
| **Run versioning** | None | run-{timestamp}/ hierarchy | Keep as-is |

**Key insight:** browser-use is a great reference for agent patterns but is not a testing product. They focus on "AI that can browse the web" — not "AI that helps you test your web app." Our lane is **production-ready testing with CI/CD integration, rich reporting, and per-commit confidence.** We borrow their reliability patterns (retry, fallback) but keep our testing-first focus.

---

## 10. Open Questions

1. **LangChain dependency level:** Should tool calling be a hard dependency or optional? Decision: optional (`pip install llm-browser-driver[langchain]`). Core stays dependency-light.

2. **LangGraph timing:** Evaluate after spec-driven testing works. The simple loop is working fine. LangGraph adds checkpointing and human-in-the-loop value but also complexity.

3. **Spec parser scope:** Full OpenAPI 3.x support or subset? Decision: subset first (paths + POST/PUT request bodies). Full support if users ask for GET/DELETE testing.

4. **Screenshot storage in reports:** Embed base64 screenshots in JSON or reference external files? Decision: reference external files (keep report.json small). Screenshots in separate directory.

5. **Multi-browser support:** Chromium only or Firefox/WebKit too? Decision: Chromium only for now (headless is most reliable). Add Firefox/WebKit later if users request it.

6. **License:** MIT. Compatible with Playwright's Apache 2.0. Clear and permissive for commercial use.

---

## 11. Appendix: What "Done" Looks Like

### M3 Done (Spec-Driven Testing)
- [ ] `llm-browser-driver spec --spec openapi.yaml --url http://staging` produces a report
- [ ] Report has per-endpoint pass/fail with evidence (screenshots, console errors)
- [ ] 10 integration tests for spec parser + field mapping
- [ ] Documentation: how to write endpoint mappings

### M4 Done (CI/CD)
- [ ] `llm-browser-driver batch` produces `manifest.json` + `report.json` + `report.xml`
- [ ] Results uploadable to S3 with `upload_results()` utility
- [ ] `compare_runs()` detects regressions between commits
- [ ] GitHub Actions + CircleCI examples in repo
- [ ] Documentation: CI/CD integration guide

### M6 Done (Open-Source)
- [ ] `pip install llm-browser-driver` works
- [ ] README: install, first run, CLI reference
- [ ] 5 runnable examples in `examples/`
- [ ] Docs in `docs/usage/`
- [ ] `CONTRIBUTING.md`, `CHANGELOG.md`, MIT license
- [ ] GitHub issue templates, Discussions enabled
- [ ] Pre-commit hooks (ruff + mypy) pass
- [ ] 128+ tests passing, ≥ 80% coverage

# LLM Browser Driver — Product Requirements Document

**Status:** Initial Draft  
**Created:** 2026-05-21  
**Source:** `spikes/browser-use-augment/` in Hauliage repo (2026-04 to 2026-05)

---

## Executive Summary

LLM Browser Driver is a standalone, open-source Python library that enables autonomous AI-driven web testing and exploration. It combines Playwright's browser automation with an LLM's ability to understand and navigate pages without hardcoded selectors.

**Key differentiator:** Zero selector maintenance. The LLM discovers elements the way a human does — by labels, text content, and structure — so UI refactors don't break tests.

---

## Problem Statement

Static E2E test suites face three fundamental problems:

1. **Selector brittleness** — DOM changes (class name swaps, ID rewrites, component restructuring) break test selectors. Teams spend more time fixing tests than finding bugs.
2. **Exponential growth** — Every new feature, state, or edge case multiplies the number of test scenarios to maintain.
3. **Missing exploratory depth** — Deterministic tests validate known paths. They don't discover unknown bugs like broken navigation, unexpected state transitions, or missing error states.

Manual exploratory testing solves (3) but doesn't scale. LLM Browser Driver brings human-level exploration into an automated, repeatable, scriptable pipeline.

---

## Product Capabilities

### C1: Autonomous Interactive Testing (Core)

An LLM drives a Playwright browser session in a closed loop:

1. **State capture** — Extract comprehensive page state (elements, text, forms, accessibility tree, console errors)
2. **LLM reasoning** — Given page state + goal + action history, the LLM decides the next action
3. **Action execution** — Driver executes the action (click, fill, select, navigate, scroll, evaluate, wait)
4. **State comparison** — Capture new state, detect changes from previous step
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

### C2: Spec-Driven Testing

Given an OpenAPI spec or feature description, the driver:

1. Parses the spec to identify endpoints and required fields
2. Maps endpoints to frontend pages (via URL patterns or manual config)
3. Identifies which form fields each endpoint populates
4. Runs interactive tests to validate each endpoint's UI implementation

**Input:** `openapi.yaml` + `--url <frontend>`  
**Output:** Test report with pass/fail per endpoint

**Configurable mapping:**

```yaml
# driver-config.yaml
endpoint_mappings:
  "/api/v1/jobs": /post-a-job
  "/api/v1/auth/signin": /signin
  "/api/v1/auth/signup": /signup

field_mappings:
  /post-a-job:
    "create_job_request.pickup_country": country
    "create_job_request.delivery_country": delivery
```

### C3: Library Mode

Importable Python API for programmatic control:

```python
from llm_browser_driver import BrowserDriver

driver = BrowserDriver(
    llm_api_url="http://vllm:8000/v1",
    llm_model="qwen3",
    max_tokens=2048,
    temperature=0.3,
    timeout=300,
)

# Run a single exploration
result = driver.explore(
    url="http://myapp.com",
    goal="Validate the checkout flow end-to-end",
    max_iterations=30,
)

# Run multiple explorers in parallel (async)
results = await driver.explore_batch([
    {"url": ..., "goal": "..."},
    {"url": ..., "goal": "..."},
])

# Run spec-driven testing
results = await driver.test_openapi(
    spec_path="./openapi.yaml",
    base_url="http://staging.myapp.com",
)
```

**Output** from any method is a structured result dict with:

```python
{
    "status": "success",  # or "error"
    "iterations": 23,
    "action_history": [
        {
            "step": 1,
            "action": "click",
            "parameters": {"element": "Sign In"},
            "result": "Clicked button: Sign In",
            "url": "http://myapp.com/signin",
            "time_taken": 0.42,
        },
        # ...
    ],
    "console_errors": [
        {"type": "error", "text": "Failed to load resource..."}
    ],
    "final_url": "http://myapp.com/dashboard",
    "findings": [
        {
            "type": "bug",
            "severity": "high",
            "description": "Password field is visible in plaintext on signin page",
        },
    ],
}
```

### C4: CLI Interface

Command-line tool for spec-driven and exploratory testing without code:

```bash
# Exploratory test
llm-browser-driver explore \
    --url http://localhost:3000 \
    --goal "Test the user registration flow" \
    --max-iterations 30 \
    --model qwen3 \
    --llm-api http://localhost:8000/v1

# Spec-driven test
llm-browser-driver spec \
    --spec openapi.yaml \
    --url http://staging.myapp.com \
    --output results.json \
    --model claude-sonnet-4

# Run from environment config
llm-browser-driver explore \
    --url http://localhost:3000 \
    --env staging.yaml
```

### C5: LLM Abstraction Layer

Support for any OpenAI-compatible LLM endpoint:

- OpenAI (gpt-4, gpt-4o)
- OpenRouter
- vLLM, TGI, Ollama, LM Studio
- Azure OpenAI
- Any endpoint implementing `/v1/chat/completions`

**Configuration:**

```yaml
llm:
  api_url: http://localhost:8000/v1
  model: qwen3
  max_tokens: 2048
  temperature: 0.3
  timeout: 300
  # Optional: streaming disabled (required for Qwen3 on vLLM per spike findings)
  streaming: false
```

### C6: Auth Integration

Playwright storage-shipper for authenticated sessions:

```python
result = driver.explore(
    url="http://myapp.com/dashboard",
    goal="Validate dashboard widgets",
    auth_file="storage-shipper.json",  # Playwright browser.context.storage_state()
)
```

### C7: Test Report Generation

Structured output in multiple formats:

- **JSON** — machine-readable, machine-parsable
- **Markdown** — human-readable test report
- **Gherkin** — BDD feature files generated from exploration findings (future)
- **JUnit XML** — CI/CD integration (future)

---

## Architecture

### Component Diagram

```
┌─────────────────────────────────────────────┐
│  LLM Browser Driver                        │
├─────────────────────────────────────────────┤
│                                             │
│  ┌──────────┐   ┌──────────┐   ┌─────────┐ │
│  │   CLI    │   │ Library  │   │  Config │ │
│  │  (click) │   │  (API)   │   │  YAML   │ │
│  └────┬─────┘   └────┬─────┘   └────┬────┘ │
│       │              │              │       │
│       └──────────────┼──────────────┘       │
│                      │                       │
│              ┌───────▼────────┐              │
│              │  Agent Engine  │              │
│              │                │              │
│              │  ┌──────────┐  │              │
│              │  │  Loop    │  │              │
│              │  │  Driver  │  │              │
│              │  └──────────┘  │              │
│              │  ┌──────────┐  │              │
│              │  │ Selector │  │              │
│              │  │ Fuzzing  │  │              │
│              │  └──────────┘  │              │
│              │  ┌──────────┐  │              │
│              │  │ Action   │  │              │
│              │  │ Executor │  │              │
│              │  └──────────┘  │              │
│              └────────────────┘              │
│                      │                       │
│              ┌───────▼────────┐              │
│              │  State         │              │
│              │  Extractor     │              │
│              │                │              │
│              │  • DOM details │              │
│              │  • A11y tree   │              │
│              │  • Console log │              │
│              │  • HTML snippet│              │
│              └────────────────┘              │
│                                              │
│              ┌───────▼────────┐              │
│              │  Report        │              │
│              │  Generator     │              │
│              │  (JSON/MD/Gherkin)             │
│              └────────────────┘              │
├─────────────────────────────────────────────┤
│  Playwright (browser automation)             │
│  OpenAI SDK (LLM client abstraction)         │
└─────────────────────────────────────────────┘
         │                    │
    ┌────▼────┐          ┌───▼───┐
    │ Browser │          │  LLM  │
    │(headless)│         │endpoint│
    └─────────┘          └───────┘
```

### Module Structure

```
llm-browser-driver/
├── src/
│   ├── llm_browser_driver/
│   │   ├── __init__.py          # Public API: BrowserDriver class
│   │   ├── agent.py             # Core interaction loop (the "loop driver")
│   │   ├── selector.py          # Action-to-element matching (fuzzy lookup)
│   │   ├── actions.py           # Action executor (click, fill, navigate, etc.)
│   │   ├── state.py             # Page state extraction
│   │   ├── llm_client.py        # LLM abstraction layer
│   │   ├── report.py            # Test report generation
│   │   ├── spec_parser.py       # OpenAPI spec parser
│   │   └── auth.py              # Auth session management
│   │
│   └── cli.py                   # CLI entry point (click)
│
├── tests/
│   ├── unit/                    # Unit tests for each module
│   ├── integration/             # Integration tests against mock server
│   └── fixtures/                # Sample OpenAPI specs, test pages
│
├── config/
│   ├── default.yaml             # Default configuration
│   └── models.yaml              # Model presets (qwen3, claude, gpt, etc.)
│
├── examples/
│   ├── explore.py               # Library mode example
│   ├── spec_test.py             # Spec-driven example
│   └── parallel.py              # Parallel exploration example
│
├── pyproject.toml               # Package metadata, dependencies
├── README.md                    # User documentation
├── CONTRIBUTING.md              # Contributing guide
└── LICENSE
```

### Module Responsibilities

**`agent.py`** — The core loop driver. Maintains:
- Action history
- State snapshots
- LLM conversation context (system prompt + message history)
- Iteration counter and timeout

**`selector.py`** — Action-to-element matching. Implements:
- Click selection: ID → button text → link href → fuzzy text
- Fill selection: name → placeholder → ID → aria-label → label[for] text
- Select selection: field name → option text
- Confidence scoring: each selection strategy returns a confidence score
- Fallback chain: tries each strategy in order, first match wins

**`actions.py`** — Action executor. Each action type has an async method:
- `click(locator)`, `fill(locator, value)`, `select(locator, option)`
- `navigate(url)`, `scroll(direction, distance)`
- `wait(condition)`, `go_back()`, `evaluate(script)`

**`state.py`** — Page state extraction. Returns a structured dict:
- Input details (type, name, placeholder, value, disabled, readonly)
- Button/link details (text, href, aria-label, disabled)
- Select options (text, value, selected)
- Form field labels (for → text mapping)
- Accessibility tree (role, name, expanded, disabled per node)
- Console errors/warnings (type, text, timestamp)
- HTML snippet (top 2KB of body)
- Viewport dimensions

**`llm_client.py`** — LLM abstraction. Wraps OpenAI SDK:
- Configurable `base_url`, `model`, `max_tokens`, `temperature`, `timeout`
- Streaming toggle (default: `False` — per spike findings with Qwen3)
- Automatic retry on timeout and rate limits
- Token usage tracking
- Supports any `/v1/chat/completions` endpoint

**`report.py`** — Test report generation:
- JSON output (structured findings, action history, console errors)
- Markdown output (human-readable summary table)
- Extensible: add Gherkin and JUnit XML generators

**`spec_parser.py`** — OpenAPI spec analyzer:
- Extracts POST/PUT endpoints with request bodies
- Maps request body fields to form fields on pages
- Generates test tasks from endpoint specs

---

## Configuration System

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

browser:
  headless: true
  viewport:
    width: 1280
    height: 720
  timeout: 30000

agent:
  max_iterations: 30
  max_actions_per_step: 5
  max_failures: 3
  system_prompt: |
    You are an exploratory QA tester. Your goal is to find bugs.

report:
  format: json  # json | markdown | all
  output_dir: ./reports
```

---

## Spike-to-Product Migration

### What moves as-is (after parameterization)

| Spike Code | Product Module | Changes Needed |
|-----------|---------------|----------------|
| `09_interactive_exploration.py` — LLM loop | `agent.py` | Extract constants to config, parameterize URLs |
| `09_interactive_exploration.py` — element extraction | `state.py` | Parameterize selectors, add timeout config |
| `09_interactive_exploration.py` — action executor | `actions.py` | Parameterize URLs, add auth support |
| `09_interactive_exploration.py` — selector matching | `selector.py` | Extract all matching logic into dedicated module |
| `09_interactive_exploration.py` — LLM call + parsing | `llm_client.py` | Abstract client, add retry, streaming toggle |
| `09_interactive_exploration.py` — JSON parser | `llm_client.py` | Keep as utility inside client |
| `09_interactive_exploration.py` — results output | `report.py` | Generalize from Hauliage-specific to generic |
| `08_sync_hybrid.py` — early state extraction | `state.py` | Merge with 09's state extraction (09 is superset) |
| SPIKE_NOTES.md | `docs/spike-findings.md` | Document known issues, Qwen3 quirks |

### What gets added (new for product)

| New Feature | Purpose |
|------------|---------|
| Config layer (YAML + env vars + defaults) | No hardcoded values |
| CLI (click) | Command-line interface |
| Library API (`BrowserDriver` class) | Programmatic access |
| OpenAPI spec parser | Spec-driven testing |
| Auth integration | Authenticated session loading |
| Report generators (JSON, Markdown) | Multiple output formats |
| Test framework (pytest) | Unit + integration tests |
| Example pages (mock HTML) | Testing without live app |
| Package distribution (pyproject.toml) | `pip install` support |

### What gets removed

| Removed | Reason |
|---------|--------|
| Hauliage-specific URLs | Config-driven |
| Hauliage-specific form field names | Generic matching |
| Hauliage-specific OpenAPI paths | Spec parser handles mapping |
| Spike iteration scripts (01–07) | Superseded by 09, kept as historical reference in `legacy/` |
| `.venv/` directory | Not committed |
| `progress_*.txt` files | Generated artifacts, not source |
| `exploratory_results_*.json` | Generated artifacts, not source |

---

## Milestones

### M1: Core Library (Week 1-2)

Extract and parameterize `09_interactive_exploration.py` into the module structure:

- [ ] `llm_browser_driver/__init__.py` — `BrowserDriver` class with `explore()` method
- [ ] `llm_browser_driver/agent.py` — loop driver, extracted from 09
- [ ] `llm_browser_driver/selector.py` — matching logic from 09
- [ ] `llm_browser_driver/actions.py` — action executor from 09
- [ ] `llm_browser_driver/state.py` — state extraction from 09
- [ ] `llm_browser_driver/llm_client.py` — LLM client from 09 (configurable, retry, streaming toggle)
- [ ] Config layer (YAML + env vars)
- [ ] Package structure (`pyproject.toml`)
- [ ] Basic tests against mock server
- [ ] README with quickstart

**Success criteria:** Can import `BrowserDriver`, pass it a URL and goal, get back a structured result dict. Works with any OpenAI-compatible LLM.

### M2: CLI + Reports (Week 3)

- [ ] CLI (`click`) with `explore` and `spec` subcommands
- [ ] Report generators (JSON, Markdown)
- [ ] Auth integration (storage-shipper)
- [ ] Configuration presets (`--model claude`, `--model qwen3`)
- [ ] Integration tests against Playwright's `playwright-test` fixtures

**Success criteria:** `llm-browser-driver explore --url http://localhost:3000 --goal "test login"` works end-to-end.

### M3: Spec-Driven Testing (Week 4-5)

- [ ] OpenAPI spec parser
- [ ] Endpoint-to-page mapping logic
- [ ] Field mapping configuration
- [ ] Spec-driven test runner
- [ ] Test report with endpoint-level pass/fail

**Success criteria:** `llm-browser-driver spec --spec openapi.yaml --url http://staging` produces a full test report.

### M4: Advanced Features (Week 6-8)

- [ ] Parallel exploration (`explore_batch`)
- [ ] BDD output (Gherkin generation from findings)
- [ ] JUnit XML export for CI
- [ ] CI/CD integration example (GitHub Actions workflow)
- [ ] Documentation site (MkDocs or similar)
- [ ] Example pages for offline testing
- [ ] Comprehensive integration tests

---

## Non-Functional Requirements

### Performance

- Each LLM call: < 30s (configurable timeout)
- State extraction: < 2s per page
- Memory: < 500MB for typical sessions (headless browser + LLM client)

### Compatibility

- Python 3.10+
- Playwright 1.40+
- Any OpenAI-compatible LLM endpoint
- Linux, macOS, Windows (headless Chrome)

### Quality

- ≥ 80% unit test coverage on `llm_browser_driver/`
- Integration tests for each action type
- Regression test suite using mock HTML pages

### Security

- LLM API key stored in env vars or config file only (never hardcoded)
- No automatic data exfiltration (LLM calls go to configured endpoint only)
- No persistent storage without explicit opt-in

---

## Known Issues from Spike (to be addressed in M1)

1. **Qwen3 streaming bug** — All output routes to `reasoning` field, `content` is empty. Must use `stream=False`. (Documented in config.)
2. **Empty field matching** — When frontend inputs lack `aria-label` or proper `name`/`placeholder`, LLM can't find fields. (Workaround: document that accessible HTML is required; add `data-testid` as a fallback selection strategy.)
3. **LLM timeout** — vLLM can take 37s+ for complex pages, causing timeouts. (Addressed by configurable timeout.)
4. **Adaptive guessing** — LLM sometimes tries wrong field names before guessing correctly, wasting iterations. (Could add a prompt optimization to prioritize exact matches over fuzzy ones.)

---

## Success Metrics

| Metric | Target | How Measured |
|--------|--------|-------------|
| Selector match success rate | ≥ 95% | % of actions that find their target element |
| Action execution success rate | ≥ 90% | % of actions that complete without error |
| Spec test coverage | ≥ 90% | % of OpenAPI endpoints with matching UI pages |
| Time to first result | < 10s (first LLM call) | Wall clock from start to first action result |
| Memory usage | < 500MB | RSS during typical session |

---

## Open Questions

1. **Should we wrap `playwright-core` or `playwright`?** `playwright-core` is lighter (no bundled browsers) but requires separate browser install. `playwright` bundles Chromium. For a testing tool, `playwright` is simpler for users.

2. **Should we support multiple LLM calls per loop iteration?** Currently one LLM call → one action. Could batch (e.g., "explore this section" → 5 actions in one call) for speed. Trade-off: harder to reason about failures.

3. **Should spec-driven testing be a separate module or part of core?** For M1, spec-driven is optional. M3 makes it required. Keep it as an optional plugin-style import to avoid forcing users who only want exploratory testing to install OpenAPI parsers.

4. **Async vs sync?** Spike uses sync API (`sync_playwright`). This is simpler for users. Async (`async_playwright`) is needed for `explore_batch` (M4). Support both: sync wrapper around async core.

5. **License?** MIT is the default for open-source Python tools. Aligns with Playwright's Apache 2.0 (compatible).

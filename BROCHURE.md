# LLM Browser Driver

## Autonomous AI Testing for Modern Web Applications

---

### The Problem

Static test suites and manual QA can't keep up. Your frontend changes
faster than your test writers can update selectors. Playwright scripts
break on the slightest DOM shift. E2E suites are expensive to maintain
and brittle to refactoring. Exploratory testing scales with hiring, not
CI minutes.

**And your users don't care about your test coverage.**
They care if the "Submit" button works on Tuesday.

---

### The Solution

**LLM Browser Driver** is an autonomous testing engine that combines the
reliability of Playwright with the adaptability of a human QA engineer.

```
+--- Playwright drives the browser ---+
|   LLM sees the page, decides what to |
|   do next, and the cycle repeats.    |
|                                      |
|   No brittle selectors. No hardcoded |
|   step definitions. No test rot.     |
+--------------------------------------+
```

---

### How It Works

Three modes, one engine.

**1. SPEC-DRIVEN AUTONOMOUS TESTING**

Point it at your OpenAPI spec or feature docs. The LLM reads the
contract, navigates to the relevant pages, fills real forms, clicks
through workflows, and validates behavior end-to-end.

> **Input:** `openapi.yaml` + URL
> **Output:** Structured test report with pass/fail per endpoint

**2. EXPLORATORY AUTONOMOUS TESTING**

Give the LLM a goal and a URL. It explores the page like a human QA
engineer: clicks links, fills forms, tries edge cases, discovers
broken states, captures console errors, and reports what it found.

> **Input:** `goal` + `URL`
> **Output:** Exploration log with discovered issues

**3. LIBRARY MODE**

Import the driver, pass it your Playwright page object, and let the
LLM drive interactions programmatically:

```python
from llm_browser_driver import AutonomousDriver

driver = AutonomousDriver(
    page=my_page,
    model="qwen3",
    llm_api="http://vllm:8000/v1",
)
result = driver.explore(
    goal="Test the job posting wizard",
    max_iterations=50,
)
```

---

### Capabilities

| Action    | Selection Strategy                                      |
|-----------|---------------------------------------------------------|
| Click     | ID match → button text → link href → fuzzy fallback     |
| Fill      | Name, placeholder, id, aria-label, label[for] match     |
| Select    | Dropdown options by text                                |
| Navigate  | Full URL navigation with state waiting                  |
| Evaluate  | Arbitrary JavaScript (with `console.log` auto-rewriting) |
| Scroll    | Partial and full, up and down                           |
| Wait      | `networkidle`, `load`, or custom timeout                |
| History   | `go_back`, `go_forward`                                 |

Every action is recorded. Every page state is captured:

- Form fields (type, name, placeholder, value, disabled state)
- Buttons and links (text, href, disabled)
- Selects with options
- Accessibility tree snapshot
- Console errors/warnings during navigation
- HTML snippet for DOM structure

---

### Why It Matters

**92%** action success rate on real-world multi-step forms
(verified against Hauliage, a 6-page SolidJS app)

- **Zero selector maintenance** — the LLM understands the page
  the same way a human does: labels, placeholders, text content.

- **Catches what static tests miss:**
  - Broken click handlers
  - Form validation edge cases
  - Navigation failures
  - Unexpected state transitions
  - Missing error states
  - Accessibility gaps

- **Scales infinitely** — spin up 50 parallel explorers, give each
  a different goal, get 50 reports. No flaky test flakiness.

---

### Technical Details

- **Driver:** Python, Playwright (sync API)
- **LLM:** OpenAI-compatible API (any model, any backend)
- **Action:** JSON from LLM, fuzzy-matched to DOM
- **Output:** Structured JSON report (action history, state changes,
  discovered issues, console errors)
- **Auth:** Playwright storage-shipper (load authenticated session
  from JSON, test protected routes)

---

### Use Cases

**CI/CD Pre-flight**

Run exploratory tests before BDD suites to catch regressions early.

**Spec Compliance**

Validate OpenAPI contracts against running UI in staging.

**Release Validation**

Autonomous smoke test of critical user journeys (signup, checkout,
job posting).

**Regression Discovery**

Run weekly explorers against production to catch silent UI rot.

**Accessibility QA**

Accessibility tree snapshot + disabled element detection built into
every scan.

---

### Get Started

```bash
pip install llm-browser-driver
# or clone:
git clone https://github.com/microscaler/llm-browser-driver
```

---

> *"The only QA engineer that never sleeps, never complains about
> flaky tests, and scales to thousands of parallel test runners."*

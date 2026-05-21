# LLM Browser Driver

## Agent Rules

> **Desktop dev environment** — before doing anything in this repo, read the
> Microscaler-wide topology brief. It explains that you are on a Mac but the
> code lives on `ms02` (NFS), where commands execute for this environment, how
> the Kind cluster and vLLM fit in, and the network constraints behind the SSH
> tunneling. Do not duplicate its contents here — link to it. If reality drifts,
> fix the canonical doc, not this copy.
>
> - GitHub: [`cylon-local-infra/docs/desktop-dev-environment.md`](https://github.com/microscaler/cylon-local-infra/blob/main/docs/desktop-dev-environment.md)
> - On ms02 NFS: `~/Workspace/microscaler/cylon-local-infra/docs/desktop-dev-environment.md`

---

## Core Rules

### 1. Spike code is the source of truth for existing logic

All existing behavior is in `src/09_interactive_exploration.py` (the superset). When refactoring or adding features:

1. Read `09_interactive_exploration.py` to understand what exists
2. Map functionality to the module structure below
3. Never rewrite logic from memory — always reference the spike
4. The spike files `src/01_exploratory_test.py` through `src/08_sync_hybrid.py` are historical — `09` is the canonical implementation

### 2. Module Structure

```
src/llm_browser_driver/
├── __init__.py          # Public API: BrowserDriver class, __version__
├── agent.py             # Core interaction loop — decides actions, runs the loop
├── selector.py          # Action-to-element matching (fuzzy lookup)
├── actions.py           # Action executor (click, fill, navigate, etc.)
├── state.py             # Page state extraction (DOM, A11y tree, console, etc.)
├── llm_client.py        # LLM abstraction (OpenAI-compatible client, JSON parsing)
├── report.py            # Test report generation (JSON, Markdown)
├── config.py            # Configuration management (env vars, YAML, defaults)
├── spec_parser.py       # OpenAPI spec analyzer (M2+)
├── auth.py              # Auth session management (M2+)
└── exceptions.py        # Custom exceptions
```

### 3. No hardcoded values

Every constant from the spike must become configurable:

| Spike constant | Product config | Source in `09_*.py` |
|---|---|---|
| `FRONTEND_URL` | `config.url` (required) | Line 26 |
| `LLM_API_URL` | `config.llm.api_url` (required) | Line 27 |
| `LLM_MODEL` | `config.llm.model` (required) | Line 28 |
| `MAX_ITERATIONS` | `config.agent.max_iterations` (default 30) | Line 31 |
| `MAX_TOKENS` | `config.llm.max_tokens` (default 2048) | Line 32 |
| `TEMPERATURE` | `config.llm.temperature` (default 0.3) | Line 33 |

### 4. Configuration System

Configuration is loaded in priority order:

1. Constructor args (highest priority)
2. Environment variables (`LLM_BROWSER_DRIVER_*`)
3. YAML config file (`--config config.yaml` or `$HOME/.llm-browser-driver/config.yaml`)
4. Defaults (lowest priority)

**Environment variable naming:** Flatten the config structure:

```
config.llm.api_url        → LLM_BROWSER_DRIVER__LLM_API_URL
config.llm.model          → LLM_BROWSER_DRIVER__LLM_MODEL
config.llm.max_tokens     → LLM_BROWSER_DRIVER__LLM_MAX_TOKENS
config.llm.temperature    → LLM_BROWSER_DRIVER__LLM_TEMPERATURE
config.llm.timeout        → LLM_BROWSER_DRIVER__LLM_TIMEOUT
config.llm.streaming      → LLM_BROWSER_DRIVER__LLM_STREAMING
config.agent.max_iterations → LLM_BROWSER_DRIVER__MAX_ITERATIONS
config.agent.max_failures → LLM_BROWSER_DRIVER__MAX_FAILURES
config.browser.headless   → LLM_BROWSER_DRIVER__HEADLESS
```

### 5. LLM Quirks from Spike

**Qwen3 on vLLM requires `stream=False`.** When streaming is enabled, Qwen3 routes all output into the `reasoning` field and `content` is empty. The JSON parser will fail because it looks for `"action"` in the content field.

**This is a documented constraint:** The config system enforces `streaming: false` when the model is `qwen3` (or logs a warning). Document this in the public API.

**JSON parsing strategy** (from `parse_action_from_response` in spike):
1. Scan from end of response text to find last `{...}` block
2. Try parsing as JSON — if valid and has `action` key, return it
3. Fallback: regex search for `"action": "..."` anywhere in text
4. Fallback: return `done` with the text as summary

### 6. Selection Strategy — Anti-Fragile Selectors

**NEVER use CSS class selectors or XPath.** Every action is matched by semantically stable identifiers:

- **Click:** element `id` → button/link visible text → href match → fuzzy text
- **Fill:** input `name` → `placeholder` → `id` → `aria-label` → `<label[for]>` text
- **Select:** select `name` → option text

This is the core product differentiator. UI refactors (class name swaps, component restructuring) don't break tests.

### 7. Action-to-Code Mapping (from spike 09)

When implementing a module, reference the exact function in `09_interactive_exploration.py`:

| Module | Source function(s) in `09_*.py` | Lines |
|---|---|---|
| `state.py` | `extract_visible_text()`, `extract_element_details()`, `extract_html_snippet()`, `extract_accessibility_tree()`, `extract_console_during_navigation()`, `get_page_state()`, `build_page_summary()` | 36–351, 861–901 |
| `llm_client.py` | `decide_action()`, `parse_action_from_response()` | 430–527 |
| `actions.py` | `execute_action()` | 529–777 |
| `agent.py` | `run_interactive_test()`, `main()`, constants, system prompt | 354–427, 780–859, 904–980 |
| `config.py` | (new — no direct spike equivalent) | — |

### 8. Testing

- Use `pytest`
- Unit tests: `tests/unit/test_<module>.py`
- Integration tests: `tests/integration/test_<feature>.py`
- Fixtures: `tests/fixtures/` — mock HTML pages for offline testing
- Must mock LLM calls — never make real LLM calls in CI
- Use `playwright.sync_api` (sync API) — it's simpler and matches the spike

### 9. Commit Discipline

- Conventional Commits: `feat(module):`, `fix(module):`, `docs(module):`, `chore(module):`, `refactor(module):`
- **Never push** without explicit authorization
- **Never use `--no-verify`** — let pre-commit hooks run and fix what they flag
- Small, logically-grouped commits with full messages explaining the *why*

### 10. Dependencies

Pin to specific versions in `pyproject.toml`. Key dependencies:

```
playwright>=1.40
openai>=1.0
click>=8.0
pydantic>=2.0
pyyaml>=6.0
```

No transitive dependencies with non-FOSS licenses. Verify every dependency's license.

### 11. Move Spike Scripts to `legacy/` When Refactored

When a feature from `src/09_interactive_exploration.py` has been fully migrated to a module in `src/llm_browser_driver/`:

1. Copy `09_interactive_exploration.py` to `legacy/09_interactive_exploration.py`
2. Delete `src/09_interactive_exploration.py`
3. Update the commit message to reference the migration
4. Keep `legacy/` as a historical reference — do NOT delete it

This preserves the ability to diff against the original spike if regressions appear.

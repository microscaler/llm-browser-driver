# Hybrid Playwright + LLM Exploratory Testing — Iteration Plan

| Feature | Status | Notes |
|---------|--------|-------|
| P0: Richer page state | ✅ Done | Visible text, ARIA labels, form labels, accessible tree |
| P1: Interactive exploration | ✅ Done | LLM decides actions, agent executes them, state loop |
| P2: Auth integration | ⬜ TODO | Load storage-shipper.json, test authenticated flows |
| P3: BDD output generation | ⬜ TODO | LLM findings → Gherkin scenarios |
| P4: Integration with BDD | ⬜ TODO | Pre-BDD exploratory tests in CI |

## P1 Results (Actual Run)

| Page | Iterations | Success Rate | Key Observations |
|------|------------|--------------|------------------|
| Homepage Navigation | 15 | 93% (14/15) | Clicked Businesses, Hauliers, Warehouses, How It Works, navigated to /signin |
| Post a Job Form | 13 | 100% (13/13) | Discovered form fields via evaluate(), filled inputs, clicked Next Step |
| Login Page | 15 | 87% (13/15) | Filled email/password, clicked Sign In, detected error state |
| Register Page | 2 | 50% (1/2) | Failed on "First Name" field — field labels need aria-label |
| **Total** | **45** | **92% (41/45)** | 100% JSON parsing success rate |

## P1 Fixes Applied

1. **JSON parser**: Scan from end of LLM response for last `{...}` block (handles Qwen3 reasoning text and markdown code blocks)
2. **Evaluate handler**: Transform `console.log(expr)` → `return expr` so Playwright captures results
3. **Fill handler**: Now checks `name`, `placeholder`, `id`, `aria-label`, AND label text (via `label[for="id"]`)
4. **Frontend AuthInput**: Added `aria-label={props.label}`, `title={props.label}`, `aria-describedby` for accessibility AND discoverability

## Known Issues

- Register page: `First Name` field needs `aria-label` attribute (being fixed in AuthInput.jsx)
- LLM sometimes tries wrong field names before guessing correctly (adaptive behavior — works but wastes iterations)
- Empty LLM responses occur when vLLM times out (37s+ delays)

## How to Proceed

We iterate one priority at a time. Each iteration:
1. Implement the feature in `spikes/browser-use-augment/`
2. Test against the Hauliage frontend
3. Update `hybrid-playwright-llm-testing` skill with new patterns
4. Update wiki with learnings

Next: **P2** (auth integration) — load `storage-shipper.json` and test authenticated flows.


# LLM Browser Driver

An open-source, LLM-powered web testing tool that combines Playwright's browser automation with AI-driven exploratory testing.

**Key differentiator:** Zero selector maintenance. The LLM discovers elements the way a human does — by labels, text content, and structure — so UI refactors don't break tests.

## Quick Start

```bash
# Install
pip install llm-browser-driver

# Run an exploratory test
llm-browser-driver explore \
    --url http://localhost:3000 \
    --goal "Test the user registration flow" \
    --model qwen3 \
    --llm-api http://localhost:8000/v1

# Run spec-driven tests from an OpenAPI spec
llm-browser-driver spec \
    --spec openapi.yaml \
    --url http://staging.example.com \
    --mapping endpoint-mapping.yaml
```

## Features

- **AI-Driven Exploration**: LLM drives browser navigation, form filling, and validation without hardcoded selectors
- **Spec-Driven Testing**: Generate tests from OpenAPI specs — map API endpoints to frontend pages and automatically test
- **Anti-Fragile Selectors**: Never maintain CSS selectors again. The LLM matches by text content, labels, and structure
- **Rich Reporting**: JSON, Markdown, HTML (with screenshot thumbnails), JUnit XML outputs
- **Screenshot Capture**: Automatic screenshots at configurable intervals and on failures
- **Run Versioning**: `run-{timestamp}/` hierarchy with central dashboard
- **Multi-LLM Support**: OpenAI, OpenRouter, vLLM, TGI, Ollama — any `/v1/chat/completions` endpoint

## Installation

```bash
pip install llm-browser-driver
```

Install Playwright browsers:

```bash
playwright install chromium
```

## Configuration

### Environment Variables

```bash
LLM_BROWSER_DRIVER__LLM_API_URL=http://localhost:8000/v1
LLM_BROWSER_DRIVER__LLM_MODEL=qwen3
LLM_BROWSER_DRIVER__MAX_TOKENS=2048
LLM_BROWSER_DRIVER__TEMPERATURE=0.3
LLM_BROWSER_DRIVER__MAX_ITERATIONS=30
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

browser:
  headless: true
  viewport:
    width: 1280
    height: 720
```

## CLI Reference

### Exploratory Testing

```bash
llm-browser-driver explore \
    --url http://localhost:3000 \
    --goal "Test the user registration flow" \
    --output ./reports \
    --model claude-sonnet-4 \
    --llm-api https://api.anthropic.com/v1
```

### Spec-Driven Testing

```bash
llm-browser-driver spec \
    --spec openapi.yaml \
    --url http://staging.example.com \
    --mapping endpoint-mapping.yaml \
    --test-data test-data.yaml \
    --output ./spec-results \
    --verbose
```

### Batch Testing

```bash
llm-browser-driver batch \
    --tests tests/e2e/regression-tests.json \
    --output ./batch-results \
    --model qwen3
```

### View Reports

```bash
llm-browser-driver serve --directory results/
```

## Library Mode

```python
from llm_browser_driver import BrowserDriver

driver = BrowserDriver(
    llm_api_url="http://vllm:8000/v1",
    llm_model="qwen3",
    max_tokens=2048,
    temperature=0.3,
)

result = driver.explore(
    url="http://myapp.com",
    goal="Validate the checkout flow end-to-end",
    max_iterations=30,
)

print(result.status)  # "success" | "error"
print(result.findings)  # List of discovered issues
```

## Supported LLMs

- OpenAI (gpt-4, gpt-4o)
- Anthropic (Claude)
- OpenRouter
- vLLM, TGI, Ollama, LM Studio
- Azure OpenAI
- Any OpenAI-compatible endpoint

## CI/CD Integration

Generate JUnit XML for CI:

```bash
llm-browser-driver batch \
    --tests tests/e2e/regression-tests.json \
    --report-formats junit \
    --output ci-results/
```

GitHub Actions example:

```yaml
- run: pip install llm-browser-driver playwright
- run: |
    llm-browser-driver batch \
      --tests e2e/regression-tests.json \
      --output ci-results/
      --report-formats json,junit
- uses: actions/upload-artifact@v4
  with:
    name: browser-test-results
    path: ci-results/
```

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md) for development setup and contribution guidelines.

## License

MIT License. See [LICENSE](./LICENSE) for details.

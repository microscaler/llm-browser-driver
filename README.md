# LLM Browser Driver

Autonomous AI-driven web testing and exploration. Combines Playwright with an LLM that navigates pages without hardcoded selectors.

**Key differentiator:** Zero selector maintenance. The LLM discovers elements by labels, text content, and structure — not CSS classes or XPath.

## Quickstart

```bash
pip install llm-browser-driver

# Explore a page
from llm_browser_driver import BrowserDriver

driver = BrowserDriver(
    llm_api_url="http://localhost:8000/v1",
    llm_model="qwen3",
)

result = driver.explore(
    url="http://localhost:3000",
    goal="Test the user registration flow",
    max_iterations=30,
)

for finding in result.findings:
    print(finding["description"])
```

## Features

- **Interactive exploration** — LLM drives navigation, form filling, clicks, and JavaScript evaluation
- **Anti-fragile selectors** — matching by id, name, placeholder, aria-label, and label text (never CSS classes)
- **Console error capture** — detects JS errors during navigation and interaction
- **Accessibility tree** — full a11y snapshot for every page state
- **Any LLM backend** — OpenAI-compatible API (vLLM, Ollama, OpenRouter, etc.)

## Installation

```bash
pip install llm-browser-driver
playwright install chromium
```

## Testing

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

## License

MIT

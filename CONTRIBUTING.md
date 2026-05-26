# Contributing to LLM Browser Driver

Thank you for your interest in contributing! This guide will help you get started.

## Development Setup

1. **Clone the repo**
   ```bash
   git clone https://github.com/microscaler/llm-browser-driver.git
   cd llm-browser-driver
   ```

2. **Create a virtual environment**
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```

3. **Install development dependencies**
   ```bash
   pip install -e ".[dev]"
   ```

4. **Install Playwright browsers**
   ```bash
   playwright install chromium
   ```

## Project Structure

```
llm-browser-driver/
├── src/llm_browser_driver/   # Main library code
│   ├── agent.py              # BrowserAgent — LLM decision maker
│   ├── driver.py             # BrowserDriver — public API
│   ├── cli.py                # CLI subcommands (explore, spec, batch, serve)
│   ├── selector.py           # Anti-fragile selectors (click, type, fill)
│   ├── spec_parser.py        # OpenAPI spec parser for spec-driven testing
│   ├── state.py              # Page state extraction (DOM, a11y, HTML)
│   ├── config.py             # Configuration management
│   ├── logging.py            # Structured JSON logging
│   ├── tracing.py            # OpenTelemetry tracing
│   ├── retry.py              # Retry/recovery patterns
│   └── report.py             # Report generation (JSON, HTML, JUnit)
├── tests/unit/               # Unit tests
├── examples/                 # Runnable examples
├── docs/                     # Documentation
│   └── PRD.md                # Product requirements
└── .github/                  # GitHub templates
```

## Testing

Run the full test suite:

```bash
python -m pytest tests/ -v
```

Run a specific test file:

```bash
python -m pytest tests/unit/test_spec_parser.py -v
```

Test coverage (requires `pytest-cov`):

```bash
python -m pytest tests/ --cov=src/llm_browser_driver --cov-report=term-missing
```

## Adding a New CLI Subcommand

1. Add the function in `src/llm_browser_driver/cli.py`
2. Decorate with `@click.command()` and `@click.option(...)`
3. Register with `main.add_command(my_cmd)`

Example:
```python
@click.command()
@click.option("--url", required=True, help="Target URL")
def my_cmd(url):
    """My new subcommand."""
    driver = BrowserDriver()
    driver.explore(url=url, goal="Test my feature")

main.add_command(my_cmd)
```

## Code Style

- **Python**: Follow PEP 8, use type hints
- **Formatting**: `ruff format` (or `black`)
- **Linting**: `ruff check` (or `flake8`)
- **Docstrings**: Google style for public APIs

## Submitting Changes

1. **Create a feature branch**: `git checkout -b feature/my-feature`
2. **Write tests** for your changes
3. **Run tests**: `python -m pytest tests/ -v`
4. **Commit** using conventional commits:
   - `feat:` — new feature
   - `fix:` — bug fix
   - `docs:` — documentation
   - `refactor:` — code refactoring
   - `test:` — tests
   - `chore:` — maintenance
5. **Push and open a Pull Request**

## Questions?

Open an issue or discussion on GitHub. We welcome all contributions!

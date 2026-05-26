# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- m4-cicd-docs

## [0.2.0] - 2025-05-21

### Added
- **Spec-driven testing** — `llm-browser-driver spec` CLI subcommand
- **OpenAPI spec parser** — Extracts endpoints, request bodies, schemas from OpenAPI 3.x YAML
- **Test goal generation** — Natural-language goals from API specs with page mapping
- **Structured JSON logging** — Extra fields, log timing, standalone mode
- **OpenTelemetry tracing** — Optional distributed tracing with no-op fallback
- **Retry & recovery** — Exponential backoff, fallback selectors, recovery actions (wait, scroll, refresh)
- **Comprehensive test suite** — 217 unit tests across all modules

### Changed
- README.md expanded with full CLI reference, library mode, CI/CD examples

## [0.1.0] - 2025-05-20

### Added
- Initial release
- Anti-fragile selectors (click by ID/text/link, fill by name/placeholder/aria-label)
- BrowserAgent with 8 action types (click, type_text, fill_field, click_link, submit, navigate, screenshot, done)
- BrowserDriver public API for library usage
- CLI with `explore`, `batch`, and `serve` subcommands
- Multi-format reporting: JSON, Markdown, HTML dashboard, JUnit XML
- Screenshot capture at configurable intervals
- Run versioning with timestamped directories
- Multi-LLM support (OpenAI, OpenRouter, vLLM, TGI, Ollama)
- Deep merge config with env var and YAML overrides
- Model presets (qwen3, claude, gpt-4o)

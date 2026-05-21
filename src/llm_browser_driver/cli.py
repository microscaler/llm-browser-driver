"""CLI interface for LLM Browser Driver.

Provides command-line access to exploratory and spec-driven testing via
the `llm-browser-driver` command. Uses Click for argument parsing and
subcommand structure.

Usage::

    llm-browser-driver explore --url http://localhost:3000 --goal "test login"
    llm-browser-driver explore --url http://localhost:3000 --goal "test login" --output reports/
    llm-browser-driver spec --spec openapi.yaml --url http://staging.example.com

Uses Click for argument parsing and subcommand structure.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import click

from llm_browser_driver.agent import BrowserDriver, TestResult
from llm_browser_driver.config import load_config
from llm_browser_driver.report import generate_all_reports


# ---------------------------------------------------------------------------
# Shared options
# ---------------------------------------------------------------------------

def _common_options(fn):
    """Decorator for shared CLI options across subcommands."""
    fn = click.option(
        "--url",
        "-u",
        "url",
        help="Target application URL to test (e.g., http://localhost:3000).",
    )(fn)
    fn = click.option(
        "--model",
        "-m",
        default="qwen3",
        help="LLM model name (default: qwen3).",
    )(fn)
    fn = click.option(
        "--llm-api",
        default=None,
        help="LLM API URL (default: http://localhost:8000/v1).",
    )(fn)
    fn = click.option(
        "--max-tokens",
        type=int,
        default=2048,
        help="Maximum tokens for LLM responses (default: 2048).",
    )(fn)
    fn = click.option(
        "--temperature",
        type=float,
        default=0.3,
        help="LLM temperature (default: 0.3).",
    )(fn)
    fn = click.option(
        "--max-iterations",
        type=int,
        default=30,
        help="Maximum exploration iterations (default: 30).",
    )(fn)
    fn = click.option(
        "--headless/--no-headless",
        default=True,
        help="Run browser in headless mode (default: headless).",
    )(fn)
    fn = click.option(
        "--screenshot-dir",
        "-s",
        default=None,
        help="Directory to save screenshots (e.g., results/screenshots/).",
    )(fn)
    fn = click.option(
        "--screenshot-interval",
        type=int,
        default=5,
        help="Take a screenshot every N iterations (default: 5).",
    )(fn)
    fn = click.option(
        "--screenshot-on-failure/--no-screenshot-on-failure",
        default=True,
        help="Capture screenshot on errors (default: enabled).",
    )(fn)
    fn = click.option(
        "--output",
        "-o",
        default=None,
        help="Output directory for reports (JSON, Markdown, HTML, JUnit XML).",
    )(fn)
    fn = click.option(
        "--report-formats",
        default="json,markdown,html,junit",
        help="Comma-separated report formats to generate (default: json,markdown,html,junit).",
    )(fn)
    fn = click.option(
        "--config",
        type=click.Path(exists=True, dir_okay=False),
        default=None,
        help="Path to YAML configuration file.",
    )(fn)
    fn = click.option(
        "--verbose",
        "-v",
        is_flag=True,
        default=False,
        help="Enable verbose output.",
    )(fn)
    return fn


# ---------------------------------------------------------------------------
# Explore subcommand
# ---------------------------------------------------------------------------

@click.command(name="explore")
@click.argument("goal", required=False)
@_common_options
@click.option(
    "--auth-file",
    type=click.Path(exists=True, dir_okay=False),
    default=None,
    help="Playwright storage-shipper JSON file for authenticated sessions.",
)
@click.option(
    "--goal-file",
    type=click.Path(exists=True, dir_okay=False),
    default=None,
    help="Path to a file containing the exploration goal.",
)
@click.pass_context
def explore_cmd(ctx, url, model, llm_api, max_tokens, temperature,
                max_iterations, headless, screenshot_dir, screenshot_interval,
                screenshot_on_failure, output, report_formats,
                config, verbose, goal, auth_file, goal_file):
    """Run an exploratory test against a web application.

    The LLM drives a Playwright browser session in a closed loop:
    capturing page state, deciding actions, executing them, and
    reporting findings.

    GOAL is a required argument if --goal-file is not provided.

    Example::

        llm-browser-driver explore \\
            --url http://localhost:3000 \\
            --goal "Test the user registration flow" \\
            --model qwen3 \\
            --output ./reports

    """
    # Resolve goal
    goal_text = goal
    if goal_file:
        goal_text = Path(goal_file).read_text().strip()
    if not goal_text:
        click.echo("Error: --goal or --goal-file is required.", err=True)
        ctx.exit(1)

    # Resolve report formats
    formats = [f.strip() for f in report_formats.split(",") if f.strip()]

    # Build config from CLI args
    overrides: dict[str, Any] = {
        "llm": {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
        },
        "agent": {"max_iterations": max_iterations},
        "browser": {"headless": headless},
    }
    if llm_api:
        overrides["llm"]["api_url"] = llm_api
    if config:
        overrides["config_file"] = config

    config_obj = load_config(**overrides)

    if verbose:
        click.echo(f"[*] Target URL: {url}")
        click.echo(f"[*] Model: {config_obj.llm.model}")
        click.echo(f"[*] API: {config_obj.llm.api_url}")
        click.echo(f"[*] Max iterations: {config_obj.agent.max_iterations}")
        click.echo(f"[*] Headless: {config_obj.browser.headless}")
        click.echo("")

    # Run exploration
    if verbose:
        click.echo(f"[*] Starting exploration: {goal_text[:80]}...")

    driver = BrowserDriver(config=config_obj)
    result: TestResult = driver.explore(
        url=url,
        goal=goal_text,
        max_iterations=max_iterations,
        auth_file=auth_file,
        screenshot_dir=screenshot_dir,
        screenshot_interval=screenshot_interval,
        screenshot_on_failure=screenshot_on_failure,
    )

    # Print summary
    click.echo("")
    click.echo("=" * 60)
    click.echo(f" Exploration: {result.test_name}")
    click.echo(f" Status: {result.status.upper()}")
    click.echo(f" Iterations: {result.iterations}")
    click.echo(f" Time: {result.time_taken:.1f}s")
    click.echo(f" Initial URL: {result.initial_url}")
    click.echo(f" Final URL: {result.final_url}")
    click.echo("=" * 60)

    if result.findings:
        click.echo(f"\n Findings ({len(result.findings)}):")
        for f in result.findings:
            severity = f.get("severity", "info").upper()
            desc = f.get("description", "")
            click.echo(f"  [{severity}] {desc}")

    if result.console_errors:
        click.echo(f"\n Console Errors ({len(result.console_errors)}):")
        for err in result.console_errors:
            click.echo(f"  [{err.get('type', '?')}] {err.get('text', '')}")

    if result.error:
        click.echo(f"\n Error: {result.error}")

    # Generate reports
    if output:
        report_dir = Path(output)
        paths = generate_all_reports(result, report_dir, formats=formats)
        click.echo("")
        click.echo(" Reports generated:")
        for fmt, path in paths.items():
            click.echo(f"  [{fmt}] {path}")

    # Exit with error code if exploration failed
    if result.status == "error":
        sys.exit(1)


# ---------------------------------------------------------------------------
# Batch subcommand
# ---------------------------------------------------------------------------

@click.command(name="batch")
@_common_options
@click.option(
    "--tests",
    "-t",
    type=click.Path(exists=True, dir_okay=False),
    required=True,
    help="Path to a JSON file containing an array of test definitions.",
)
@click.option(
    "--parallel/--sequential",
    default=False,
    help="Run tests in parallel (requires async, not yet implemented). Defaults to sequential.",
)
@click.pass_context
def batch_cmd(ctx, url, model, llm_api, max_tokens, temperature,
              max_iterations, headless, screenshot_dir, screenshot_interval,
              screenshot_on_failure, output, report_formats,
              config, verbose, tests, parallel):
    """Run multiple exploratory tests from a JSON file.

    The test file should contain a JSON array of objects with keys:
    - url (str): Target URL
    - goal (str): Exploration goal
    - auth_file (str, optional): Path to auth storage file

    Example test file::

        [
            {"url": "http://localhost:3000", "goal": "Test login flow"},
            {"url": "http://localhost:3000/signin", "goal": "Test registration"}
        ]

    """
    if parallel:
        click.echo("Warning: Parallel mode not yet implemented. Running sequentially.", err=True)

    # Load test definitions
    tests_path = Path(tests)
    try:
        test_defs = json.loads(tests_path.read_text())
    except json.JSONDecodeError as e:
        click.echo(f"Error: Invalid JSON in test file: {e}", err=True)
        ctx.exit(1)

    if not isinstance(test_defs, list):
        click.echo("Error: Test file must contain a JSON array.", err=True)
        ctx.exit(1)

    if not test_defs:
        click.echo("Error: Test file is empty.", err=True)
        ctx.exit(1)

    # Build config
    overrides: dict[str, Any] = {
        "llm": {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
        },
        "agent": {"max_iterations": max_iterations},
        "browser": {"headless": headless},
    }
    if llm_api:
        overrides["llm"]["api_url"] = llm_api
    if config:
        overrides["config_file"] = config

    config_obj = load_config(**overrides)

    if verbose:
        click.echo(f"[*] Running {len(test_defs)} tests...")
        click.echo(f"[*] Model: {config_obj.llm.model}")
        click.echo(f"[*] Max iterations: {config_obj.agent.max_iterations}")
        click.echo("")

    driver = BrowserDriver(config=config_obj)

    # Run each test individually to capture per-test screenshots
    results = []
    for test in test_defs:
        r = driver.explore(
            url=test["url"],
            goal=test["goal"],
            max_iterations=max_iterations,
            auth_file=test.get("auth_file"),
            screenshot_dir=screenshot_dir,
            screenshot_interval=screenshot_interval,
            screenshot_on_failure=screenshot_on_failure,
        )
        results.append(r)

    # Print summary
    passed = sum(1 for r in results if r.status == "success")


# ---------------------------------------------------------------------------
# Info subcommand
# ---------------------------------------------------------------------------

@click.command(name="info")
def info_cmd():
    """Show version and configuration information."""
    from llm_browser_driver import __version__

    click.echo(f"LLM Browser Driver v{__version__}")
    click.echo("")
    click.echo("Configuration:")
    config = load_config()
    click.echo(f"  LLM model: {config.llm.model}")
    click.echo(f"  LLM API: {config.llm.api_url}")
    click.echo(f"  Max tokens: {config.llm.max_tokens}")
    click.echo(f"  Temperature: {config.llm.temperature}")
    click.echo(f"  Max iterations: {config.agent.max_iterations}")
    click.echo(f"  Headless: {config.browser.headless}")
    click.echo(f"  Timeout: {config.browser.timeout}ms")


# ---------------------------------------------------------------------------
# Main CLI group
# ---------------------------------------------------------------------------

@click.group()
@click.version_option(version="0.1.0", prog_name="llm-browser-driver")
@click.pass_context
def main(ctx):
    """LLM Browser Driver — Autonomous AI-driven web testing.

    Combines Playwright's browser automation with an LLM's ability to
    understand and navigate pages without hardcoded selectors.
    """
    ctx.ensure_object(dict)
    ctx.obj["config"] = {}


main.add_command(explore_cmd)
main.add_command(batch_cmd)
main.add_command(info_cmd)


if __name__ == "__main__":
    main()

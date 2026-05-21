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
from llm_browser_driver.spec_parser import SpecParser


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
    failed = sum(1 for r in results if r.status == "error")
    total_time = sum(r.time_taken for r in results)

    click.echo("")
    click.echo("=" * 60)
    click.echo(" Batch Test Summary")
    click.echo("=" * 60)
    click.echo(f" Total: {len(results)}")
    click.echo(f" Passed: {passed}")
    click.echo(f" Failed: {failed}")
    click.echo(f" Time: {total_time:.1f}s")
    click.echo("=" * 60)

    # Per-test detail
    for i, r in enumerate(results, 1):
        status_icon = "✓" if r.status == "success" else "✗"
        click.echo(f"  {i}. [{status_icon}] {r.test_name}")
        if r.findings:
            for f in r.findings:
                severity = f.get("severity", "info").upper()
                desc = f.get("description", "")[:80]
                click.echo(f"      [{severity}] {desc}")

    # Generate reports
    if output:
        report_dir = Path(output)
        paths = generate_all_reports(results, report_dir, formats=report_formats.split(","))
        click.echo("")
        click.echo(" Reports generated:")
        for fmt, path in paths.items():
            click.echo(f"  [{fmt}] {path}")

    if failed > 0:
        sys.exit(1)


# ---------------------------------------------------------------------------
# Spec subcommand
# ---------------------------------------------------------------------------

@click.command(name="spec")
@_common_options
@click.option(
    "--spec",
    "spec_path",
    type=click.Path(exists=True, dir_okay=False),
    required=True,
    help="Path to an OpenAPI 3.x YAML specification file.",
)
@click.option(
    "--mapping",
    type=click.Path(exists=True, dir_okay=False),
    default=None,
    help="Path to a YAML file mapping API endpoints to frontend page paths.",
)
@click.option(
    "--test-data",
    type=click.Path(exists=True, dir_okay=False),
    default=None,
    help="Path to a YAML file with deterministic test data per endpoint.",
)
@click.option(
    "--skip-get/--all-methods",
    "include_get",
    default=False,
    help="Include GET endpoints in addition to POST/PUT/PATCH. Default: body methods only.",
)
@click.pass_context
def spec_cmd(ctx, url, model, llm_api, max_tokens, temperature,
             max_iterations, headless, screenshot_dir, screenshot_interval,
             screenshot_on_failure, output, report_formats,
             config, verbose, spec_path, mapping, test_data, include_get):
    """Run spec-driven tests from an OpenAPI specification.

    Parses the OpenAPI spec to identify endpoints with request bodies,
    maps them to frontend pages via a mapping file, generates test goals,
    and runs each through the exploratory driver.

    The mapping file (YAML) connects API paths to frontend pages::

        /api/v1/auth/signin: /signin
        /api/v1/auth/signup: /signup
        /api/v1/jobs: /post-a-job

    The test data file (YAML) provides deterministic input values::

        POST /api/v1/auth/signin:
          email: ci-test@example.com
          password: TestP@ss123!

    The driver will:
    - For each endpoint: explore the mapped page, validate form fields
      exist and match the spec, submit with test data, check response.

    Example::

        llm-browser-driver spec \\\\
            --spec openapi.yaml \\\\
            --url http://staging.example.com \\\\
            --mapping endpoint-mapping.yaml \\\\
            --test-data test-data.yaml \\\\
            --output ./spec-results \\\\
            --verbose

    """
    # Parse the OpenAPI spec
    click.echo(f"[*] Parsing spec: {spec_path}")
    parser = SpecParser(spec_path=spec_path)

    # Show spec info
    info = parser.get_spec_info()
    click.echo(f"    Title: {info['title']} v{info['version']}")

    counts = parser.get_endpoint_count()
    click.echo(f"    Endpoints: {dict(counts)} total")

    # Get body endpoints (or all if --all-methods)
    if include_get:
        endpoints = parser.get_endpoints()
    else:
        endpoints = parser.get_body_endpoints()

    click.echo(f"    Testing: {len(endpoints)} endpoint(s)")

    # Load mapping
    mapping_dict: dict[str, str] | None = None
    if mapping:
        mapping_path = Path(mapping)
        mapping_dict = yaml.safe_load(mapping_path.read_text()) or {}
        click.echo(f"    Mapping: {len(mapping_dict)} endpoint-to-page mappings")
    else:
        click.echo("    Warning: No mapping file provided. Endpoints without a mapped")
        click.echo("    page will be skipped. Use --mapping to connect API paths to pages.")
        click.echo("")
        click.echo("    Skipping spec-driven testing without a mapping.")
        click.echo("    Provide a mapping file to generate test goals.")
        return

    # Load test data
    test_data_dict: dict[str, dict[str, Any]] | None = None
    if test_data:
        test_data_path = Path(test_data)
        test_data_dict = yaml.safe_load(test_data_path.read_text()) or {}
        click.echo(f"    Test data: {len(test_data_dict)} endpoint data sets")

    # Generate goals
    goals = parser.generate_goals(url, mapping_dict, test_data_dict)
    if not goals:
        click.echo("")
        click.echo("    No test goals generated. Check that:")
        click.echo("    1. The spec has endpoints with request bodies")
        click.echo("    2. The mapping covers those endpoints")
        click.echo("")
        click.echo("    Available endpoints for mapping:")
        for ep in endpoints:
            click.echo(f"      {ep.identifier}")
        return

    click.echo(f"    Generated {len(goals)} test goal(s)")
    click.echo("")

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
        click.echo(f"[*] Model: {config_obj.llm.model}")
        click.echo(f"[*] API: {config_obj.llm.api_url}")
        click.echo(f"[*] Max iterations: {config_obj.agent.max_iterations}")
        click.echo("")

    driver = BrowserDriver(config=config_obj)

    # Run each test goal
    results: list[TestResult] = []
    endpoint_results: list[dict[str, Any]] = []

    for i, goal_info in enumerate(goals, 1):
        ep = goal_info["endpoint"]
        page_url = goal_info["page_url"]
        goal_text = goal_info["goal"]

        if verbose:
            click.echo(f"[*] [{i}/{len(goals)}] Testing {ep.identifier} -> {page_url}")

        r: TestResult = driver.explore(
            url=page_url,
            goal=goal_text,
            max_iterations=max_iterations,
            screenshot_dir=screenshot_dir,
            screenshot_interval=screenshot_interval,
            screenshot_on_failure=screenshot_on_failure,
        )
        results.append(r)

        endpoint_results.append({
            "endpoint": ep.identifier,
            "url": page_url,
            "status": r.status,
            "iterations": r.iterations,
            "findings": r.findings,
            "console_errors": r.console_errors,
            "error": r.error,
        })

    # Print spec-driven summary
    passed = sum(1 for e in endpoint_results if e["status"] == "success")
    failed = sum(1 for e in endpoint_results if e["status"] == "error")
    skipped = sum(1 for e in endpoint_results if e["status"] == "skipped")

    click.echo("")
    click.echo("=" * 60)
    click.echo(" Spec-Driven Test Summary")
    click.echo("=" * 60)
    click.echo(f" Spec: {info['title']} v{info['version']}")
    click.echo(f" Endpoints tested: {len(endpoint_results)}")
    click.echo(f" Passed: {passed}")
    click.echo(f" Failed: {failed}")
    click.echo("=" * 60)

    # Per-endpoint detail
    for e in endpoint_results:
        status_icon = "✓" if e["status"] == "success" else "✗"
        click.echo(f"  {status_icon} {e['endpoint']}")
        click.echo(f"      URL: {e['url']}")
        if e["findings"]:
            for f in e["findings"]:
                severity = f.get("severity", "info").upper()
                desc = f.get("description", "")[:100]
                click.echo(f"      [{severity}] {desc}")
        if e["console_errors"]:
            for ce in e["console_errors"]:
                click.echo(f"      [CONSOLE] {ce.get('text', '')[:100]}")

    # Generate reports
    if output:
        report_dir = Path(output)
        paths = generate_all_reports(results, report_dir, formats=report_formats.split(","))
        click.echo("")
        click.echo(" Reports generated:")
        for fmt, path in paths.items():
            click.echo(f"  [{fmt}] {path}")

    if failed > 0:
        sys.exit(1)


# ---------------------------------------------------------------------------
# Serve subcommand
# ---------------------------------------------------------------------------

@click.command(name="serve")
@click.option(
    "--directory",
    "-d",
    default="results",
    help="Directory containing report runs (default: results/).",
)
@click.option(
    "--port",
    "-p",
    type=int,
    default=8080,
    help="Port to serve on (default: 8080).",
)
@click.option(
    "--host",
    "-h",
    default="127.0.0.1",
    help="Host to bind to (default: 127.0.0.1).",
)
@click.option(
    "--open/--no-open",
    "open_browser",
    default=True,
    help="Open the report dashboard in the default browser (default: open).",
)
def serve_cmd(directory, port, host, open_browser):
    """Start a local HTTP server to view test reports and dashboard.

    Serves the results directory as a static site with the central
    dashboard (index.html) at the root. Each run-{timestamp}/ folder
    contains its own report.html with screenshot thumbnails.

    Example::

        llm-browser-driver serve --directory results/ --port 8080

    """
    import http.server
    import threading
    import webbrowser
    from urllib.parse import urlparse

    results_dir = Path(directory).resolve()
    if not results_dir.is_dir():
        click.echo(f"Error: Results directory not found: {results_dir}", err=True)
        sys.exit(1)

    index_file = results_dir / "index.html"
    if not index_file.is_file():
        click.echo(
            f"Warning: No index.html found at {results_dir}. "
            f"Run an exploration first with --output {results_dir}.",
            err=True,
        )

    # Start server in a thread
    class QuietHandler(http.server.SimpleHTTPRequestHandler):
        """HTTP handler that suppresses request logging for a quiet serve."""

        def log_message(self, format, *args):
            pass  # Silence request logs

        def end_headers(self):
            # Add CORS headers so the dashboard can fetch run data
            self.send_header("Access-Control-Allow-Origin", "*")
            super().end_headers()

    server = http.server.HTTPServer(
        (host, port),
        lambda *args, **kwargs: QuietHandler(*args, directory=str(results_dir), **kwargs),
    )

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    # Open in browser
    url = f"http://{host}:{port}/"
    if open_browser:
        webbrowser.open(url)

    click.echo(f"Report server started: {url}")
    click.echo(f"  Directory: {results_dir}")
    click.echo(f"  Press Ctrl+C to stop")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        click.echo("\nServer stopped.")
        server.shutdown()


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
main.add_command(spec_cmd)
main.add_command(serve_cmd)

if __name__ == "__main__":
    main()

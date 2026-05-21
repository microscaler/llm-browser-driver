"""Test report generation for LLM Browser Driver.

Generates structured test reports from TestResult objects in multiple formats:
- JSON: machine-readable, machine-parsable
- Markdown: human-readable summary table
- Playwright HTML: rich interactive report (via HTML report generation)
- JUnit XML: CI/CD integration

The report generator handles both single TestResult and batch (list[TestResult])
output, producing summary statistics alongside per-test detail.

Extracted from spike patterns in `spike_deprecated/` scripts.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from llm_browser_driver.agent import TestResult


# ---------------------------------------------------------------------------
# Report format base
# ---------------------------------------------------------------------------

def _timestamp() -> str:
    """Return ISO-8601 timestamp for report headers."""
    return datetime.now(timezone.utc).isoformat()


def _status_emoji(status: str) -> str:
    """Map test status to emoji for markdown rendering."""
    return {"success": "✅", "error": "❌"}.get(status, "❓")


# ---------------------------------------------------------------------------
# JSON report
# ---------------------------------------------------------------------------

def generate_json(
    result: TestResult | list[TestResult],
    indent: int = 2,
) -> str:
    """Generate a JSON report from one or more TestResults.

    Args:
        result: A single TestResult or a list of TestResults.
        indent: JSON indentation level.

    Returns:
        JSON-formatted report string.

    Example:
        >>> result = driver.explore(url="http://localhost:3000", goal="test login")
        >>> print(generate_json(result))
    """
    if isinstance(result, TestResult):
        results = [result]
    else:
        results = list(result)

    report: dict[str, Any] = {
        "report_generated_at": _timestamp(),
        "total_tests": len(results),
        "summary": {
            "passed": sum(1 for r in results if r.status == "success"),
            "failed": sum(1 for r in results if r.status == "error"),
            "total_time_seconds": sum(r.time_taken for r in results),
            "total_iterations": sum(r.iterations for r in results),
        },
        "tests": [r.to_dict() for r in results],
    }

    return json.dumps(report, indent=indent, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Markdown report
# ---------------------------------------------------------------------------

def generate_markdown(
    result: TestResult | list[TestResult],
    max_history_lines: int = 20,
) -> str:
    """Generate a human-readable Markdown report.

    Produces a summary table followed by per-test detail sections including
    action history, console errors, and findings.

    Args:
        result: A single TestResult or a list of TestResults.
        max_history_lines: Maximum action history lines to include per test.

    Returns:
        Markdown-formatted report string.

    Example:
        >>> result = driver.explore(url="http://localhost:3000", goal="test login")
        >>> print(generate_markdown(result))
    """
    if isinstance(result, TestResult):
        results = [result]
    else:
        results = list(result)

    lines: list[str] = []
    lines.append("# LLM Browser Driver — Test Report\n")
    lines.append(f"**Generated:** {_timestamp()}  ")
    lines.append(f"**Total Tests:** {len(results)}  ")
    lines.append(f"**Passed:** {sum(1 for r in results if r.status == 'success')}  ")
    lines.append(f"**Failed:** {sum(1 for r in results if r.status == 'error')}  ")
    total_time = sum(r.time_taken for r in results)
    lines.append(f"**Total Time:** {total_time:.1f}s\n")

    # Summary table
    lines.append("## Summary\n")
    lines.append("| # | Test | URL | Status | Iterations | Time |")
    lines.append("|---|------|-----|--------|------------|------|")
    for i, r in enumerate(results, 1):
        lines.append(
            f"| {i} | {r.test_name} | `{r.url}` | "
            f"{_status_emoji(r.status)} {r.status} | "
            f"{r.iterations} | {r.time_taken:.1f}s |"
        )
    lines.append("")

    # Per-test detail
    for r in results:
        lines.append(f"## Test: {r.test_name}\n")
        lines.append(f"- **URL:** `{r.url}`")
        lines.append(f"- **Status:** {_status_emoji(r.status)} {r.status}")
        if r.initial_url:
            lines.append(f"- **Initial URL:** `{r.initial_url}`")
        if r.final_url:
            lines.append(f"- **Final URL:** `{r.final_url}`")
        lines.append(f"- **Iterations:** {r.iterations}")
        lines.append(f"- **Time:** {r.time_taken:.1f}s")
        lines.append("")

        # Action history
        if r.action_history:
            lines.append("### Action History\n")
            lines.append("| Step | Action | Parameters | Result | URL |")
            lines.append("|------|--------|-----------|--------|-----|")
            for entry in r.action_history[:max_history_lines]:
                params = json.dumps(entry.get("parameters", {}), ensure_ascii=False)
                lines.append(
                    f"| {entry.get('step', '?')} | "
                    f"{entry.get('action', '?')} | "
                    f"`{params}` | "
                    f"{entry.get('result', '')[:100]} | "
                    f"`{entry.get('url', '')}` |"
                )
            if len(r.action_history) > max_history_lines:
                lines.append(
                    f"\n*... and {len(r.action_history) - max_history_lines} more steps*"
                )
            lines.append("")

        # Console errors
        if r.console_errors:
            lines.append(f"### Console Errors ({len(r.console_errors)})\n")
            for err in r.console_errors:
                lines.append(f"- **[{err.get('type', '?')}]** {err.get('text', '')}")
            lines.append("")

        # Findings
        if r.findings:
            lines.append(f"### Findings ({len(r.findings)})\n")
            for finding in r.findings:
                severity = finding.get("severity", "info")
                lines.append(
                    f"- **[{severity.upper()}]** {finding.get('description', '')}"
                )
            lines.append("")

        # Errors
        if r.error:
            lines.append(f"### Error\n\n```\n{r.error}\n```\n")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Playwright HTML report
# ---------------------------------------------------------------------------

def generate_html_report(
    result: TestResult | list[TestResult],
    output_path: str | Path,
    *,
    include_action_history: bool = True,
    include_console_errors: bool = True,
    include_findings: bool = True,
    screenshot_base: str | Path | None = None,
) -> Path:
    """Generate a rich Playwright-style HTML test report.

    Produces a standalone HTML file with styled sections for test results,
    action history, console errors, and findings. Designed for human review
    and can be opened in any browser.

    Args:
        result: A single TestResult or a list of TestResults.
        output_path: File path to write the HTML report to.
        include_action_history: Whether to include the action history table.
        include_console_errors: Whether to include console error listings.
        include_findings: Whether to include findings section.
        screenshot_base: Base path for screenshots. When the HTML report is
            generated inside a run directory, pass the run directory path
            here — screenshots are rendered as relative ``screenshots/step-N.png``
            links. If None, the screenshot column is omitted.

    Returns:
        Absolute path to the generated HTML file.

    Example:
        >>> generate_html_report(result, "reports/test-report.html")
    """
    if isinstance(result, TestResult):
        results = [result]
    else:
        results = list(result) if not isinstance(result, list) else result

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    total_time = sum(r.time_taken for r in results)
    passed = sum(1 for r in results if r.status == "success")
    failed = sum(1 for r in results if r.status == "error")

    # Build per-test HTML sections
    test_sections = []
    for r in results:
        status_class = "pass" if r.status == "success" else "fail"
        status_label = "PASS" if r.status == "success" else "FAIL"
        status_color = "#2ea44f" if r.status == "success" else "#da3633"

        section = f'''
        <div class="test-result {status_class}">
            <div class="test-header">
                <span class="status-badge" style="background-color: {status_color};">{status_label}</span>
                <span class="test-name">{_html_escape(r.test_name)}</span>
                <span class="test-meta">
                    <span>{r.iterations} iterations</span>
                    <span>{r.time_taken:.1f}s</span>
                </span>
            </div>
            <div class="test-body">
                <div class="url-info">
                    <strong>URL:</strong> <code>{_html_escape(r.url)}</code>
                    {'<br>' + '<strong>Final:</strong> <code>' + _html_escape(r.final_url) + '</code>' if r.final_url and r.final_url != r.url else ''}
                </div>'''

        # Action history table
        if include_action_history and r.action_history:
            rows = []
            for entry in r.action_history:
                action = _html_escape(str(entry.get("action", "?")))
                params_json = json.dumps(entry.get("parameters", {}), ensure_ascii=False)
                params = _html_escape(f"`{params_json}`" if params_json else "-")
                result_text = _html_escape(str(entry.get("result", ""))[:120])
                url = _html_escape(str(entry.get("url", "")))
                screenshot_path = entry.get("screenshot", "")

                screenshot_cell = ""
                if screenshot_base and screenshot_path:
                    screenshot_url = f"{Path(screenshot_base).name}/{screenshot_path}"
                    screenshot_cell = (
                        f'<td><a href="{screenshot_url}" target="_blank">'
                        f'<img src="{screenshot_url}" class="screenshot-thumb" '
                        f'alt="Step {entry.get("step", "?")}"></a></td>'
                    )
                else:
                    screenshot_cell = "<td>-</td>"

                rows.append(
                    f'<tr><td>{entry.get("step", "?")}</td>'
                    f'<td><code>{action}</code></td>'
                    f'<td>{params}</td>'
                    f'<td>{result_text}</td>'
                    f'<td><code>{url}</code></td>'
                    f'{screenshot_cell}</tr>'
                )
            screenshot_col_header = ""
            if screenshot_base:
                screenshot_col_header = '<th>Screenshot</th>'
            section += f'''
                <div class="action-history">
                    <h3>Action History</h3>
                    <table class="history-table">
                        <thead><tr><th>Step</th><th>Action</th><th>Parameters</th><th>Result</th><th>URL</th>{screenshot_col_header}</tr></thead>
                        <tbody>
{"                ".join(f"<tr>{row}</tr>" for row in rows)}
                        </tbody>
                    </table>
                </div>'''

        # Console errors
        if include_console_errors and r.console_errors:
            error_items = []
            for err in r.console_errors:
                etype = _html_escape(str(err.get("type", "?")))
                etext = _html_escape(str(err.get("text", "")))
                error_items.append(f'<div class="console-error"><span class="error-type">{etype}</span>: {etext}</div>')
            section += f'''
                <div class="console-errors">
                    <h3>Console Errors ({len(r.console_errors)})</h3>
                    {"\n".join(error_items)}
                </div>'''

        # Findings
        if include_findings and r.findings:
            finding_items = []
            for f in r.findings:
                severity = f.get("severity", "info")
                desc = _html_escape(str(f.get("description", "")))
                finding_items.append(
                    f'<div class="finding"><span class="finding-severity finding-{severity}">{severity.upper()}</span> {desc}</div>'
                )
            section += f'''
                <div class="findings">
                    <h3>Findings ({len(r.findings)})</h3>
                    {"\n".join(finding_items)}
                </div>'''

        # Error
        if r.error:
            section += f'''
                <div class="error-section">
                    <h3>Error</h3>
                    <pre class="error-text">{_html_escape(r.error)}</pre>
                </div>'''

        section += "\n            </div>\n        </div>"
        test_sections.append(section)

    tests_html = "\n".join(test_sections)

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>LLM Browser Driver — Test Report</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
            background: #0d1117;
            color: #c9d1d9;
            padding: 2rem;
            line-height: 1.6;
        }}
        .report-header {{
            border-bottom: 1px solid #30363d;
            padding-bottom: 1rem;
            margin-bottom: 2rem;
        }}
        .report-header h1 {{
            font-size: 1.5rem;
            color: #58a6ff;
            margin-bottom: 0.5rem;
        }}
        .report-meta {{
            display: flex;
            gap: 2rem;
            font-size: 0.9rem;
            color: #8b949e;
        }}
        .report-meta span {{ display: flex; align-items: center; gap: 0.25rem; }}
        .summary-cards {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 1rem;
            margin-bottom: 2rem;
        }}
        .summary-card {{
            background: #161b22;
            border: 1px solid #30363d;
            border-radius: 6px;
            padding: 1rem;
            text-align: center;
        }}
        .summary-card .value {{
            font-size: 2rem;
            font-weight: 600;
        }}
        .summary-card .label {{
            font-size: 0.8rem;
            color: #8b949e;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }}
        .test-result {{
            background: #161b22;
            border: 1px solid #30363d;
            border-radius: 6px;
            margin-bottom: 1rem;
            overflow: hidden;
        }}
        .test-result.pass {{ border-left: 4px solid #2ea44f; }}
        .test-result.fail {{ border-left: 4px solid #da3633; }}
        .test-header {{
            display: flex;
            align-items: center;
            gap: 0.75rem;
            padding: 0.75rem 1rem;
            background: #1c2128;
        }}
        .status-badge {{
            display: inline-block;
            padding: 0.15rem 0.5rem;
            border-radius: 12px;
            font-size: 0.75rem;
            font-weight: 600;
            color: #fff;
        }}
        .test-name {{
            font-weight: 600;
            font-size: 1rem;
            flex: 1;
        }}
        .test-meta {{
            display: flex;
            gap: 1rem;
            font-size: 0.85rem;
            color: #8b949e;
        }}
        .test-body {{ padding: 1rem; }}
        .url-info {{ margin-bottom: 1rem; }}
        .url-info code {{
            background: #0d1117;
            padding: 0.2rem 0.5rem;
            border-radius: 4px;
            font-size: 0.85rem;
        }}
        .action-history, .console-errors, .findings, .error-section {{
            margin-top: 1rem;
        }}
        .action-history h3, .console-errors h3, .findings h3, .error-section h3 {{
            font-size: 0.9rem;
            color: #8b949e;
            margin-bottom: 0.5rem;
        }}
        .history-table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 0.85rem;
        }}
        .history-table th, .history-table td {{
            text-align: left;
            padding: 0.4rem 0.6rem;
            border-bottom: 1px solid #21262d;
        }}
        .history-table th {{
            color: #8b949e;
            font-weight: 500;
        }}
        .history-table code {{
            background: #0d1117;
            padding: 0.1rem 0.3rem;
            border-radius: 3px;
            font-size: 0.8rem;
        }}
        .screenshot-thumb {{
            max-width: 180px;
            max-height: 120px;
            border-radius: 4px;
            border: 1px solid #30363d;
            cursor: pointer;
            transition: opacity 0.2s;
        }}
        .screenshot-thumb:hover {{
            opacity: 0.85;
        }}
        .history-table td:last-child {{
            text-align: center;
            vertical-align: middle;
        }}
        .history-table th:last-child {{
            text-align: center;
        }}
        .console-error {{
            padding: 0.4rem 0.6rem;
            background: #1c2128;
            border-radius: 4px;
            margin-bottom: 0.3rem;
            font-size: 0.85rem;
        }}
        .error-type {{
            font-weight: 600;
            color: #d29922;
        }}
        .finding {{
            padding: 0.4rem 0.6rem;
            background: #1c2128;
            border-radius: 4px;
            margin-bottom: 0.3rem;
            font-size: 0.85rem;
        }}
        .finding-severity {{
            font-weight: 600;
            margin-right: 0.5rem;
        }}
        .finding-info .finding-severity {{ color: #58a6ff; }}
        .finding-low .finding-severity {{ color: #d29922; }}
        .finding-high .finding-severity {{ color: #f85149; }}
        .error-text {{
            background: #1c0000;
            border: 1px solid #da3633;
            padding: 0.75rem;
            border-radius: 4px;
            font-family: 'SFMono-Regular', Consolas, monospace;
            font-size: 0.85rem;
            color: #f85149;
            overflow-x: auto;
            white-space: pre-wrap;
        }}
        @media (max-width: 768px) {{
            body {{ padding: 1rem; }}
            .report-meta {{ flex-wrap: wrap; gap: 1rem; }}
            .summary-cards {{ grid-template-columns: repeat(2, 1fr); }}
            .history-table {{ font-size: 0.75rem; }}
            .history-table th, .history-table td {{ padding: 0.3rem; }}
        }}
    </style>
</head>
<body>
    <div class="report-header">
        <h1>LLM Browser Driver — Test Report</h1>
        <div class="report-meta">
            <span>📅 {_html_escape(_timestamp())}</span>
            <span>🧪 {len(results)} tests</span>
            <span>⏱ {total_time:.1f}s total</span>
        </div>
    </div>

    <div class="summary-cards">
        <div class="summary-card">
            <div class="value" style="color: #2ea44f;">{passed}</div>
            <div class="label">Passed</div>
        </div>
        <div class="summary-card">
            <div class="value" style="color: #f85149;">{failed}</div>
            <div class="label">Failed</div>
        </div>
        <div class="summary-card">
            <div class="value">{sum(r.iterations for r in results)}</div>
            <div class="label">Iterations</div>
        </div>
        <div class="summary-card">
            <div class="value">{total_time:.1f}s</div>
            <div class="label">Total Time</div>
        </div>
    </div>

    {tests_html}
</body>
</html>"""

    output_path.write_text(html_content, encoding="utf-8")
    return output_path


# ---------------------------------------------------------------------------
# JUnit XML report
# ---------------------------------------------------------------------------

def generate_junit_xml(
    result: TestResult | list[TestResult],
) -> str:
    """Generate a JUnit XML report for CI/CD integration.

    Args:
        result: A single TestResult or a list of TestResults.

    Returns:
        JUnit XML string.

    Example:
        >>> xml = generate_junit_xml(result)
        >>> with open("results.xml", "w") as f:
        ...     f.write(xml)
    """
    if isinstance(result, TestResult):
        results = [result]
    else:
        results = list(result)

    lines = ['<?xml version="1.0" encoding="UTF-8"?>']
    lines.append('<testsuites tests="{total}" failures="{failed}" time="{total_time:.3f}">'.format(
        total=len(results),
        failed=sum(1 for r in results if r.status == "error"),
        total_time=sum(r.time_taken for r in results),
    ))

    for r in results:
        lines.append(
            f'  <testsuite name="{_xml_escape(r.test_name)}" '
            f'tests="1" failures="{"1" if r.status == "error" else "0"}" '
            f'time="{r.time_taken:.3f}">'
        )

        # Test case
        lines.append(
            f'    <testcase classname="{_xml_escape(r.test_name)}" '
            f'name="{_xml_escape(r.test_name)}" '
            f'time="{r.time_taken:.3f}">'
        )

        if r.status == "error":
            lines.append(f'      <failure message="{_xml_escape(r.error or "Test failed")}"/>')

        lines.append("    </testcase>")
        lines.append("  </testsuite>")

    lines.append("</testsuites>")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# HTML report (plain — non-Playwright)
# ---------------------------------------------------------------------------

def write_html_report(
    result: TestResult | list[TestResult],
    output_path: str | Path,
) -> Path:
    """Generate a simple HTML report (drop-in replacement for Playwright reports).

    This is a simplified HTML report writer suitable for CI environments where
    Playwright's built-in HTML report generation isn't available.

    Args:
        result: A single TestResult or a list of TestResults.
        output_path: File path to write the HTML report to.

    Returns:
        Absolute path to the generated HTML file.

    Example:
        >>> from llm_browser_driver.report import write_html_report
        >>> write_html_report(result, "reports/test-report.html")
    """
    return generate_html_report(result, output_path)


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Run versioning and dashboard
# ---------------------------------------------------------------------------

def _create_run_directory(
    output_dir: Path,
    results: list[TestResult],
) -> Path:
    """Create a run-{timestamp} directory and return its path.

    Args:
        output_dir: The base results directory (e.g., "results/").
        results: List of TestResults for this run.

    Returns:
        Path to the run directory (e.g., results/run-2026-05-21T10-00-00/).
    """
    from datetime import datetime
    if len(results) == 1:
        run_label = results[0].test_name.lower().replace(" ", "-")[:40]
    else:
        run_label = "batch"

    ts = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    run_dir = output_dir / f"run-{ts}-{run_label}"
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def _copy_screenshots(
    run_dir: Path,
    result: TestResult,
) -> list[str]:
    """Copy screenshots from the agent's screenshot_dir to the run directory.

    Args:
        run_dir: The run directory to copy screenshots into.
        result: The TestResult containing screenshot metadata.

    Returns:
        List of relative paths to copied screenshots.
    """
    screenshots_copied: list[str] = []
    screenshot_dir = getattr(result, "_screenshot_dir", None)
    if not screenshot_dir or not Path(screenshot_dir).is_dir():
        return screenshots_copied

    dest_screenshots = run_dir / "screenshots"
    dest_screenshots.mkdir(parents=True, exist_ok=True)

    # Walk the screenshot directory and copy all PNGs
    for png_file in sorted(Path(screenshot_dir).glob("*.png")):
        dest = dest_screenshots / png_file.name
        dest.write_bytes(png_file.read_bytes())
        screenshots_copied.append(f"screenshots/{png_file.name}")

    return screenshots_copied


def _collect_runs(output_dir: Path) -> list[dict[str, Any]]:
    """Scan the output directory for all run-{timestamp}-* folders.

    Returns:
        List of dicts with keys: name, dir, started_at, test_name,
        passed, failed, total_steps, screenshots_count.
    """
    runs: list[dict[str, Any]] = []
    if not output_dir.is_dir():
        return runs

    for run_dir in sorted(output_dir.glob("run-*"), reverse=True):
        if not run_dir.is_dir():
            continue
        report_json = run_dir / "report.json"
        if not report_json.is_file():
            continue
        try:
            data = json.loads(report_json.read_text())
        except (json.JSONDecodeError, ValueError):
            continue

        tests = data.get("tests", [data]) if "tests" not in data else data["tests"]
        passed = sum(1 for t in tests if t.get("status") == "success")
        failed = sum(1 for t in tests if t.get("status") == "error")
        total_steps = sum(t.get("iterations", 0) for t in tests)

        screenshots_count = 0
        screenshots_dir = run_dir / "screenshots"
        if screenshots_dir.is_dir():
            screenshots_count = len(list(screenshots_dir.glob("*.png")))

        # Extract human-readable name from first test
        test_name = tests[0].get("test", "Unnamed") if tests else "Unnamed"

        runs.append({
            "name": run_dir.name,
            "dir": run_dir.name,
            "test_name": test_name,
            "started_at": _timestamp(),
            "passed": passed,
            "failed": failed,
            "total_steps": total_steps,
            "screenshots_count": screenshots_count,
        })

    return runs


def _generate_dashboard_html(
    output_dir: Path,
) -> Path:
    """Generate the central index.html dashboard listing all runs.

    The dashboard provides a table of all runs with pass/fail counts,
    step counts, and screenshot availability. Each row is a link to
    that run's report.html.

    Args:
        output_dir: The base results directory (e.g., "results/").

    Returns:
        Path to the generated index.html.
    """
    runs = _collect_runs(output_dir)
    total_tests = len(runs)
    total_passed = sum(r["passed"] for r in runs)
    total_failed = sum(r["failed"] for r in runs)

    run_rows = []
    for r in runs:
        status_color = "#2ea44f" if r["failed"] == 0 and r["passed"] > 0 else "#da3633" if r["failed"] > 0 else "#8b949e"
        screenshot_badge = f'{r["screenshots_count"]} screenshots' if r["screenshots_count"] > 0 else "No screenshots"
        run_rows.append(f'''
        <tr>
            <td><a href="{r['dir']}/report.html">{r['name']}</a></td>
            <td>{r['test_name']}</td>
            <td style="color: {status_color}; font-weight: 600;">
                {r['passed']} passed / {r['failed']} failed
            </td>
            <td>{r['total_steps']}</td>
            <td>{screenshot_badge}</td>
        </tr>''')

    dashboard_html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>LLM Browser Driver — Report Dashboard</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
            background: #0d1117;
            color: #c9d1d9;
            padding: 2rem;
        }}
        h1 {{
            color: #58a6ff;
            margin-bottom: 0.5rem;
        }}
        .subtitle {{
            color: #8b949e;
            margin-bottom: 2rem;
        }}
        .stats {{
            display: flex;
            gap: 2rem;
            margin-bottom: 2rem;
        }}
        .stat-card {{
            background: #161b22;
            border: 1px solid #30363d;
            border-radius: 6px;
            padding: 1rem 1.5rem;
            text-align: center;
        }}
        .stat-card .value {{
            font-size: 2rem;
            font-weight: 600;
        }}
        .stat-card .label {{
            font-size: 0.8rem;
            color: #8b949e;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
        }}
        th, td {{
            text-align: left;
            padding: 0.75rem 1rem;
            border-bottom: 1px solid #21262d;
        }}
        th {{
            color: #8b949e;
            font-weight: 500;
            font-size: 0.85rem;
            text-transform: uppercase;
        }}
        td a {{
            color: #58a6ff;
            text-decoration: none;
        }}
        td a:hover {{
            text-decoration: underline;
        }}
        tr:hover {{
            background: #161b22;
        }}
        @media (max-width: 768px) {{
            body {{ padding: 1rem; }}
            .stats {{ flex-wrap: wrap; gap: 1rem; }}
            .stat-card {{ flex: 1; min-width: 120px; }}
        }}
    </style>
</head>
<body>
    <h1>LLM Browser Driver — Report Dashboard</h1>
    <p class="subtitle">Generated {_timestamp()}</p>

    <div class="stats">
        <div class="stat-card">
            <div class="value">{total_tests}</div>
            <div class="label">Total Runs</div>
        </div>
        <div class="stat-card">
            <div class="value" style="color: #2ea44f;">{total_passed}</div>
            <div class="label">Passed</div>
        </div>
        <div class="stat-card">
            <div class="value" style="color: #f85149;">{total_failed}</div>
            <div class="label">Failed</div>
        </div>
    </div>

    <table>
        <thead>
            <tr>
                <th>Run</th>
                <th>Test</th>
                <th>Results</th>
                <th>Steps</th>
                <th>Evidence</th>
            </tr>
        </thead>
        <tbody>
{"".join(run_rows)}
        </tbody>
    </table>
</body>
</html>'''

    index_path = output_dir / "index.html"
    index_path.write_text(dashboard_html, encoding="utf-8")
    return index_path


# ---------------------------------------------------------------------------
# Batch report generation with run versioning
# ---------------------------------------------------------------------------

def generate_all_reports(
    result: TestResult | list[TestResult],
    output_dir: str | Path,
    *,
    formats: list[str] | None = None,
    include_dashboard: bool = True,
) -> dict[str, Path]:
    """Generate reports in a versioned run directory structure.

    Each call creates a new run-{timestamp} subdirectory under output_dir,
    writes all report formats there, copies screenshots, and updates
    a central dashboard index.html.

    Directory structure::

        results/
        ├── index.html                  # Dashboard listing all runs
        ├── run-2026-05-21T10-00-00-login/
        │   ├── report.json
        │   ├── report.html
        │   ├── report.md
        │   ├── report.xml
        │   └── screenshots/
        │       ├── step-1.png
        │       └── step-2.png
        └── run-2026-05-21T11-00-00-signup/
            └── ...

    Args:
        result: A single TestResult or a list of TestResults.
        output_dir: Base directory for results (e.g., "results/").
        formats: List of formats to generate. Options:
                 "json", "markdown", "html", "junit".
                 Defaults to all four.
        include_dashboard: Whether to generate/update the central
                          index.html dashboard. Default True.

    Returns:
        Dict mapping format name to output file path within the run dir,
        plus "dashboard" pointing to the central index.html.

    Example:
        >>> paths = generate_all_reports(result, "results/")
        >>> print(paths)
        {
            "json": Path("results/run-2026-05-21T10-00-00/login/report.json"),
            "markdown": Path(".../report.md"),
            "html": Path(".../report.html"),
            "junit": Path(".../report.xml"),
            "dashboard": Path("results/index.html"),
        }
    """
    if isinstance(result, TestResult):
        results = [result]
    else:
        results = list(result)

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Create run directory
    run_dir = _create_run_directory(output_dir, results)

    formats = formats or ["json", "markdown", "html", "junit"]
    paths: dict[str, Path] = {}

    for fmt in formats:
        if fmt == "json":
            path = run_dir / "report.json"
            path.write_text(generate_json(results), encoding="utf-8")
            paths["json"] = path
        elif fmt == "markdown":
            path = run_dir / "report.md"
            path.write_text(generate_markdown(results), encoding="utf-8")
            paths["markdown"] = path
        elif fmt == "html":
            path = run_dir / "report.html"
            generate_html_report(results, path, screenshot_base=run_dir)
            paths["html"] = path
        elif fmt == "junit":
            path = run_dir / "report.xml"
            path.write_text(generate_junit_xml(results), encoding="utf-8")
            paths["junit"] = path

    # Copy screenshots if present
    if results:
        _copy_screenshots(run_dir, results[0])

    # Generate/update dashboard
    if include_dashboard:
        dashboard_path = _generate_dashboard_html(output_dir)
        paths["dashboard"] = dashboard_path

    return paths


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def _html_escape(text: str) -> str:
    """Escape HTML special characters."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def _xml_escape(text: str) -> str:
    """Escape XML special characters."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )

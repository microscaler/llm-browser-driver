"""Tests for report generation, screenshot capture, run versioning, and dashboard.

Covers:
- generate_json / generate_markdown / generate_html_report / generate_junit_xml
- Screenshot display in HTML report (screenshot column, thumbnails)
- Run directory creation (_create_run_directory)
- Screenshot copying (_copy_screenshots)
- Dashboard generation (_generate_dashboard_html) and collection (_collect_runs)
- generate_all_reports with versioned structure
- CLI serve command (server startup, URL construction)
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from llm_browser_driver.agent import TestResult
from llm_browser_driver.report import (
    _collect_runs,
    _copy_screenshots,
    _create_run_directory,
    _generate_dashboard_html,
    generate_all_reports,
    generate_html_report,
    generate_json,
    generate_junit_xml,
    generate_markdown,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def single_result():
    """A single successful TestResult with screenshots."""
    return TestResult(
        test_name="Login Flow",
        url="http://localhost:3000",
        status="success",
        initial_url="http://localhost:3000",
        final_url="http://localhost:3000/dashboard",
        iterations=5,
        action_history=[
            {
                "step": 1,
                "action": "navigate",
                "parameters": {"url": "http://localhost:3000"},
                "result": "Navigated to login page",
                "url": "http://localhost:3000",
                "screenshot": "screenshots/step-1.png",
            },
            {
                "step": 2,
                "action": "fill",
                "parameters": {"field": "username", "value": "admin"},
                "result": "Filled username field",
                "url": "http://localhost:3000",
                "screenshot": "screenshots/step-2.png",
            },
            {
                "step": 3,
                "action": "click",
                "parameters": {"selector": "#login-btn"},
                "result": "Clicked login button",
                "url": "http://localhost:3000/dashboard",
            },
        ],
        console_errors=[
            {"type": "warning", "text": "Deprecated API call"}
        ],
        findings=[
            {
                "type": "info",
                "description": "Login successful",
            }
        ],
        time_taken=12.5,
        _screenshot_dir=None,  # Will be set in tests that need it
        _screenshots_taken=0,
    )


@pytest.fixture
def error_result():
    """A failed TestResult with error."""
    return TestResult(
        test_name="Broken Form",
        url="http://localhost:3000/broken",
        status="error",
        error="Element not found: #submit-btn",
        iterations=2,
        action_history=[
            {
                "step": 1,
                "action": "navigate",
                "parameters": {"url": "http://localhost:3000/broken"},
                "result": "Navigated",
                "url": "http://localhost:3000/broken",
            }
        ],
        time_taken=3.2,
    )


@pytest.fixture
def results_pair(single_result, error_result):
    """Two TestResults: one pass, one fail."""
    return [single_result, error_result]


# ---------------------------------------------------------------------------
# JSON report tests
# ---------------------------------------------------------------------------


class TestGenerateJSON:
    def test_single_result(self, single_result):
        json_str = generate_json(single_result)
        data = json.loads(json_str)

        assert data["total_tests"] == 1
        assert data["summary"]["passed"] == 1
        assert data["summary"]["failed"] == 0
        assert data["summary"]["total_iterations"] == 5
        assert len(data["tests"]) == 1
        assert data["tests"][0]["test"] == "Login Flow"

    def test_batch_results(self, results_pair):
        json_str = generate_json(results_pair)
        data = json.loads(json_str)

        assert data["total_tests"] == 2
        assert data["summary"]["passed"] == 1
        assert data["summary"]["failed"] == 1

    def test_action_screenshots_included(self, single_result):
        json_str = generate_json([single_result])
        data = json.loads(json_str)

        action = data["tests"][0]["action_history"][0]
        assert action["screenshot"] == "screenshots/step-1.png"


# ---------------------------------------------------------------------------
# Markdown report tests
# ---------------------------------------------------------------------------


class TestGenerateMarkdown:
    def test_single_result_markdown(self, single_result):
        md = generate_markdown(single_result)

        assert "# LLM Browser Driver" in md
        assert "## Summary" in md
        assert "Login Flow" in md
        assert "**Iterations:** 5" in md
        assert "12.5s" in md

    def test_markdown_includes_findings(self, single_result):
        md = generate_markdown(single_result)
        assert "Login successful" in md

    def test_markdown_includes_console_errors(self, single_result):
        md = generate_markdown(single_result)
        assert "Deprecated API call" in md


# ---------------------------------------------------------------------------
# HTML report tests
# ---------------------------------------------------------------------------


class TestGenerateHTMLReport:
    def test_generates_html_file(self, single_result, tmp_path):
        output_path = tmp_path / "report.html"
        result = generate_html_report(single_result, output_path)

        assert result == output_path
        assert result.is_file()
        html = result.read_text()
        assert "LLM Browser Driver" in html
        assert "Login Flow" in html

    def test_passing_status_styled_green(self, single_result, tmp_path):
        output_path = tmp_path / "report.html"
        generate_html_report(single_result, output_path)
        html = output_path.read_text()
        assert "#2ea44f" in html  # green
        assert "PASS" in html

    def test_failing_status_styled_red(self, error_result, tmp_path):
        output_path = tmp_path / "report.html"
        generate_html_report(error_result, output_path)
        html = output_path.read_text()
        assert "#da3633" in html  # red
        assert "FAIL" in html

    def test_screenshot_column_when_base_provided(self, single_result, tmp_path):
        """Screenshot column should appear when screenshot_base is set."""
        run_dir = tmp_path / "run-2026-05-21T10-00-00-login"
        run_dir.mkdir(parents=True)

        generate_html_report(
            single_result,
            run_dir / "report.html",
            screenshot_base=run_dir,
        )

        html = (run_dir / "report.html").read_text()
        # Should have screenshot thumbnail images
        assert "screenshots/step-1.png" in html
        assert "screenshots/step-2.png" in html
        assert 'class="screenshot-thumb"' in html
        assert '<th>Screenshot</th>' in html

    def test_no_screenshot_column_when_base_none(self, single_result, tmp_path):
        """No screenshot column when screenshot_base is None."""
        output_path = tmp_path / "report.html"
        generate_html_report(single_result, output_path, screenshot_base=None)

        html = output_path.read_text()
        # Should have the "-" placeholder but no actual screenshot images
        # (action_history entries without screenshot keys won't have images)


# ---------------------------------------------------------------------------
# JUnit XML report tests
# ---------------------------------------------------------------------------


class TestGenerateJUnitXML:
    def test_single_pass(self, single_result):
        xml = generate_junit_xml(single_result)
        assert '<?xml version="1.0"' in xml
        assert "Login Flow" in xml
        assert 'failures="0"' in xml

    def test_single_fail(self, error_result):
        xml = generate_junit_xml(error_result)
        assert 'failures="1"' in xml
        assert 'Element not found' in xml

    def test_batch(self, results_pair):
        xml = generate_junit_xml(results_pair)
        # Should contain both test names
        assert "Login Flow" in xml
        assert "Broken Form" in xml


# ---------------------------------------------------------------------------
# Run directory creation tests
# ---------------------------------------------------------------------------


class TestCreateRunDirectory:
    def test_creates_timestamped_directory(self, tmp_path):
        result = TestResult(
            test_name="Test Login Flow",
            url="http://example.com",
            status="success",
            iterations=1,
        )
        run_dir = _create_run_directory(tmp_path, [result])

        assert run_dir.is_dir()
        assert run_dir.name.startswith("run-")
        assert "test-login-flow" in run_dir.name

    def test_batch_uses_batch_label(self, tmp_path):
        results = [
            TestResult(
                test_name="Test A",
                url="http://a.com",
                status="success",
                iterations=1,
            ),
            TestResult(
                test_name="Test B",
                url="http://b.com",
                status="success",
                iterations=1,
            ),
        ]
        run_dir = _create_run_directory(tmp_path, results)
        assert "batch" in run_dir.name


# ---------------------------------------------------------------------------
# Screenshot copying tests
# ---------------------------------------------------------------------------


class TestCopyScreenshots:
    def test_copies_screenshots_from_agent_dir(self, tmp_path):
        # Simulate agent screenshot directory
        agent_screenshots = tmp_path / "agent-screenshots"
        agent_screenshots.mkdir()
        (agent_screenshots / "step-1.png").write_bytes(b"fake-png-1")
        (agent_screenshots / "step-2.png").write_bytes(b"fake-png-2")

        result = TestResult(
            test_name="Test",
            url="http://test.com",
            status="success",
            iterations=2,
            _screenshot_dir=str(agent_screenshots),
            _screenshots_taken=2,
        )
        run_dir = tmp_path / "run-dir"
        run_dir.mkdir()

        copied = _copy_screenshots(run_dir, result)

        assert len(copied) == 2
        assert "screenshots/step-1.png" in copied
        assert "screenshots/step-2.png" in copied
        assert (run_dir / "screenshots/step-1.png").is_file()
        assert (run_dir / "screenshots/step-2.png").is_file()

    def test_no_op_when_no_screenshot_dir(self, tmp_path):
        result = TestResult(
            test_name="Test",
            url="http://test.com",
            status="success",
            iterations=1,
            _screenshot_dir=None,
        )
        run_dir = tmp_path / "run-dir"
        run_dir.mkdir()

        copied = _copy_screenshots(run_dir, result)
        assert copied == []

    def test_no_op_when_dir_doesnt_exist(self, tmp_path):
        result = TestResult(
            test_name="Test",
            url="http://test.com",
            status="success",
            iterations=1,
            _screenshot_dir="/nonexistent/path",
        )
        run_dir = tmp_path / "run-dir"
        run_dir.mkdir()

        copied = _copy_screenshots(run_dir, result)
        assert copied == []


# ---------------------------------------------------------------------------
# Dashboard generation tests
# ---------------------------------------------------------------------------


class TestDashboardGeneration:
    def test_generates_index_html(self, tmp_path):
        # Create a mock run directory with report.json
        run_dir = tmp_path / "run-2026-05-21T10-00-00-login"
        run_dir.mkdir(parents=True)
        (run_dir / "report.json").write_text(
            json.dumps({
                "tests": [
                    {
                        "test": "Login Flow",
                        "status": "success",
                        "iterations": 5,
                    }
                ]
            })
        )
        (run_dir / "screenshots").mkdir()
        (run_dir / "screenshots" / "step-1.png").write_bytes(b"fake")

        index_path = _generate_dashboard_html(tmp_path)

        assert index_path == tmp_path / "index.html"
        assert index_path.is_file()
        html = index_path.read_text()
        assert "LLM Browser Driver" in html
        assert "Login Flow" in html

    def test_dashboard_shows_pass_fail_counts(self, tmp_path):
        run_dir = tmp_path / "run-2026-05-21T10-00-00-login"
        run_dir.mkdir(parents=True)
        (run_dir / "report.json").write_text(
            json.dumps({
                "tests": [
                    {"test": "Login", "status": "success", "iterations": 5},
                    {"test": "Register", "status": "error", "iterations": 2},
                ]
            })
        )

        index_path = _generate_dashboard_html(tmp_path)
        html = index_path.read_text()

        assert "1 passed / 1 failed" in html
        assert 'style="color: #f85149;"' in html  # red for failures


# ---------------------------------------------------------------------------
# Run collection tests
# ---------------------------------------------------------------------------


class TestCollectRuns:
    def test_collects_multiple_runs(self, tmp_path):
        # Create two runs
        for name in ["run-2026-01-01T00-00-00-a", "run-2026-01-02T00-00-00-b"]:
            run_dir = tmp_path / name
            run_dir.mkdir(parents=True)
            (run_dir / "report.json").write_text(
                json.dumps({"tests": [{"test": "Test", "status": "success", "iterations": 1}]})
            )

        runs = _collect_runs(tmp_path)

        assert len(runs) == 2
        assert runs[0]["name"] == "run-2026-01-02T00-00-00-b"  # reverse chronological

    def test_skips_missing_report_json(self, tmp_path):
        run_dir = tmp_path / "run-2026-01-01T00-00-00-test"
        run_dir.mkdir(parents=True)
        # No report.json!

        runs = _collect_runs(tmp_path)
        assert len(runs) == 0

    def test_returns_empty_for_nonexistent_dir(self):
        runs = _collect_runs(Path("/nonexistent/path"))
        assert runs == []


# ---------------------------------------------------------------------------
# generate_all_reports integration tests
# ---------------------------------------------------------------------------


class TestGenerateAllReports:
    def test_creates_run_directory_structure(self, single_result, tmp_path):
        paths = generate_all_reports(single_result, tmp_path / "results")

        # Should have dashboard
        assert "dashboard" in paths
        assert paths["dashboard"].is_file()

        # Should have run directory
        run_dirs = list((tmp_path / "results").glob("run-*"))
        assert len(run_dirs) == 1
        run_dir = run_dirs[0]

        # Should have report files
        assert (run_dir / "report.json").is_file()
        assert (run_dir / "report.html").is_file()
        assert (run_dir / "report.md").is_file()
        assert (run_dir / "report.xml").is_file()

        # Should have dashboard at base
        assert (tmp_path / "results" / "index.html").is_file()

    def test_generates_all_formats(self, single_result, tmp_path):
        paths = generate_all_reports(
            single_result,
            tmp_path / "results",
            formats=["json", "markdown", "html", "junit"],
        )

        for fmt in ["json", "markdown", "html", "junit"]:
            assert fmt in paths
            assert paths[fmt].is_file()

    def test_omits_formats_when_specified(self, single_result, tmp_path):
        paths = generate_all_reports(
            single_result,
            tmp_path / "results",
            formats=["json", "html"],
        )

        assert "json" in paths
        assert "html" in paths
        assert "markdown" not in paths
        assert "junit" not in paths

    def test_excludes_dashboard_when_requested(self, single_result, tmp_path):
        paths = generate_all_reports(
            single_result,
            tmp_path / "results",
            include_dashboard=False,
        )

        assert "dashboard" not in paths
        assert not (tmp_path / "results" / "index.html").is_file()

    def test_copies_screenshots_with_report(self, tmp_path):
        # Create agent screenshot dir
        agent_dir = tmp_path / "agent-screenshots"
        agent_dir.mkdir()
        (agent_dir / "step-1.png").write_bytes(b"fake-png")

        result = TestResult(
            test_name="Login",
            url="http://test.com",
            status="success",
            iterations=1,
            action_history=[
                {
                    "step": 1,
                    "action": "navigate",
                    "parameters": {},
                    "result": "OK",
                    "url": "http://test.com",
                    "screenshot": "screenshots/step-1.png",
                }
            ],
            _screenshot_dir=str(agent_dir),
            _screenshots_taken=1,
        )

        paths = generate_all_reports(result, tmp_path / "results")

        # Find the run directory
        run_dirs = list((tmp_path / "results").glob("run-*"))
        assert len(run_dirs) == 1
        run_screenshots = run_dirs[0] / "screenshots"
        assert run_screenshots.is_dir()
        assert (run_screenshots / "step-1.png").is_file()

    def test_html_report_has_screenshot_thumbnails(self, single_result, tmp_path):
        paths = generate_all_reports(single_result, tmp_path / "results")

        # The run dir
        run_dirs = list((tmp_path / "results").glob("run-*"))
        assert len(run_dirs) == 1
        run_dir = run_dirs[0]

        # HTML should reference screenshots from action_history
        html = (run_dir / "report.html").read_text()
        assert "screenshots/step-1.png" in html
        assert "screenshots/step-2.png" in html


# ---------------------------------------------------------------------------
# CLI serve command tests
# ---------------------------------------------------------------------------


class TestServeCommand:
    def test_serve_requires_directory(self, tmp_path):
        """Serve command should fail gracefully on missing directory."""
        from click.testing import CliRunner
        from llm_browser_driver.cli import serve_cmd

        runner = CliRunner()
        result = runner.invoke(serve_cmd, ["--directory", "/nonexistent"])

        assert result.exit_code == 1
        assert "not found" in result.output.lower()

    def test_serve_warns_without_index(self, tmp_path):
        """Serve should warn if no index.html exists but directory does."""
        results_dir = tmp_path / "results"
        results_dir.mkdir()

        from click.testing import CliRunner
        from llm_browser_driver.cli import serve_cmd
        from unittest.mock import patch, MagicMock

        runner = CliRunner()

        # Mock the server to not actually start, just verify it gets to the right point
        with patch("http.server.HTTPServer") as MockServer:
            mock_server = MagicMock()
            MockServer.return_value = mock_server

            # Patch serve_forever to return immediately after setup
            def fake_serve_forever():
                pass

            mock_server.serve_forever = fake_serve_forever

            # Patch webbrowser.open to do nothing
            with patch("webbrowser.open"):
                result = runner.invoke(
                    serve_cmd,
                    ["--directory", str(results_dir), "--no-open"],
                )

        assert "No index.html" in result.output

    def test_serve_starts_server(self, tmp_path):
        """Serve command should start an HTTP server on the given port."""
        results_dir = tmp_path / "results"
        results_dir.mkdir()
        (results_dir / "index.html").write_text("<html></html>")

        from click.testing import CliRunner
        from llm_browser_driver.cli import serve_cmd
        from unittest.mock import patch, MagicMock

        runner = CliRunner()

        with patch("http.server.HTTPServer") as MockServer:
            mock_server = MagicMock()
            MockServer.return_value = mock_server

            def fake_serve_forever():
                pass

            mock_server.serve_forever = fake_serve_forever

            with patch("webbrowser.open"):
                result = runner.invoke(
                    serve_cmd,
                    ["--directory", str(results_dir), "--port", "8765", "--no-open"],
                )

        assert "Report server started" in result.output
        assert "http://127.0.0.1:8765/" in result.output
        # Verify HTTPServer was created with the right address and handler
        MockServer.assert_called_once()
        call_args = MockServer.call_args
        # call_args[0] = positional args: (address, handler_class)
        address = call_args[0][0]
        assert address == ("127.0.0.1", 8765)


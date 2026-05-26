"""Tests for CI/CD integration module.

Covers:
- RunManifest creation and serialization
- manifest.json save/load round-trip
- upload_to_s3 rejection when source doesn't exist
- compare_runs with mock run directories
- format_diff_report output structure
"""

from __future__ import annotations

import json
import pathlib
import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from llm_browser_driver.cicd import (
    RunManifest,
    create_manifest,
    load_manifest,
    upload_to_s3,
    compare_runs,
    format_diff_report,
)


# ---------------------------------------------------------------------------
# Manifest tests
# ---------------------------------------------------------------------------


class TestRunManifest:
    def test_defaults(self):
        m = RunManifest()
        assert m.version == "1.0"
        assert m.commit_sha != "unknown"
        assert m.branch != "unknown"
        assert m.model_provider == ""
        assert m.model_name == ""
        assert m.test_count == 0
        assert m.passed == 0
        assert m.failed == 0
        assert m.skipped == 0
        assert m.report_files == []
        assert m.screenshot_count == 0

    def test_to_dict(self):
        m = RunManifest(
            model_name="qwen3",
            model_provider="openrouter",
            test_count=10,
            passed=8,
            failed=2,
        )
        d = m.to_dict()
        assert d["model_name"] == "qwen3"
        assert d["model_provider"] == "openrouter"
        assert d["test_count"] == 10
        assert d["passed"] == 8
        assert d["failed"] == 2

    def test_save_and_load(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest_path = Path(tmpdir) / "manifest.json"
            m = RunManifest(
                model_name="claude-sonnet-4",
                model_provider="anthropic",
                test_count=5,
                passed=4,
                failed=1,
            )
            m.save(manifest_path)

            # Verify file was written
            assert manifest_path.exists()
            with open(manifest_path) as f:
                data = json.load(f)
            assert data["model_name"] == "claude-sonnet-4"
            assert data["test_count"] == 5

            # Load it back
            loaded = load_manifest(manifest_path)
            assert loaded.model_name == "claude-sonnet-4"
            assert loaded.test_count == 5
            assert loaded.passed == 4
            assert loaded.failed == 1


class TestCreateManifest:
    def test_creates_and_saves(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest = create_manifest(
                output_dir=tmpdir,
                model_name="qwen3",
                model_provider="openrouter",
                test_count=12,
                passed=11,
                failed=1,
            )
            assert manifest.model_name == "qwen3"
            assert manifest.test_count == 12
            assert manifest.passed == 11
            assert manifest.failed == 1
            assert (Path(tmpdir) / "manifest.json").exists()


# ---------------------------------------------------------------------------
# S3 upload tests
# ---------------------------------------------------------------------------


class TestUploadToS3:
    def test_raises_on_missing_source(self):
        with pytest.raises(FileNotFoundError):
            upload_to_s3("./nonexistent", "my-bucket")

    def test_raises_without_boto3_or_aws_cli(self):
        """When neither boto3 nor aws CLI is available, raise RuntimeError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create an empty file to upload
            Path(tmpdir, "test.txt").write_text("hello")

            # Patch at the module level where boto3 and subprocess are imported
            with patch.dict("sys.modules", {"boto3": None}):
                # Invalidate the import cache for cicd so boto3 reimport fails
                import importlib
                import llm_browser_driver.cicd as cicd_mod
                original_boto3 = cicd_mod.__dict__.get("boto3")
                cicd_mod.__dict__["boto3"] = None

                try:
                    with patch.object(cicd_mod.subprocess, "run") as mock_run:
                        mock_run.side_effect = FileNotFoundError("no aws")
                        with pytest.raises(RuntimeError, match="neither boto3 nor aws CLI"):
                            cicd_mod.upload_to_s3(tmpdir, "my-bucket")
                finally:
                    # Restore
                    if original_boto3 is not None:
                        cicd_mod.__dict__["boto3"] = original_boto3
                    elif "boto3" in cicd_mod.__dict__:
                        del cicd_mod.__dict__["boto3"]


# ---------------------------------------------------------------------------
# Compare runs tests
# ---------------------------------------------------------------------------


class TestCompareRuns:
    @pytest.fixture
    def old_run_dir(self, tmp_path):
        """Create a run directory with old results."""
        report = {
            "results": [
                {"name": "login", "status": "success", "findings": ["form validated correctly"]},
                {"name": "signup", "status": "success", "findings": []},
                {"name": "navigation", "status": "success", "findings": []},
            ],
        }
        (tmp_path / "report.json").write_text(json.dumps(report))
        return tmp_path

    @pytest.fixture
    def new_run_dir(self):
        """Create a separate run directory with new results."""
        report = {
            "results": [
                {"name": "login", "status": "failure", "findings": ["email field missing"]},
                {"name": "signup", "status": "success", "findings": []},
                {"name": "navigation", "status": "success", "findings": ["footer links broken"]},
                {"name": "checkout", "status": "success", "findings": []},
            ],
        }
        path = pathlib.Path(tempfile.mkdtemp())
        (path / "report.json").write_text(json.dumps(report))
        yield path
        shutil.rmtree(path, ignore_errors=True)

    def test_detects_regressions(self, old_run_dir, new_run_dir):
        diff = compare_runs(old_run_dir, new_run_dir)
        assert len(diff["regressions"]) == 1
        assert diff["regressions"][0]["test"] == "login"
        assert diff["regressions"][0]["old_status"] == "success"
        assert diff["regressions"][0]["new_status"] == "failure"

    def test_detects_improvements(self, old_run_dir, new_run_dir):
        """If signup went from failure to success, it should show as improvement."""
        # Modify old to have signup failure
        report = {
            "results": [
                {"name": "login", "status": "success", "findings": []},
                {"name": "signup", "status": "failure", "findings": []},
            ],
        }
        old_run_dir.joinpath("report.json").write_text(json.dumps(report))

        # New has signup success
        new_report = {
            "results": [
                {"name": "login", "status": "success", "findings": []},
                {"name": "signup", "status": "success", "findings": []},
            ],
        }
        new_run_dir.joinpath("report.json").write_text(json.dumps(new_report))

        diff = compare_runs(old_run_dir, new_run_dir)
        assert any(r["test"] == "signup" for r in diff["improvements"])

    def test_detects_new_findings(self, old_run_dir, new_run_dir):
        diff = compare_runs(old_run_dir, new_run_dir)
        assert "footer links broken" in diff["new_findings"]
        assert "email field missing" in diff["new_findings"]

    def test_detects_removed_findings(self, old_run_dir, new_run_dir):
        diff = compare_runs(old_run_dir, new_run_dir)
        assert "form validated correctly" in diff["removed_findings"]

    def test_detects_new_tests(self, old_run_dir, new_run_dir):
        diff = compare_runs(old_run_dir, new_run_dir)
        assert any(t["test"] == "checkout" for t in diff["new_tests"])

    def test_confidence_score(self, old_run_dir, new_run_dir):
        diff = compare_runs(old_run_dir, new_run_dir)
        # 3 tests compared (login, signup, navigation) + 1 new (checkout)
        # login failed in new (regression), signup stable, navigation stable
        # 2/3 stable = 0.67
        assert 0.0 <= diff["confidence_score"] <= 1.0

    def test_no_regressions(self, old_run_dir, new_run_dir):
        """If both runs are identical, no regressions and confidence = 1.0."""
        # Copy the old report to the new run directory
        shutil.copy(old_run_dir / "report.json", new_run_dir / "report.json")
        diff = compare_runs(old_run_dir, new_run_dir)
        assert len(diff["regressions"]) == 0
        assert diff["confidence_score"] == 1.0

    def test_missing_report_json(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            compare_runs(tmp_path, tmp_path)


# ---------------------------------------------------------------------------
# format_diff_report tests
# ---------------------------------------------------------------------------


class TestFormatDiffReport:
    def test_format_with_regressions(self):
        diff = {
            "regressions": [{"test": "login", "old_status": "success", "new_status": "failure"}],
            "improvements": [],
            "new_tests": [],
            "removed_tests": [],
            "new_findings": ["email field missing"],
            "removed_findings": [],
            "confidence_score": 0.67,
        }
        report = format_diff_report(diff)
        assert "=== Browser Test Diff Report ===" in report
        assert "Confidence Score: 0.67" in report
        assert "Regressions (1):" in report
        assert "login: success -> failure" in report
        assert "New Findings (1):" in report
        assert "email field missing" in report

    def test_format_clean(self):
        diff = {
            "regressions": [],
            "improvements": [],
            "new_tests": [],
            "removed_tests": [],
            "new_findings": [],
            "removed_findings": [],
            "confidence_score": 1.0,
        }
        report = format_diff_report(diff)
        assert "No regressions" in report

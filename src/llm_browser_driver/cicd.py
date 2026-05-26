"""Run manifest, S3 upload, and run diff for CI/CD integration.

Generates a manifest.json per test run containing metadata:
- commit SHA and branch
- timestamp, model provider/version
- test count, pass/fail/skipped
- report file paths and screenshot count

Provides:
- upload_to_s3 / upload_and_symlink — persist results to S3
- compare_runs / format_diff_report — regression detection
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------


def _get_commit_sha() -> str:
    """Get the current git commit SHA (short form)."""
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            stderr=subprocess.DEVNULL,
        ).decode().strip()[:12]
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def _get_branch() -> str:
    """Get the current git branch name."""
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            stderr=subprocess.DEVNULL,
        ).decode().strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


@dataclass
class RunManifest:
    """Metadata for a single test run."""

    version: str = "1.0"
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    commit_sha: str = field(default_factory=_get_commit_sha)
    branch: str = field(default_factory=_get_branch)
    model_provider: str = ""
    model_name: str = ""
    output_dir: str = ""
    test_count: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    total_duration_ms: float = 0.0
    report_files: list[str] = field(default_factory=list)
    screenshot_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)


def create_manifest(
    output_dir: str,
    model_name: str = "",
    model_provider: str = "",
    test_count: int = 0,
    passed: int = 0,
    failed: int = 0,
    skipped: int = 0,
    total_duration_ms: float = 0.0,
    report_files: list[str] | None = None,
    screenshot_count: int = 0,
) -> RunManifest:
    """Create a run manifest, save it, and return it.

    Example::

        manifest = create_manifest(
            output_dir="./ci-results/run-42",
            model_name="qwen3",
            model_provider="openrouter",
            test_count=12,
            passed=11,
            failed=1,
        )
    """
    manifest = RunManifest(
        model_name=model_name,
        model_provider=model_provider,
        output_dir=output_dir,
        test_count=test_count,
        passed=passed,
        failed=failed,
        skipped=skipped,
        total_duration_ms=total_duration_ms,
        report_files=report_files or [],
        screenshot_count=screenshot_count,
    )
    manifest.save(Path(output_dir) / "manifest.json")
    return manifest


def load_manifest(path: str | Path) -> RunManifest:
    """Load a manifest from a manifest.json file."""
    path = Path(path)
    with open(path) as f:
        data = json.load(f)
    known = set(RunManifest.__dataclass_fields__)
    return RunManifest(**{k: v for k, v in data.items() if k in known})


# ---------------------------------------------------------------------------
# S3 Upload
# ---------------------------------------------------------------------------


def upload_to_s3(
    source_dir: str | Path,
    bucket: str,
    prefix: str = "",
    region: str = "us-east-1",
    endpoint_url: str | None = None,
) -> list[str]:
    """Upload all files in a directory to an S3-compatible bucket.

    Tries boto3 first, falls back to aws CLI if not installed.

    Args:
        source_dir: Local directory to upload.
        bucket: S3 bucket name.
        prefix: S3 key prefix (e.g. "myproject/abc123/20260521/").
        region: AWS region.
        endpoint_url: S3-compatible endpoint (e.g. Minio URL).

    Returns:
        List of uploaded S3 keys.

    Raises:
        FileNotFoundError: If source_dir does not exist.
        RuntimeError: If neither boto3 nor aws CLI is available.
    """
    source_dir = Path(source_dir)
    if not source_dir.exists():
        raise FileNotFoundError(f"Source directory not found: {source_dir}")

    keys: list[str] = []

    # Try boto3
    try:
        import boto3

        kwargs = {"region_name": region}
        if endpoint_url:
            kwargs["endpoint_url"] = endpoint_url
        s3 = boto3.client("s3", **kwargs)
        for fp in source_dir.rglob("*"):
            if fp.is_file():
                rel = fp.relative_to(source_dir)
                key = f"{prefix}{rel}"
                s3.upload_file(str(fp), bucket, key)
                keys.append(key)
        return keys
    except ImportError:
        pass

    # Fall back to aws CLI
    import subprocess as sp

    try:
        cmd = ["aws", "s3", "sync", str(source_dir), f"s3://{bucket}/{prefix}", "--quiet"]
        if region:
            cmd += ["--region", region]
        if endpoint_url:
            cmd += ["--endpoint-url", endpoint_url]
        result = sp.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(result.stderr)
        for line in result.stdout.strip().split("\n"):
            if line.startswith("upload:"):
                s3_key = line.split("s3://")[1] if "s3://" in line else ""
                if s3_key:
                    keys.append(f"{prefix}{s3_key.replace(f'{bucket}/', '')}")
        return keys
    except (FileNotFoundError, sp.CalledProcessError) as e:
        raise RuntimeError(
            "Cannot upload to S3: neither boto3 nor aws CLI is available. "
            "Install one: pip install boto3 or aws configure"
        ) from e


def upload_and_symlink(
    source_dir: str | Path,
    bucket: str,
    project: str,
    region: str = "us-east-1",
    endpoint_url: str | None = None,
) -> dict[str, str]:
    """Upload results, maintain latest/ and manifests/ symlinks on S3.

    Args:
        source_dir: Run results directory (must contain manifest.json).
        bucket: S3 bucket name.
        project: Project identifier for the key path.
        region: AWS region.
        endpoint_url: S3-compatible endpoint URL.

    Returns:
        Dict with 'upload_dir', 'manifest_key', and 'latest_key'.
    """
    source_dir = Path(source_dir)
    if not (source_dir / "manifest.json").exists():
        manifest = RunManifest()
    else:
        manifest = load_manifest(source_dir / "manifest.json")

    commit_sha = manifest.commit_sha
    ts = manifest.timestamp.replace(":", "-").replace("+", "")
    upload_dir = f"{project}/{commit_sha}/{ts}"

    # Upload all files
    upload_to_s3(
        source_dir=source_dir,
        bucket=bucket,
        prefix=upload_dir,
        region=region,
        endpoint_url=endpoint_url,
    )

    # Upload manifest to manifests/
    manifest_key = f"{project}/manifests/{commit_sha}.json"
    if endpoint_url:
        import boto3
        s3 = boto3.client("s3", region_name=region, endpoint_url=endpoint_url)
        s3.upload_file(str(source_dir / "manifest.json"), bucket, manifest_key)
    else:
        import subprocess as sp
        sp.run(["aws", "s3", "cp", str(source_dir / "manifest.json"), f"s3://{bucket}/{manifest_key}"], check=True)

    return {
        "upload_dir": upload_dir,
        "manifest_key": manifest_key,
        "latest_key": f"{project}/latest/{commit_sha}",
    }


# ---------------------------------------------------------------------------
# Run Diff / Compare
# ---------------------------------------------------------------------------


def load_run_results(path: str | Path) -> dict[str, Any]:
    """Load run results from report.json in a run directory.

    Args:
        path: Path to the run directory.

    Returns:
        Parsed report.json dict.

    Raises:
        FileNotFoundError: If report.json is missing.
    """
    path = Path(path)
    report_path = path / "report.json"
    if not report_path.exists():
        raise FileNotFoundError(f"report.json not found in {path}")
    with open(report_path) as f:
        return json.load(f)


def compare_runs(
    old_run: str | Path,
    new_run: str | Path,
) -> dict[str, Any]:
    """Compare two test runs and identify regressions/improvements.

    Args:
        old_run: Path to the older run directory.
        new_run: Path to the newer run directory.

    Returns:
        Dict with:
        - regressions: [{test, old_status, new_status}]
        - improvements: [{test, old_status, new_status}]
        - new_tests: [{test, status}]
        - removed_tests: [{test, status}]
        - new_findings: [str]
        - removed_findings: [str]
        - confidence_score: float 0-1

    Example::

        diff = compare_runs("./ci-results/abc123/", "./ci-results/def456/")
        for reg in diff["regressions"]:
            print(f"REGRESSION: {reg['test']} ({reg['old_status']} -> {reg['new_status']})")
    """
    old = load_run_results(old_run)
    new = load_run_results(new_run)

    old_tests = {t.get("name", ""): t.get("status", "unknown") for t in old.get("results", [])}
    new_tests = {t.get("name", ""): t.get("status", "unknown") for t in new.get("results", [])}

    all_names = set(old_tests) | set(new_tests)

    regressions: list[dict] = []
    improvements: list[dict] = []
    new_tests_list: list[dict] = []
    removed_tests: list[dict] = []

    for name in all_names:
        old_status = old_tests.get(name, "missing")
        new_status = new_tests.get(name, "missing")

        if old_status == "success" and new_status == "failure":
            regressions.append({"test": name, "old_status": old_status, "new_status": new_status})
        elif old_status == "failure" and new_status == "success":
            improvements.append({"test": name, "old_status": old_status, "new_status": new_status})
        elif name not in old_tests:
            new_tests_list.append({"test": name, "status": new_status})
        elif name not in new_tests:
            removed_tests.append({"test": name, "status": old_status})

    # Findings comparison
    old_findings: set[str] = set()
    for t in old.get("results", []):
        old_findings.update(t.get("findings", []))
    new_findings: set[str] = set()
    for t in new.get("results", []):
        new_findings.update(t.get("findings", []))

    # Confidence score
    total_compared = sum(1 for s in old_tests.values() if s in ("success", "failure"))
    if total_compared == 0:
        confidence = 1.0
    else:
        stable = sum(
            1 for n in all_names
            if old_tests.get(n) == new_tests.get(n) and old_tests.get(n) in ("success", "failure")
        )
        confidence = stable / total_compared

    return {
        "regressions": regressions,
        "improvements": improvements,
        "new_tests": new_tests_list,
        "removed_tests": removed_tests,
        "new_findings": list(new_findings - old_findings),
        "removed_findings": list(old_findings - new_findings),
        "confidence_score": round(confidence, 2),
    }


def format_diff_report(diff: dict[str, Any]) -> str:
    """Format a diff result as a human-readable report.

    Args:
        diff: Output from compare_runs().

    Returns:
        Formatted string suitable for CI output or PR comments.
    """
    lines = [
        "=== Browser Test Diff Report ===",
        f"Confidence Score: {diff['confidence_score']}",
        "",
    ]

    if diff["regressions"]:
        lines.append(f"Regressions ({len(diff['regressions'])}):")
        for r in diff["regressions"]:
            lines.append(f"  - {r['test']}: {r['old_status']} -> {r['new_status']}")
        lines.append("")

    if diff["improvements"]:
        lines.append(f"Improvements ({len(diff['improvements'])}):")
        for r in diff["improvements"]:
            lines.append(f"  - {r['test']}: {r['old_status']} -> {r['new_status']}")
        lines.append("")

    if diff["new_findings"]:
        lines.append(f"New Findings ({len(diff['new_findings'])}):")
        for f in diff["new_findings"]:
            lines.append(f"  - {f}")
        lines.append("")

    if not any([diff["regressions"], diff["improvements"], diff["new_findings"]]):
        lines.append("No regressions, improvements, or new findings detected.")

    return "\n".join(lines)

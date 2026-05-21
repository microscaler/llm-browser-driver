# PRD: Rich Report Viewer with Run History & Visual Evidence

**Status:** Draft
**Created:** 2026-05-21
**Context:** Extending `llm-browser-driver` to provide a rich, interactive reporting experience with screenshot support and test run versioning.

---

## 1. Problem Statement

The current reporting mechanism (`report.py`) generates static HTML, JSON, and Markdown files. While functional, it lacks:
1.  **Visual Evidence**: No screenshot capture on errors or at key steps, making debugging difficult.
2.  **Versioning**: No way to compare current runs against previous runs to identify regressions.
3.  **Browsing**: Users must open individual files rather than navigating a hierarchical report dashboard.
4.  **Server-less Viewing**: Complex JS-heavy reports often fail when opened via `file://` due to browser security policies (CORS, local file restrictions).

## 2. Goal

Create a **Rich Report Viewer** system that:
- Captures screenshots on test failures (and configurable intervals).
- Organizes test results into versioned "runs" with a consistent directory structure.
- Provides a static, self-contained HTML viewer that handles screenshots and navigation.
- Supports a local `serve` command to view reports via HTTP (avoiding `file://` limitations).
- Allows users to "tab through" historical runs and compare results.

---

## 3. Functional Requirements

### 3.1. Artifact Directory Structure
The system must produce a standardized directory structure:

```text
results/
├── index.html                # Global dashboard listing all runs
├── run-2026-05-21T10-00-00/  # Run 1 (timestamped folder)
│   ├── report.json           # Machine-readable data
│   ├── report.html           # Single-page app for this run
│   ├── summary.md            # Human-readable markdown
│   └── screenshots/          # Screenshots for this run
│       ├── step-1.png
│       ├── step-2.png
│       └── failure-step-5.png
└── run-2026-05-21T11-00-00/  # Run 2
    └── ...
```

### 3.2. Run Versioning
- Every CLI execution (or batch) creates a new folder named `run-{ISO_TIMESTAMP}`.
- The dashboard (`results/index.html`) lists all runs in reverse chronological order.
- Users can select a specific run to view its details.

### 3.3. Screenshot Capture
- **On Failure**: Automatically capture a screenshot when an action fails or a page error occurs.
- **Sampling**: Capture screenshots at regular intervals (e.g., every N steps) via CLI flag `--screenshot-every N`.
- **Storage**: Screenshots are stored as PNGs in the run's `screenshots/` directory.
- **Reference**: `TestResult` objects will store relative paths to screenshots (e.g., `screenshots/step-1.png`) in their metadata.

### 3.4. Static HTML Viewer
- **No External Server Required**: The viewer must be a static HTML/JS file (SPAs) that reads data from the JSON file.
- **Dashboard (`index.html`)**:
    - Scans the `results/` directory for run folders.
    - Displays a list of runs with summary stats (pass/fail counts, time).
    - Clicking a run loads its `report.html`.
- **Run View (`report.html`)**:
    - Displays a table of actions/steps.
    - Collapsible sections for detailed logs, console errors, and findings.
    - **Screenshot Modal/Inline**: Clicking a screenshot step expands it inline or opens a modal.
    - Handles CORS issues by using local file access (Blob URLs) if possible, or requiring the `serve` command for full features.

### 3.5. CLI Commands
- `llm-browser-driver run --url ... --output results/` (Existing `explore` command, enhanced to use the new artifact structure).
- `llm-browser-driver serve --directory results/`
    - Starts a lightweight Python HTTP server.
    - Opens `results/index.html` in the default browser.
    - Supports file watching (optional) to refresh if artifacts update.

---

## 4. Technical Design

### 4.1. Report Data Format (`report.json`)
We will extend the JSON schema to include artifact paths.

```json
{
  "run_id": "2026-05-21T10-00-00",
  "run_name": "Login Flow Test",
  "started_at": "2026-05-21T10:00:00Z",
  "duration_seconds": 14.2,
  "status": "success",
  "summary": {
    "steps": 45,
    "failures": 0,
    "screenshots_taken": 12
  },
  "steps": [
    {
      "id": 1,
      "action": "navigate",
      "target": "http://localhost:3000",
      "screenshot": "screenshots/step-1.png",
      "success": true,
      "details": "Loaded page in 1.2s"
    },
    {
      "id": 5,
      "action": "click",
      "target": "#login-btn",
      "screenshot": "screenshots/step-5.png",
      "success": true,
      "details": "Clicked button"
    }
  ]
}
```

### 4.2. HTML Viewer Implementation
- **Vanilla JS**: No React/Vue dependency to keep it "static overlay" friendly.
- **Data Loading**: Uses `fetch('report.json')` or parses `<script>` embedded JSON for `file://` compatibility.
- **UI Library**: Use a lightweight CSS framework (like Tailwind via CDN or minimal custom CSS) to avoid bloat.
- **Navigation**:
    - **Dashboard**: Grid of cards (one per run).
    - **Run View**: Vertical timeline of steps. Screenshot thumbnails align with steps.

### 4.3. Server Component (`serve` command)
- A simple Python `http.server` wrapper.
- Serves the `results/` directory as root.
- Sets appropriate headers for static assets.

---

## 5. Non-Functional Requirements

- **Performance**: The viewer must load and render a 500-step run in under 1 second.
- **Portability**: The `results/` directory must be copyable to another machine and `index.html` must still work (assuming images are included).
- **Extensibility**: The JSON schema must allow adding new fields (e.g., console logs, network traces) without breaking the viewer.

---

## 6. Implementation Phases

### Phase 1: Artifact Structure & Screenshot Capture
- Update `agent.py` to accept `output_dir`.
- Implement screenshot capture logic (on failure + interval).
- Update `TestResult` to store screenshot metadata.

### Phase 2: Rich Report Generator
- Update `report.py` to write the `report.json` and HTML viewer template.
- Implement the dashboard generator (`index.html` listing runs).
- Implement the run viewer (`report.html` with screenshot modal).

### Phase 3: CLI Integration & Serve Command
- Add `serve` subcommand to `cli.py`.
- Ensure `results/` structure is created and populated correctly.
- Add tests for the report generation logic.

### Phase 4: Polish
- Add dark/light mode toggle to the viewer.
- Add "Export to PDF" functionality (using browser print).
- Add filtering capabilities (search steps by text).

---

## 7. Future Considerations

- **Network Trace**: Capture HAR files (HTTP traffic) and visualize them in the viewer.
- **Video Recording**: Playwright can record videos; we can embed these as `<video>` tags in the report.
- **CI/CD Integration**: Generate a link or artifact bundle for CI systems (GitHub Actions, etc.).

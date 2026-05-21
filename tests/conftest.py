"""Pytest configuration and fixtures for llm-browser-driver tests.

Provides:
- Mock LLM responses (no real LLM calls in CI)
- Configuration fixtures for unit tests
- Test page fixtures for integration tests
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from playwright.sync_api import sync_playwright

# ---------------------------------------------------------------------------
# Fixtures: Mock LLM
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_llm_response():
    """Generate a mock LLM response parser fixture.

    Yields a function that wraps parse_action_from_response with canned responses.
    """
    def _make(response_text: str):
        """Create a patched version of parse_action_from_response."""
        with patch(
            "llm_browser_driver.agent.parse_action_from_response",
            return_value=json.loads(response_text),
        ):
            yield
    return _make


@pytest.fixture
def mock_llm_client():
    """Fixture to patch LLMClient.chat() with canned responses.

    Usage:
        @pytest.mark.usefixtures("mock_llm_client")
        def test_something(mock_llm_client):
            mock_llm_client.side_effect = [
                '{"action": "click", "element": "Sign In"}',
                '{"action": "done", "summary": "Done"}',
            ]
    """
    from unittest.mock import patch, MagicMock

    responses = []
    call_count = 0

    def set_responses(responses_list: list[str]):
        nonlocal responses
        responses = responses_list

    def mock_chat(*args: Any, **kwargs: Any) -> str:
        nonlocal call_count
        if call_count < len(responses):
            result = responses[call_count]
            call_count += 1
            return result
        return '{"action": "done", "summary": "Max iterations reached"}'

    with patch("llm_browser_driver.agent.LLMClient") as MockLLM:
        mock = MagicMock()
        mock.chat = mock_chat
        mock.model = "test-model"
        mock.streaming = False
        MockLLM.return_value = mock
        mock.set_responses = set_responses
        yield mock


@pytest.fixture
def sample_page_state() -> dict[str, Any]:
    """Sample page state for testing build_page_summary()."""
    return {
        "title": "Test Page",
        "url": "http://localhost:7174",
        "viewport": {"width": 1280, "height": 720},
        "forms": {
            "input_count": 3,
            "textarea_count": 0,
            "button_count": 2,
            "dropdown_count": 1,
            "disabled_count": 0,
            "image_count": 1,
        },
        "details": {
            "inputs": [
                {
                    "type": "email",
                    "name": "email",
                    "placeholder": "Email",
                    "aria_label": "Email address",
                    "id": "email-input",
                    "disabled": False,
                    "readonly": False,
                    "value": "",
                },
                {
                    "type": "password",
                    "name": "password",
                    "placeholder": "Password",
                    "aria_label": "Password",
                    "id": "password-input",
                    "disabled": False,
                    "readonly": False,
                    "value": "",
                },
            ],
            "textareas": [],
            "buttons": [
                {
                    "text": "Sign In",
                    "aria_label": "",
                    "type": "submit",
                    "disabled": False,
                    "role": "",
                },
                {
                    "text": "Reset",
                    "aria_label": "",
                    "type": "reset",
                    "disabled": False,
                    "role": "",
                },
            ],
            "links": [
                {
                    "text": "Sign Up",
                    "href": "/signup",
                    "aria_label": "",
                    "target": "",
                },
            ],
            "images": [
                {
                    "alt": "Logo",
                    "src": "/logo.png",
                    "aria_label": "",
                },
            ],
            "selects": [
                {
                    "name": "country",
                    "id": "country-select",
                    "disabled": False,
                    "options": [
                        {"text": "United States", "value": "US", "selected": True},
                        {"text": "Canada", "value": "CA", "selected": False},
                    ],
                },
            ],
            "form_fields": [
                {"text": "Email address", "for": "email-input"},
                {"text": "Password", "for": "password-input"},
            ],
            "disabled_elements": [],
        },
        "console": [
            {"type": "warning", "text": "Deprecated API called"},
        ],
        "accessibility_tree": {
            "method": "native",
            "children": [
                {"role": "heading", "name": "Sign In", "expanded": None, "disabled": None, "tag": "h1"},
                {"role": "textbox", "name": "Email address", "expanded": None, "disabled": None, "tag": "input"},
                {"role": "textbox", "name": "Password", "expanded": None, "disabled": None, "tag": "input"},
                {"role": "button", "name": "Sign In", "expanded": None, "disabled": None, "tag": "button"},
            ],
        },
    }


# ---------------------------------------------------------------------------
# Fixtures: Test HTML pages (for integration tests against real Playwright)
# ---------------------------------------------------------------------------

@pytest.fixture
def test_html_dir(tmp_path: Path) -> Path:
    """Create temporary test HTML pages for integration tests.

    Returns path to a directory with sample HTML pages.
    """
    # Home page
    (tmp_path / "index.html").write_text("""
<!DOCTYPE html>
<html>
<head><title>Test Home</title></head>
<body>
    <h1 id="hero-title">Welcome to TestApp</h1>
    <nav id="header-nav">
        <a href="/signin" id="nav-signin">Sign In</a>
        <a href="/signup" id="nav-signup">Sign Up</a>
    </nav>
    <form id="search-form">
        <input type="text" id="search-input" name="q" placeholder="Search...">
        <button type="submit" id="search-btn">Search</button>
    </form>
    <button id="theme-toggle">Toggle Theme</button>
    <select id="lang-select" name="lang">
        <option value="en">English</option>
        <option value="fr">French</option>
    </select>
    <a href="/nonexistent" id="broken-link">Broken Link</a>
</body>
</html>
""")

    # Sign-in page
    (tmp_path / "signin.html").write_text("""
<!DOCTYPE html>
<html>
<head><title>Sign In</title></head>
<body>
    <h1>Sign In</h1>
    <form id="signin-form">
        <label for="email">Email address</label>
        <input type="email" id="email" name="email" placeholder="email@example.com" aria-label="Email address">
        <label for="password">Password</label>
        <input type="password" id="password" name="password" placeholder="Enter password" aria-label="Password">
        <button type="submit" id="signin-btn">Sign In</button>
        <a href="/signup">Create account</a>
    </form>
    <div id="error-message" style="display:none;">Invalid credentials</div>
</body>
</html>
""")

    # Form with complex fields
    (tmp_path / "form.html").write_text("""
<!DOCTYPE html>
<html>
<head><title>Test Form</title></head>
<body>
    <h1>Registration Form</h1>
    <form id="register-form">
        <label for="first-name">First Name</label>
        <input type="text" id="first-name" name="first_name" placeholder="John">

        <label for="last-name">Last Name</label>
        <input type="text" id="last-name" name="last_name" placeholder="Doe">

        <label for="user-email">Email</label>
        <input type="email" id="user-email" name="email" placeholder="john@example.com">

        <label for="user-password">Password</label>
        <input type="password" id="user-password" name="password" placeholder="Min 8 characters">

        <label for="country-select">Country</label>
        <select id="country-select" name="country">
            <option value="">Select...</option>
            <option value="US">United States</option>
            <option value="CA">Canada</option>
            <option value="UK">United Kingdom</option>
        </select>

        <label for="bio">Bio</label>
        <textarea id="bio" name="bio" rows="3" placeholder="Tell us about yourself"></textarea>

        <button type="submit" id="submit-btn">Register</button>
    </form>
</body>
</html>
""")

    return tmp_path


# ---------------------------------------------------------------------------
# Fixtures: Config with minimal settings
# ---------------------------------------------------------------------------

@pytest.fixture
def minimal_config():
    """Minimal config for unit tests (no file I/O, no network)."""
    from llm_browser_driver.config import AppConfig, LLMConfig, AgentConfig, BrowserConfig

    return AppConfig(
        llm=LLMConfig(
            api_url="http://test:8000/v1",
            model="test-model",
            max_tokens=512,
            temperature=0.3,
            timeout=30,
        ),
        agent=AgentConfig(max_iterations=5, max_actions_per_step=1, max_failures=1),
        browser=BrowserConfig(headless=True, viewport_width=800, viewport_height=600, timeout=5000),
    )


@pytest.fixture
def browser_instance():
    """Provide a headless browser instance for integration tests."""
    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=True)
    yield browser
    browser.close()
    pw.stop()


@pytest.fixture
def browser_page(browser_instance):
    """Provide a fresh page for integration tests."""
    context = browser_instance.new_context(
        viewport={"width": 800, "height": 600},
    )
    page = context.new_page()
    yield page
    page.close()
    context.close()

"""LLM Browser Driver — Autonomous AI-driven web testing and exploration.

Combines Playwright's browser automation with an LLM's ability to understand
and navigate pages without hardcoded selectors.

Key differentiator: Zero selector maintenance. The LLM discovers elements
the way a human does — by labels, text content, and structure.

Basic usage:

    from llm_browser_driver import BrowserDriver

    driver = BrowserDriver(
        llm_api_url="http://localhost:8000/v1",
        llm_model="qwen3",
    )

    result = driver.explore(
        url="http://myapp.com",
        goal="Test the user registration flow",
        max_iterations=30,
    )

    print(result["findings"])
"""

from llm_browser_driver.agent import BrowserDriver

__version__ = "0.1.0"
__all__ = ["BrowserDriver"]

"""Example 1: Basic exploratory testing.

Navigate to a URL and let the LLM explore it autonomously.

Usage:
    python example_basic.py
"""

from llm_browser_driver import BrowserDriver

# Configure driver — point to any /v1/chat/completions endpoint
driver = BrowserDriver(
    llm_api_url="http://localhost:8000/v1",
    llm_model="qwen3",
    max_tokens=2048,
    temperature=0.3,
    headless=True,
)

# Run an exploratory test
result = driver.explore(
    url="http://example.com",
    goal="Explore the page and report on available links and content",
    max_iterations=10,
)

# Print results
print(f"Status: {result.status}")
print(f"Iterations: {result.iteration}")

if result.findings:
    print("\nFindings:")
    for finding in result.findings:
        print(f"  - {finding}")

if result.console_errors:
    print("\nConsole Errors:")
    for err in result.console_errors:
        print(f"  - {err}")

if result.screenshots:
    print(f"\nScreenshots captured: {len(result.screenshots)}")
    for path in result.screenshots:
        print(f"  - {path}")

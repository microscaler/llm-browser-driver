"""Example 2: Form filling and submission.

Test a login form by navigating to it, filling fields, and submitting.

Usage:
    python example_form_filling.py
"""

from llm_browser_driver import BrowserDriver

driver = BrowserDriver(
    llm_api_url="http://localhost:8000/v1",
    llm_model="qwen3",
    max_tokens=2048,
    temperature=0.3,
    headless=True,
)

# Explore a login page and fill out the form
result = driver.explore(
    url="http://localhost:3000/login",
    goal=(
        "Find the login form. Fill in the email field with test@example.com, "
        "fill in the password field with TestPass123, click Submit, "
        "and verify you see a welcome message or redirect to dashboard"
    ),
    max_iterations=15,
)

print(f"Status: {result.status}")
print(f"Findings: {result.findings}")
print(f"Console Errors: {result.console_errors}")

# Show screenshots
if result.screenshots:
    print(f"\nScreenshots ({len(result.screenshots)}):")
    for s in result.screenshots:
        print(f"  {s}")

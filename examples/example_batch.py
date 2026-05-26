"""Example 4: Batch testing with multiple scenarios.

Run multiple predefined test scenarios and collect results with reports.

Usage:
    python example_batch.py
"""

import json
from llm_browser_driver import BrowserDriver

# Define batch test scenarios
test_scenarios = [
    {
        "name": "Homepage loads correctly",
        "url": "http://localhost:3000",
        "goal": "Verify the homepage loads with a heading, navigation links, and footer",
        "max_iterations": 10,
    },
    {
        "name": "Login form visible",
        "url": "http://localhost:3000/login",
        "goal": "Find the login form, verify it has email and password fields, and a submit button",
        "max_iterations": 10,
    },
    {
        "name": "Navigation works",
        "url": "http://localhost:3000",
        "goal": "Click the 'About' or 'Contact' link in the navigation, verify page loads correctly",
        "max_iterations": 15,
    },
]

# Configure the driver
driver = BrowserDriver(
    llm_api_url="http://localhost:8000/v1",
    llm_model="qwen3",
    max_tokens=2048,
    temperature=0.3,
    headless=True,
)

# Run all scenarios
results = []
for i, scenario in enumerate(test_scenarios, 1):
    print(f"\n{'='*60}")
    print(f"Scenario {i}/{len(test_scenarios)}: {scenario['name']}")
    print(f"{'='*60}")

    result = driver.explore(
        url=scenario["url"],
        goal=scenario["goal"],
        max_iterations=scenario["max_iterations"],
    )

    results.append({
        "name": scenario["name"],
        "url": scenario["url"],
        "status": result.status,
        "iterations": result.iteration,
        "findings": result.findings,
        "console_errors": result.console_errors,
        "screenshots": result.screenshots,
    })

    print(f"  Status: {result.status}")
    print(f"  Iterations: {result.iteration}")
    print(f"  Findings: {len(result.findings)}")

# Save results to JSON
output = {
    "test_suite": "regression",
    "total": len(results),
    "passed": sum(1 for r in results if r["status"] == "success"),
    "failed": sum(1 for r in results if r["status"] != "success"),
    "results": results,
}

with open("batch-results.json", "w") as f:
    json.dump(output, f, indent=2)

print(f"\n{'='*60}")
print(f"Results saved to batch-results.json")
print(f"Passed: {output['passed']}/{output['total']}")
print(f"{'='*60}")

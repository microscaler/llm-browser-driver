"""Example 3: Spec-driven testing from OpenAPI.

Parse an OpenAPI spec, map endpoints to pages, and run tests against a staging site.

Usage:
    python example_spec_driven.py
"""

from llm_browser_driver import BrowserDriver
from llm_browser_driver.spec_parser import SpecParser

# Define an OpenAPI spec (or load from file)
openapi_spec = {
    "openapi": "3.0.3",
    "info": {"title": "Test API", "version": "1.0.0"},
    "paths": {
        "/api/v1/auth/signin": {
            "post": {
                "summary": "Sign in",
                "requestBody": {
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "required": ["email", "password"],
                                "properties": {
                                    "email": {"type": "string"},
                                    "password": {"type": "string"},
                                },
                            }
                        }
                    }
                },
            }
        },
        "/api/v1/users": {
            "get": {
                "summary": "List users",
            }
        },
    },
}

# Parse the spec
parser = SpecParser(spec_dict=openapi_spec)

print(f"Total endpoints: {parser.get_endpoint_count()}")
print(f"Body endpoints: {len(parser.get_body_endpoints())}")

# Define endpoint-to-page mapping
mapping = {
    "POST /api/v1/auth/signin": "/login",
}

# Define test data
test_data = {
    "POST /api/v1/auth/signin": {
        "email": "test@example.com",
        "password": "TestPass123",
    }
}

# Generate test goals
goals = parser.generate_goals(
    base_url="http://localhost:3000",
    mapping=mapping,
    test_data=test_data,
)

print(f"\nGenerated {len(goals)} test goal(s):")
for i, goal in enumerate(goals, 1):
    print(f"\nGoal {i}:")
    print(f"  Endpoint: {goal['endpoint']}")
    print(f"  Goal: {goal['goal']}")
    print(f"  Page URL: {goal['page_url']}")
    if goal.get("test_data"):
        print(f"  Test Data: {goal['test_data']}")

# Now run the first goal through the browser driver
if goals:
    first_goal = goals[0]
    driver = BrowserDriver(
        llm_api_url="http://localhost:8000/v1",
        llm_model="qwen3",
        max_tokens=2048,
        temperature=0.3,
        headless=True,
    )

    result = driver.explore(
        url=first_goal["page_url"],
        goal=first_goal["goal"],
        max_iterations=15,
    )

    print(f"\nTest result: {result.status}")
    print(f"Findings: {result.findings}")

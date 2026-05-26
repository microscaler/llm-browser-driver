"""Example 5: Retry and recovery patterns.

Demonstrate automatic retry with exponential backoff and recovery strategies.

Usage:
    python example_retry.py
"""

from llm_browser_driver.retry import RetryConfig, retry_action

# Simulate a flaky executor (fails intermittently)
call_count = 0

def flaky_executor(action):
    """Simulate a flaky action executor."""
    global call_count
    call_count += 1
    
    if action["action"] == "click":
        # First 2 attempts fail, 3rd succeeds
        if call_count <= 2:
            return (False, None, "Element not found")
        return (True, "clicked", None)
    
    if action["action"] in ("wait", "scroll", "evaluate"):
        # Recovery actions always succeed
        return (True, None, None)
    
    return (False, None, f"Unknown action: {action['action']}")

# Configure retry with aggressive backoff for testing
config = RetryConfig(
    max_retries=5,
    backoff_base=0.1,
    max_delay=1.0,
    recovery_actions=["wait", "scroll", "refresh"],
)

print("Running flaky action with retry...")
result = retry_action(flaky_executor, {"action": "click", "parameters": {}}, config)

print(f"\nResult:")
print(f"  Success: {result.success}")
print(f"  Attempts: {result.attempt}")
print(f"  Retries used: {result.retries_used}")
print(f"  Total duration: {result.total_duration_ms:.1f}ms")
print(f"  Error: {result.error}")

# Verify recovery worked
assert result.success, "Should succeed after recovery"
print("\n✓ Recovery succeeded after flaky failures!")

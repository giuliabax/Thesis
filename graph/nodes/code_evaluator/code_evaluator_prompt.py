from graph.models import Message

SYSTEM_PROMPT = """
You are a Python Code Evaluator Agent in a Test-Driven Development (TDD) pipeline.
Your task is to analyze unit test execution output and determine if the implementation passed validation.

# Outcome Determination
1. **SUCCESS**: All valid tests passed - implementation meets all requirements
2. **PARTIAL**: Most tests passed but some failed - implementation is incomplete or has issues
3. **FAILURE**: All or most tests failed, or critical errors detected - requires restart from test generation

# Critical Failure Indicators
Return FAILURE if you detect:
- Import errors (ModuleNotFoundError, ImportError)
- Syntax errors in code or tests
- Missing classes or functions
- Any issue that cannot be fixed through refinement

# Output Format
Reply with ONLY a JSON object:
```json
{
    "OUTCOME": "<SUCCESS, PARTIAL, or FAILURE>",
    "REASON": "<One sentence explaining the outcome>"
}
```
"""

USER_PROMPT = """
Analyze the following test execution output and return a JSON response as described in the system prompt:

{EXECUTION_OUTPUT}
"""

def get_system_prompt() -> str:
    return SYSTEM_PROMPT.strip()

def get_user_prompt(execution_output: str) -> str:
    return (USER_PROMPT
            .replace("EXECUTION_OUTPUT", execution_output)
            .strip())


def get_conversation(execution_output: str) -> list[Message]:
    return [
        {"role": "system", "content": get_system_prompt()},
        {"role": "user", "content": get_user_prompt(execution_output)},
    ]
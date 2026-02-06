## LangChain UI Test Spec Pipeline

This document describes the **LangChain-based AI engine** that generates UI test specifications for the platform. It assumes that **UI context** and **requirements** are already preprocessed and passed into the engine in a specific format.

The output of this engine is a **strict JSON test spec** that downstream components (e.g. Selenium/pytest code generator) can consume.

---

## 1. High-Level Workflow

At a high level, the pipeline looks like this:

1. **Upstream ingestion (outside this module)**
   - Use Selenium (or another crawler) to open the target URL and produce a structured `ui_context` JSON:
     - Page URL, title, and a list of interactive elements (buttons, links, inputs, etc.).
   - Parse product documentation into:
     - `functional_requirements` – things the UI must do.
     - `non_functional_requirements` – performance, accessibility, UX expectations.
     - `user_flow_context` – high-level descriptions of main flows.

2. **LangChain UI Test Spec Engine (this module)**
   - Takes `ui_context` and the three requirement lists as input.
   - Uses a **system prompt** that understands Selenium’s capabilities/limits.
   - Uses a **developer prompt** that enforces:
     - JSON-only output.
     - Allowed actions.
     - Realistic UI flows and assertions.
   - Calls an LLM via LangChain with **structured output** (Pydantic).
   - Validates test steps against the UI context (no unknown targets or invalid actions).
   - If validation fails, retries once with a dedicated **retry prompt**.

3. **Downstream test generator (outside this module)**
   - Converts the `TestSpec` JSON into executable Selenium/pytest code.
   - Uses its own templates/fixtures and standard waits for robust execution.

---

## 2. Expected Input Format

The public API of the engine is the `UITestEngineInput` dataclass in `langchain_ui_test_pipeline.py`:

```python
from dataclasses import dataclass
from typing import Any, Dict, List

@dataclass
class UITestEngineInput:
    ui_context: Dict[str, Any]
    functional_requirements: List[str]
    non_functional_requirements: List[str]
    user_flow_context: List[str]
```

### 2.1 `ui_context` structure

`ui_context` is a JSON-like dictionary (serializable to JSON) that summarizes the target page. A typical example:

```json
{
  "page_url": "https://example.com/login",
  "title": "Example App – Login",
  "elements": [
    {
      "id": "email_input",
      "name": "email",
      "data_testid": "login-email",
      "label": "Email address",
      "role": "input"
    },
    {
      "id": "password_input",
      "name": "password",
      "data_testid": "login-password",
      "label": "Password",
      "role": "input"
    },
    {
      "id": "login_button",
      "name": "submit",
      "data_testid": "login-submit",
      "label": "Log in",
      "role": "button"
    }
  ]
}
```

**Notes:**

- The engine treats any of `id`, `name`, `data_testid`, `label`, or `identifier` as potential **logical targets**.
- During validation, every `step.target` in the test spec must match one of these values; otherwise the spec is rejected and retried.

### 2.2 Requirements lists

The three requirement lists are free-form text arrays:

```json
functional_requirements = [
  "User must be able to log in with valid email and password and reach the dashboard.",
  "Login form should prevent submission when email is missing."
]

non_functional_requirements = [
  "Login should complete within 3 seconds in normal conditions.",
  "Error messages must be clearly visible and accessible."
]

user_flow_context = [
  "Standard login flow from the main navigation login button.",
  "Most users come from a marketing landing page before logging in."
]
```

These strings are concatenated into sections in the final prompt, keeping responsibility for **structuring** on the LLM with tight guidance.

---

## 3. Output Format

The engine returns a `TestSpec` Pydantic model (also serializable to JSON) with the following shape:

```python
from typing import List, Optional
from pydantic import BaseModel

class TestStep(BaseModel):
    action: str          # navigate | type | click | assert_visible | assert_text | assert_url_contains | assert_disabled
    target: Optional[str] = None
    value: Optional[str] = None

class TestSpec(BaseModel):
    test_name: str
    description: str
    steps: List[TestStep]
```

Example JSON output:

```json
{
  "test_name": "Successful user login",
  "description": "Verify that a user can log in with valid credentials and reach the dashboard.",
  "steps": [
    { "action": "navigate", "value": "/login" },
    { "action": "type", "target": "email_input", "value": "valid_email" },
    { "action": "type", "target": "password_input", "value": "valid_password" },
    { "action": "click", "target": "login_button" },
    { "action": "assert_url_contains", "value": "/dashboard" }
  ]
}
```

This JSON is intended to be **directly consumed** by a downstream test generator that maps:

- `target` → element locator strategy (CSS/XPath/etc.).
- `action` → concrete Selenium calls.
- `value` → input values or assertions.

---

## 4. Code-Level API

The main entry point is the `run_langchain_ui_test_pipeline` function:

```python
from langchain_openai import ChatOpenAI
from langchain_ui_test_pipeline import (
    UITestEngineInput,
    run_langchain_ui_test_pipeline,
)

llm = ChatOpenAI(
    model="gpt-4.1-mini",
    temperature=0.0,
)

payload = UITestEngineInput(
    ui_context=ui_context_dict,
    functional_requirements=functional_requirements,
    non_functional_requirements=non_functional_requirements,
    user_flow_context=user_flow_context,
)

test_spec = run_langchain_ui_test_pipeline(llm, payload)
```

- **Arguments:**
  - `llm`: Any LangChain `BaseChatModel` (e.g. `ChatOpenAI`, `ChatAnthropic`, local model wrapper).
  - `payload`: `UITestEngineInput` instance with the four fields above.
  - `max_retries` (optional keyword): how many times to retry with the corrective prompt if validation fails (default: `1`).

- **Returns:**
  - A `TestSpec` instance that has already passed:
    - Pydantic validation (schema and allowed actions).
    - Target validation against `ui_context["elements"]`.

---

## 5. Internal Workflow Details

Inside `run_langchain_ui_test_pipeline`:

1. **Serialization**
   - `ui_context` is serialized to `ui_context_json` (string).
   - Requirement lists are joined into multi-line strings.

2. **Primary generation chain**
   - `build_test_spec_chain(llm)` creates a `Runnable` that:
     - Applies the **system** and **developer** prompts.
     - Injects `ui_context_json` and requirement sections into the user prompt.
     - Uses `llm.with_structured_output(TestSpec)` so the result is parsed into a Pydantic model.

3. **Validation**
   - `validate_targets_against_context` checks that every `step.target` (if present) exists in the `ui_context["elements"]` set.
   - If there are no elements, the spec must not reference any targets.

4. **Retry on failure**
   - On `ValidationError` (schema) or `ValueError` (invalid targets), the engine:
     - Builds a secondary `retry_chain` with `RETRY_PROMPT`.
     - Passes `validation_errors` plus the original context and requirements.
     - Reinvokes the LLM to repair its own output.

5. **Return**
   - On success, the validated `TestSpec` is returned to the caller for code generation.

---

## 6. How Selenium Fits In

Selenium is not called directly by this module, but it is assumed to be used **upstream** to construct `ui_context`. A typical pattern:

1. Use Selenium (headless browser) to:
   - Load the target URL.
   - Discover interactive elements and their attributes (`id`, `name`, `data-testid`, etc.).
2. Convert discovered elements into the `ui_context["elements"]` list described above.
3. Pass this `ui_context` dictionary, along with requirement lists, into `run_langchain_ui_test_pipeline`.
4. Use the resulting `TestSpec` to generate Selenium tests that:
   - Map logical targets to concrete locators.
   - Implement actions (`click`, `type`, etc.) and assertions.

This separation ensures:

- The LLM **understands Selenium’s capabilities and limits** (via prompts).
- Test specs remain **framework-agnostic and deterministic**.
- Runtime behavior (locators, waits, retries) is controlled in your own test runner.


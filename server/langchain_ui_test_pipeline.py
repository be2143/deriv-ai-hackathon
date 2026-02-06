"""
LangChain-based pipeline for generating structured UI test specifications.

Assumptions:
- Upstream components (e.g. Selenium crawler and doc parser) provide:
  - A structured UI context JSON describing the page.
  - Requirements already split into functional / non-functional / user-flow lists.
- This module focuses purely on:
  - Prompting the LLM with that structured context.
  - Enforcing a strict JSON schema for the test spec.
  - Validating that actions and targets are realistic for Selenium-style automation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set

from pydantic import BaseModel, Field, ValidationError, field_validator

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable


# ---------------------------------------------------------------------------
# Input / output data structures
# ---------------------------------------------------------------------------


@dataclass
class UITestEngineInput:
    """
    Canonical input format for the LangChain UI test spec engine.

    This is the shape expected by the public API in this module.
    Compatible with output from ai_input_processor.py.
    """

    ui_context: Dict[str, Any]
    functional_requirements: List[str]
    non_functional_requirements: List[str]
    user_flow_context: List[str]
    overview: Optional[str] = None
    frontend_features: Optional[List[str]] = None


class TestStep(BaseModel):
    action: str = Field(
        ...,
        description="High-level UI action or assertion (navigate, type, click, assert_visible, assert_text, assert_url_contains, assert_disabled).",
    )
    target: Optional[str] = Field(
        None,
        description="Logical element identifier from the UI context (e.g. 'login_button').",
    )
    value: Optional[str] = Field(
        None,
        description="Optional value to type or expected text/URL fragment.",
    )

    @field_validator("action")
    @classmethod
    def validate_action(cls, v: str) -> str:
        allowed = {
            "navigate",
            "type",
            "click",
            "assert_visible",
            "assert_text",
            "assert_url_contains",
            "assert_disabled",
        }
        if v not in allowed:
            raise ValueError(f"Invalid action '{v}'. Allowed: {sorted(allowed)}")
        return v


class TestSpec(BaseModel):
    test_name: str
    description: str
    steps: List[TestStep]


class TestSuite(BaseModel):
    """A comprehensive suite of test cases."""
    test_cases: List[TestSpec] = Field(
        ...,
        description="List of test cases covering different scenarios, user flows, and edge cases",
        min_length=1,
    )


# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------


SYSTEM_PROMPT = """
You are a senior QA automation engineer specializing in frontend UI and UX testing.
You deeply understand the capabilities and limitations of Selenium-based browser automation
(e.g. what can or cannot be asserted reliably, typical flakiness causes, and how real browsers behave).

You do NOT generate executable code.
You do NOT reference Selenium, Playwright, or any testing framework APIs by name in your output.

You reason about WHAT to test, not HOW to implement it, but your choices must be realistic
for Selenium-based UI automation (no impossible actions, no assertions that require information
a browser cannot observe).
""".strip()


DEVELOPER_PROMPT = """
Follow these rules strictly:

1. Output must be valid JSON and nothing else.
2. Do not include explanations, comments, or markdown.
3. Generate a COMPREHENSIVE suite of test cases covering:
   - Happy path scenarios (primary user flows)
   - Edge cases (empty inputs, boundary conditions)
   - Error scenarios (invalid inputs, error handling)
   - UI validation (form validation, disabled states)
   - Navigation flows (page transitions, links)
   - Different user roles or states if applicable
4. Use only the allowed action types:
   - navigate
   - type
   - click
   - assert_visible
   - assert_text
   - assert_url_contains
   - assert_disabled

5. All "target" fields must reference element identifiers provided in the UI context.
6. Every test must include at least one assertion.
7. Prefer end-user flows over isolated element checks.
8. Do not invent UI elements or actions not present in the UI context.
9. Generate 5-15 test cases depending on the complexity of the UI and requirements.

Additionally, ensure all actions and assertions are realistic for Selenium-based browser automation:
- Do not assert on backend-only state or database content.
- Do not read network traffic or console logs unless explicitly present in the UI context.
- Avoid brittle timing assumptions; rely on visible/enabled states and URL changes.
""".strip()


USER_PROMPT = """
{overview_section}UI CONTEXT (JSON):
{ui_context_json}

{frontend_features_section}FUNCTIONAL REQUIREMENTS:
{functional_requirements}

NON-FUNCTIONAL REQUIREMENTS:
{non_functional_requirements}

USER FLOW CONTEXT:
{user_flow_context}

Generate a COMPREHENSIVE suite of UI test cases covering:
- Happy path scenarios (primary user flows)
- Edge cases (empty inputs, boundary conditions, invalid data)
- Error scenarios (validation errors, error messages)
- UI validation (form validation, disabled states, visibility)
- Navigation flows (page transitions, links, redirects)
- Different scenarios based on the requirements and UI context

Output must follow this JSON schema exactly:
{{
  "test_cases": [
    {{
      "test_name": string,
      "description": string,
      "steps": [
        {{
          "action": string,
          "target": string (optional),
          "value": string (optional)
        }}
      ]
    }}
  ]
}}

Generate 5-15 test cases depending on the complexity. Ensure test names are descriptive and unique.
""".strip()


#
# NOTE: All literal braces below are escaped as {{ and }} so that
# LangChain does not interpret them as template variables.
#
RETRY_PROMPT = """
The previous output was invalid.

Errors:
{validation_errors}

{overview_section}UI CONTEXT (JSON):
{ui_context_json}

{frontend_features_section}FUNCTIONAL REQUIREMENTS:
{functional_requirements}

NON-FUNCTIONAL REQUIREMENTS:
{non_functional_requirements}

USER FLOW CONTEXT:
{user_flow_context}

Correct the output so that:
- It is valid JSON.
- It strictly follows the schema.
- It uses only allowed actions.
- It references only elements from the UI context.
- It includes a comprehensive suite of test cases (5-15 test cases).

Return ONLY the corrected JSON, in this shape:
{{
  "test_cases": [
    {{
      "test_name": string,
      "description": string,
      "steps": [
        {{
          "action": string,
          "target": string (optional),
          "value": string (optional)
        }}
      ]
    }}
  ]
}}
""".strip()


# ---------------------------------------------------------------------------
# Chain construction
# ---------------------------------------------------------------------------


def build_test_spec_chain(llm: BaseChatModel) -> Runnable:
    """
    Build the LangChain Runnable that generates a TestSuite from structured inputs.

    The runnable expects a dict with keys:
      - ui_context_json (str)
      - functional_requirements (str)
      - non_functional_requirements (str)
      - user_flow_context (str)
      - overview_section (str, optional) - formatted overview text
      - frontend_features_section (str, optional) - formatted frontend features text
    """
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", SYSTEM_PROMPT),
            ("system", DEVELOPER_PROMPT),
            ("user", USER_PROMPT),
        ]
    )

    # Use structured output so we get a Pydantic TestSuite back directly.
    chain: Runnable = prompt | llm.with_structured_output(TestSuite)
    return chain


def build_retry_chain(llm: BaseChatModel) -> Runnable:
    """
    Build the LangChain Runnable used to correct invalid outputs.
    """
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", SYSTEM_PROMPT),
            ("system", DEVELOPER_PROMPT),
            ("user", RETRY_PROMPT),
        ]
    )
    chain: Runnable = prompt | llm.with_structured_output(TestSuite)
    return chain


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def extract_allowed_targets(ui_context: Dict[str, Any]) -> Set[str]:
    """
    Compute the set of valid element identifiers from the UI context.

    Expected UI context example (simplified):
    {
      "page_url": "...",
      "elements": [
        {
          "id": "email_input",
          "name": "email",
          "data_testid": "email-input",
          "label": "Email",
          "role": "input"
        },
        ...
      ]
    }
    """
    allowed: Set[str] = set()
    for el in ui_context.get("elements", []):
        for key in ("id", "name", "data_testid", "label", "identifier"):
            val = el.get(key)
            if isinstance(val, str) and val.strip():
                allowed.add(val.strip())
    return allowed


def validate_targets_against_context(test_spec: TestSpec, ui_context: Dict[str, Any]) -> None:
    """
    Ensure that any step.target in the TestSpec references an element
    that exists in the UI context.
    """
    allowed_targets = extract_allowed_targets(ui_context)
    if not allowed_targets:
        # If there are no elements, no steps should reference targets.
        bad_steps = [s for s in test_spec.steps if s.target]
        if bad_steps:
            raise ValueError("UI context has no elements but some steps reference targets.")
        return

    invalid_targets = [
        step.target
        for step in test_spec.steps
        if step.target and step.target not in allowed_targets
    ]
    if invalid_targets:
        unique = sorted(set(invalid_targets))
        raise ValueError(
            f"Unknown targets in test steps: {unique}. "
            f"Allowed targets are derived from UI context: {sorted(allowed_targets)[:30]}..."
        )


def validate_test_suite(test_suite: TestSuite, ui_context: Dict[str, Any]) -> None:
    """
    Validate all test cases in a test suite against the UI context.
    """
    errors = []
    for idx, test_case in enumerate(test_suite.test_cases):
        try:
            validate_targets_against_context(test_case, ui_context)
        except ValueError as e:
            errors.append(f"Test case {idx + 1} ('{test_case.test_name}'): {str(e)}")
    
    if errors:
        raise ValueError("Validation errors in test suite:\n" + "\n".join(errors))


# ---------------------------------------------------------------------------
# Public API: run pipeline
# ---------------------------------------------------------------------------


def run_langchain_ui_test_pipeline(
    llm: BaseChatModel,
    payload: UITestEngineInput,
    *,
    max_retries: int = 1,
) -> List[TestSpec]:
    """
    End-to-end pipeline:
    - Assumes ui_context and requirements are already preprocessed.
    - Calls LangChain test spec chain.
    - Validates schema and targets against UI context.
    - Optionally retries once with a corrective prompt.

    Returns:
        List of TestSpec instances (comprehensive test suite) suitable for downstream code generation.
    """
    import json

    ui_context_json = json.dumps(payload.ui_context, ensure_ascii=False)
    functional_text = "\n".join(payload.functional_requirements)
    non_functional_text = "\n".join(payload.non_functional_requirements)
    user_flow_text = "\n".join(payload.user_flow_context)
    
    # Format overview and frontend_features if provided
    overview_section = ""
    if payload.overview:
        overview_section = f"OVERVIEW:\n{payload.overview}\n\n"
    
    frontend_features_section = ""
    if payload.frontend_features:
        features_text = "\n".join(f"- {feat}" for feat in payload.frontend_features)
        frontend_features_section = f"FRONTEND FEATURES:\n{features_text}\n\n"

    test_spec_chain = build_test_spec_chain(llm)
    retry_chain = build_retry_chain(llm)

    def _invoke_chain(chain: Runnable, errors: Optional[str] = None) -> TestSuite:
        kwargs = {
            "ui_context_json": ui_context_json,
            "functional_requirements": functional_text,
            "non_functional_requirements": non_functional_text,
            "user_flow_context": user_flow_text,
            "overview_section": overview_section,
            "frontend_features_section": frontend_features_section,
        }
        if errors:
            kwargs["validation_errors"] = errors
        return chain.invoke(kwargs)

    # First attempt
    try:
        test_suite = _invoke_chain(test_spec_chain)
        validate_test_suite(test_suite, payload.ui_context)
        return test_suite.test_cases
    except (ValidationError, ValueError) as e:
        if max_retries <= 0:
            raise

        # Retry with explicit error feedback
        test_suite = _invoke_chain(retry_chain, errors=str(e))
        validate_test_suite(test_suite, payload.ui_context)
        return test_suite.test_cases


__all__ = [
    "UITestEngineInput",
    "TestStep",
    "TestSpec",
    "TestSuite",
    "run_langchain_ui_test_pipeline",
    "build_test_spec_chain",
    "build_retry_chain",
]


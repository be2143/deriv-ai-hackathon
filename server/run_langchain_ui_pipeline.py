"""
End-to-end runner for the LangChain UI test spec pipeline.

This script:
1. Builds a demo UI context + requirements (or you can replace with real inputs).
2. Calls the LangChain-based engine:

   from langchain_openai import ChatOpenAI
   from langchain_ui_test_pipeline import (
       UITestEngineInput,
       run_langchain_ui_test_pipeline,
   )

3. Generates a TestSpec.
4. Executes the spec against a real browser using Selenium.

NOTE:
- Requires OPENAI_API_KEY in the environment for ChatOpenAI.
- Uses Chrome in headless mode via webdriver_manager.
"""

from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

from langchain_ui_test_pipeline import UITestEngineInput, TestSpec, run_langchain_ui_test_pipeline
from langchain_openai import ChatOpenAI


# ---------------------------------------------------------------------------
# Demo input builders
# ---------------------------------------------------------------------------


def build_demo_ui_context(target_url: str) -> Dict[str, Any]:
    """
    Build a minimal demo UI context.

    In production you should:
    - Use Selenium (or another crawler) to discover elements for the real page.
    - Populate "elements" with stable identifiers and CSS/XPath selectors.
    """
    return {
        "page_url": target_url,
        "title": "Demo Login Page",
        "elements": [
            {
                "id": "email_input",
                "label": "Email address",
                "css_selector": "input[name='email']",
            },
            {
                "id": "password_input",
                "label": "Password",
                "css_selector": "input[name='password']",
            },
            {
                "id": "login_button",
                "label": "Log in",
                "css_selector": "button[type='submit'], button#login",
            },
        ],
    }


def build_demo_requirements() -> Dict[str, List[str]]:
    """Build simple functional / non-functional / flow requirement lists."""
    functional = [
        "User must be able to log in with valid email and password and reach the dashboard.",
    ]
    non_functional = [
        "Login should complete within 3 seconds in normal conditions.",
        "Error messages must be clearly visible to the user.",
    ]
    user_flow = [
        "Standard login flow from the main login form on the page.",
    ]
    return {
        "functional": functional,
        "non_functional": non_functional,
        "user_flow": user_flow,
    }


# ---------------------------------------------------------------------------
# Selenium execution of TestSpec
# ---------------------------------------------------------------------------


class SpecExecutor:
    """
    Minimal executor that runs a single TestSpec using Selenium.

    It expects ui_context["elements"] to include a "css_selector" for each logical target id.
    """

    def __init__(self, headless: bool = True, timeout: int = 15) -> None:
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service

        chrome_options = Options()
        if headless:
            chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--window-size=1920,1080")

        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=chrome_options)
        self.driver.implicitly_wait(5)
        self.timeout = timeout

    def close(self) -> None:
        try:
            self.driver.quit()
        except Exception:
            pass

    # Helpers ---------------------------------------------------------------

    def _build_selector_map(self, ui_context: Dict[str, Any]) -> Dict[str, str]:
        mapping: Dict[str, str] = {}
        for el in ui_context.get("elements", []):
            element_id = el.get("id") or el.get("name") or el.get("data_testid") or el.get("label")
            css = el.get("css_selector")
            if element_id and css:
                mapping[element_id] = css
        return mapping

    def _resolve_element(self, target: str, selector_map: Dict[str, str]):
        selector = selector_map.get(target)
        if not selector:
            raise ValueError(f"No selector found for target '{target}'")
        wait = WebDriverWait(self.driver, self.timeout)
        return wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))

    # Execution -------------------------------------------------------------

    def run_spec(self, spec: TestSpec, ui_context: Dict[str, Any]) -> None:
        base_url = ui_context.get("page_url", "")
        selector_map = self._build_selector_map(ui_context)

        print(f"\n▶️ Running test spec: {spec.test_name}")
        print(f"   {spec.description}")

        for idx, step in enumerate(spec.steps, start=1):
            action = step.action
            target = step.target
            value = step.value
            print(f"  Step {idx}: {action} target={target!r} value={value!r}")

            if action == "navigate":
                url = value or base_url
                if url and not url.startswith("http"):
                    # Treat as path relative to base_url
                    url = base_url.rstrip("/") + "/" + url.lstrip("/")
                self.driver.get(url or base_url)
                continue

            if action in {"type", "click", "assert_visible", "assert_disabled", "assert_text"}:
                if not target:
                    raise ValueError(f"Step {idx} with action='{action}' requires a target.")
                element = self._resolve_element(target, selector_map)

                if action == "type":
                    text = value or ""
                    element.clear()
                    element.send_keys(text)

                elif action == "click":
                    WebDriverWait(self.driver, self.timeout).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, selector_map[target]))
                    )
                    element.click()

                elif action == "assert_visible":
                    assert element.is_displayed(), f"Element '{target}' is not visible."

                elif action == "assert_disabled":
                    assert not element.is_enabled(), f"Element '{target}' is not disabled."

                elif action == "assert_text":
                    expected = value or ""
                    actual = (element.text or "").strip()
                    assert expected in actual, f"Expected text '{expected}' in '{actual}'"

            elif action == "assert_url_contains":
                fragment = value or ""
                current_url = self.driver.current_url
                assert fragment in current_url, f"Expected '{fragment}' in URL '{current_url}'"

            else:
                # Any unsupported action should have been filtered earlier.
                raise ValueError(f"Unsupported action in executor: {action}")

            # Small pacing pause to make debugging easier
            time.sleep(0.5)

        print("✅ Test spec executed without assertion failures.")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def main() -> None:
    # Adjust this URL to point to a real page you want to test
    target_url = os.environ.get("DEMO_TARGET_URL", "https://example.com/login")

    # Build demo inputs; swap these with real data in production.
    ui_context_dict = build_demo_ui_context(target_url)
    reqs = build_demo_requirements()

    payload = UITestEngineInput(
        ui_context=ui_context_dict,
        functional_requirements=reqs["functional"],
        non_functional_requirements=reqs["non_functional"],
        user_flow_context=reqs["user_flow"],
    )

    # LLM client (requires OPENAI_API_KEY for ChatOpenAI)
    llm = ChatOpenAI(model="gpt-4.1-mini", temperature=0.0)

    # Run LangChain UI test pipeline
    test_specs = run_langchain_ui_test_pipeline(llm, payload)
    print(f"\n=== Generated Test Suite ({len(test_specs)} test cases) ===")
    for idx, test_spec in enumerate(test_specs, 1):
        print(f"\n--- Test Case {idx}: {test_spec.test_name} ---")
        print(test_spec.model_dump_json(indent=2, ensure_ascii=False))

    # Execute all generated test specs using Selenium
    executor = SpecExecutor(headless=True)
    try:
        for idx, test_spec in enumerate(test_specs, 1):
            print(f"\n{'='*60}")
            print(f"Executing Test Case {idx}/{len(test_specs)}: {test_spec.test_name}")
            print('='*60)
            try:
                executor.run_spec(test_spec, ui_context_dict)
            except Exception as e:
                print(f"❌ Test case '{test_spec.test_name}' failed: {e}")
                # Continue with next test case
                continue
    finally:
        executor.close()


if __name__ == "__main__":
    main()


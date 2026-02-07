"""
End-to-end runner for the LangChain UI test spec pipeline.

This script:
1. Loads UI context from JSON file (or uses demo data).
2. Loads requirements/context from JSON file (or uses demo data).
3. Calls the LangChain-based engine to generate test specs.
4. Optionally executes the specs against a real browser using Selenium.

Usage:
    # With JSON or HTML UI context:
    python run_langchain_ui_pipeline.py \\
        --ui-context reports/page_improved.json \\
        --requirements extracted_requirements.json
    python run_langchain_ui_pipeline.py \\
        --ui-context reports/dom_www.example.com____20260206.html \\
        --requirements extracted_requirements.json

    # With demo data (default):
    python run_langchain_ui_pipeline.py [--execute]

NOTE:
- Requires OPENAI_API_KEY in the environment for ChatOpenAI.
- Uses Chrome in headless mode via webdriver_manager.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from langchain_openai import ChatOpenAI

from langchain_ui_test_pipeline import (
    UITestEngineInput,
    TestSpec,
    run_langchain_ui_test_pipeline,
)


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
# HTML and JSON File Loaders
# ---------------------------------------------------------------------------

try:
    from ui_context_loader import load_ui_context_from_html
except ImportError:
    from server.ui_context_loader import load_ui_context_from_html  # type: ignore

# ---------------------------------------------------------------------------
# JSON File Loaders
# ---------------------------------------------------------------------------


def _normalize_element_for_pipeline(el: Dict[str, Any], index: int) -> Dict[str, Any]:
    """Ensure element has id and css_selector for pipeline/executor."""
    normalized = {
        "tag": el.get("tag"),
        "role": el.get("role", el.get("tag")),
        "css_selector": el.get("css_selector"),
    }
    for key in ["id", "name", "type", "label"]:
        if el.get(key) is not None:
            normalized[key] = el[key]
    # id from container if present
    container = el.get("container") or {}
    if not normalized.get("id") and container.get("id"):
        normalized["id"] = container["id"]
    if not normalized.get("css_selector"):
        if normalized.get("id"):
            normalized["css_selector"] = f"#{normalized['id']}"
        elif normalized.get("name"):
            normalized["css_selector"] = f"[name='{normalized['name']}']"
        elif normalized.get("tag"):
            normalized["css_selector"] = normalized["tag"]
    logical_id = (
        normalized.get("id")
        or normalized.get("name")
        or normalized.get("label")
        or f"element_{index}"
    )
    normalized["id"] = logical_id
    return normalized


def load_ui_context_from_json(file_path: Path) -> Dict[str, Any]:
    """
    Load UI context from JSON file.
    
    Handles:
    - Direct format: {"page_url": "...", "elements": [...]}
    - pages as object: {"pages": {"page_url": "...", "elements": [...]}}
    - pages as array: {"pages": [{"url": "...", "forms": [...]}, ...]}
    """
    with file_path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    
    # Direct UI context at root
    if "page_url" in data or "elements" in data:
        page = data.copy()
        if "elements" in page and page["elements"]:
            page["elements"] = [
                _normalize_element_for_pipeline(el, i)
                for i, el in enumerate(page["elements"])
            ]
        return page
    
    if "pages" not in data:
        raise ValueError(
            "Invalid UI context format. Expected 'page_url'/'elements' at root or 'pages' key."
        )
    
    pages_val = data["pages"]
    
    # pages is a single object (e.g. page_improved.json)
    if isinstance(pages_val, dict):
        page = pages_val.copy()
        if "url" in page and "page_url" not in page:
            page["page_url"] = page.pop("url")
        if "elements" in page and page["elements"]:
            page["elements"] = [
                _normalize_element_for_pipeline(el, i)
                for i, el in enumerate(page["elements"])
            ]
        return page
    
    # pages is an array
    if isinstance(pages_val, list) and len(pages_val) > 0:
        base_page = pages_val[0].copy()
        if "url" in base_page and "page_url" not in base_page:
            base_page["page_url"] = base_page.pop("url")
        
        all_elements = []
        seen_ids = set()
        
        for page_idx, page in enumerate(pages_val):
            # Already has elements array
            if page.get("elements"):
                for i, el in enumerate(page["elements"]):
                    norm = _normalize_element_for_pipeline(el, len(all_elements))
                    lid = norm["id"]
                    if lid in seen_ids:
                        lid = f"{lid}_p{page_idx}"
                    seen_ids.add(lid)
                    norm["id"] = lid
                    all_elements.append(norm)
            else:
                for form in page.get("forms", []):
                    for el in form.get("elements", []):
                        normalized_el = {
                            "tag": el.get("tag"),
                            "role": el.get("role", el.get("tag")),
                        }
                        for key in ["id", "name", "type", "label"]:
                            if el.get(key):
                                normalized_el[key] = el[key]
                        if "css_selector" not in normalized_el:
                            if normalized_el.get("id"):
                                normalized_el["css_selector"] = f"#{normalized_el['id']}"
                            elif normalized_el.get("name"):
                                normalized_el["css_selector"] = f"[name='{normalized_el['name']}']"
                            else:
                                normalized_el["css_selector"] = normalized_el.get("tag", "unknown")
                        logical_id = (
                            normalized_el.get("id")
                            or normalized_el.get("name")
                            or normalized_el.get("label")
                            or f"{normalized_el.get('tag')}_{len(all_elements)}"
                        )
                        if logical_id in seen_ids:
                            logical_id = f"{logical_id}_page{page_idx}"
                        seen_ids.add(logical_id)
                        normalized_el["id"] = logical_id
                        all_elements.append(normalized_el)
        
        if all_elements:
            base_page["elements"] = all_elements
        return base_page
    
    raise ValueError(
        "Invalid UI context format: 'pages' must be an object or a non-empty array."
    )


def load_requirements_from_json(file_path: Path) -> Dict[str, Any]:
    """
    Load requirements/context from JSON file.
    
    Handles:
    - Wrapped format from ai_input_processor: {"requirements": {...}}
    - Direct format: {"overview": ..., "functional_requirements": [...]}
    """
    with file_path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    
    # Handle wrapped format (from ai_input_processor save)
    if "requirements" in data:
        return data["requirements"]
    
    # Handle direct format
    if "functional_requirements" in data or "overview" in data:
        return data
    
    raise ValueError(
        f"Invalid requirements format. Expected 'requirements' wrapper or direct format."
    )


# ---------------------------------------------------------------------------
# Selenium execution of TestSpec
# ---------------------------------------------------------------------------


class SpecExecutor:
    """
    Minimal executor that runs a single TestSpec using Selenium.

    It expects ui_context["elements"] to include a "css_selector" for each logical target id.
    """

    def __init__(self, headless: bool = True, timeout: int = 15) -> None:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        from webdriver_manager.chrome import ChromeDriverManager

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
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.support.ui import WebDriverWait
        
        selector = selector_map.get(target)
        if not selector:
            raise ValueError(f"No selector found for target '{target}'")
        wait = WebDriverWait(self.driver, self.timeout)
        return wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))

    # Execution -------------------------------------------------------------

    def run_spec(self, spec: TestSpec, ui_context: Dict[str, Any]) -> None:
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.support.ui import WebDriverWait
        
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
    parser = argparse.ArgumentParser(
        description="Generate and optionally execute UI test specs.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--ui-context",
        type=Path,
        help="Path to UI context JSON file (from crawl results)",
    )
    parser.add_argument(
        "--requirements",
        type=Path,
        help="Path to requirements JSON file (from ai_input_processor)",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Execute generated tests with Selenium",
    )

    args = parser.parse_args()

    # Check API key
    if "OPENAI_API_KEY" not in os.environ:
        print("❌ OPENAI_API_KEY not set in environment")
        print("   Please set it before running:")
        print("   export OPENAI_API_KEY='your-key'")
        return

    # Load UI context (from HTML, JSON, or use demo)
    if args.ui_context:
        if not args.ui_context.exists():
            print(f"❌ UI context file not found: {args.ui_context}")
            return
        print(f"📄 Loading UI context from: {args.ui_context}")
        if args.ui_context.suffix.lower() == ".html":
            ui_context_dict = load_ui_context_from_html(args.ui_context)
            print(f"✅ Loaded UI context from HTML: {len(ui_context_dict.get('elements', []))} elements")
        else:
            ui_context_dict = load_ui_context_from_json(args.ui_context)
            print(f"✅ Loaded UI context: {len(ui_context_dict.get('elements', []))} elements")
    else:
        target_url = os.environ.get("DEMO_TARGET_URL", "https://example.com/login")
        print("📄 Using demo UI context")
        ui_context_dict = build_demo_ui_context(target_url)

    # Load requirements (from JSON or use demo)
    reqs_data = None
    if args.requirements:
        if not args.requirements.exists():
            print(f"❌ Requirements file not found: {args.requirements}")
            return
        print(f"📄 Loading requirements from: {args.requirements}")
        reqs_data = load_requirements_from_json(args.requirements)
        print(f"✅ Loaded requirements:")
        print(f"   - Functional: {len(reqs_data.get('functional_requirements', []))}")
        print(f"   - Non-functional: {len(reqs_data.get('non_functional_requirements', []))}")
        print(f"   - User flows: {len(reqs_data.get('user_flow_context', []))}")
        
        reqs = {
            "functional": reqs_data.get("functional_requirements", []),
            "non_functional": reqs_data.get("non_functional_requirements", []),
            "user_flow": reqs_data.get("user_flow_context", []),
        }
    else:
        print("📄 Using demo requirements")
        reqs = build_demo_requirements()

    # Build payload
    payload = UITestEngineInput(
        ui_context=ui_context_dict,
        functional_requirements=reqs["functional"],
        non_functional_requirements=reqs["non_functional"],
        user_flow_context=reqs["user_flow"],
        overview=reqs_data.get("overview") if reqs_data else None,
        frontend_features=reqs_data.get("frontend_features") if reqs_data else None,
    )

    # LLM client (requires OPENAI_API_KEY for ChatOpenAI)
    llm = ChatOpenAI(model="gpt-4.1-mini", temperature=0.0)

    # Run LangChain UI test pipeline
    print("\n🔄 Generating test suite...")
    test_specs = run_langchain_ui_test_pipeline(llm, payload)
    print(f"\n=== Generated Test Suite ({len(test_specs)} test cases) ===")
    for idx, test_spec in enumerate(test_specs, 1):
        print(f"\n--- Test Case {idx}: {test_spec.test_name} ---")
        print(test_spec.model_dump_json(indent=2, ensure_ascii=False))

    # Execute all generated test specs using Selenium (if requested)
    if args.execute:
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
    else:
        print("\n💡 Tip: Add --execute flag to run tests with Selenium")


if __name__ == "__main__":
    main()

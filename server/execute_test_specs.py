"""
Execute generated test specs using Selenium.

This script takes a generated test spec JSON file and executes it against a real browser.

Usage:
    python execute_test_specs.py \\
        --test-specs reports/test_specs_random_org_20260206_123456.json \\
        --ui-context reports/optimized_ui_context.json \\
        [--headless]  # Run in headless mode (default: True)
        [--no-headless]  # Run with visible browser
        [--output-dir reports/execution_results]  # Save execution results

The test specs JSON should be in format:
{
  "generated_at": "...",
  "page_url": "...",
  "total_test_cases": N,
  "test_cases": [
    {
      "test_name": "...",
      "description": "...",
      "steps": [...]
    }
  ]
}
"""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from langchain_ui_test_pipeline import TestSpec


class TestExecutor:
    """
    Executes TestSpec instances using Selenium WebDriver.
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

    def _iter_element_like_items(self, ui_context: Dict[str, Any]):
        """Yield element-like items from any UI context (any website/crawl format)."""
        for key in ("elements", "headings", "links", "buttons"):
            for el in ui_context.get(key, []):
                if isinstance(el, dict):
                    yield el
        for form in ui_context.get("forms", []):
            if isinstance(form, dict):
                for el in form.get("elements", []):
                    if isinstance(el, dict):
                        yield el
        for key, val in ui_context.items():
            if key in ("elements", "headings", "forms", "links", "buttons", "pages", "summary"):
                continue
            if isinstance(val, list):
                for item in val:
                    if isinstance(item, dict) and (
                        item.get("css_selector") or item.get("id") or item.get("text")
                    ):
                        yield item

    def _build_selector_map(self, ui_context: Dict[str, Any]) -> Dict[str, str]:
        """Build mapping from target to CSS selector; works with any UI context structure."""
        mapping: Dict[str, str] = {}

        def add_el(el: Dict[str, Any]) -> None:
            css = el.get("css_selector")
            if css:
                for key in ("id", "name", "data_testid", "label", "identifier", "text"):
                    val = el.get(key)
                    if isinstance(val, str) and val.strip():
                        mapping[val.strip()] = css
                mapping[css] = css
            container = el.get("container") or {}
            if isinstance(container, dict):
                cid = container.get("id")
                if isinstance(cid, str) and cid.strip():
                    mapping["#" + cid.strip()] = "#" + cid.strip()

        for el in self._iter_element_like_items(ui_context):
            add_el(el)
        return mapping

    def _resolve_element(self, target: str, selector_map: Dict[str, str]):
        """Resolve a logical target to a Selenium WebElement."""
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.support.ui import WebDriverWait

        selector = selector_map.get(target)
        if not selector:
            # Treat target as literal CSS selector if it looks like one (id, attribute, class, or combinator)
            if (
                target.startswith("#")
                or target.startswith("[")
                or target.startswith(".")
                or " > " in target
            ):
                selector = target
            else:
                raise ValueError(f"No selector found for target '{target}'")
        wait = WebDriverWait(self.driver, self.timeout)
        return wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))

    def execute_test_spec(
        self, spec: TestSpec, ui_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute a single test spec and return results.

        Returns:
            Dictionary with: status, execution_time, error_message, steps_executed
        """
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.support.ui import WebDriverWait

        base_url = ui_context.get("page_url", "")
        selector_map = self._build_selector_map(ui_context)

        start_time = time.time()
        steps_executed = []
        error_message = None
        status = "PASS"

        try:
            # Navigate to base URL first
            if base_url:
                self.driver.get(base_url)
                time.sleep(1)  # Allow page to load

            # Execute each step
            for idx, step in enumerate(spec.steps, start=1):
                step_start = time.time()
                action = step.action
                target = step.target
                value = step.value

                try:
                    if action == "navigate":
                        url = value or base_url
                        if url and not url.startswith("http"):
                            # Treat as path relative to base_url
                            url = base_url.rstrip("/") + "/" + url.lstrip("/")
                        self.driver.get(url or base_url)
                        steps_executed.append(
                            {
                                "step": idx,
                                "action": action,
                                "target": target,
                                "value": value,
                                "status": "PASS",
                                "duration": time.time() - step_start,
                            }
                        )
                        continue

                    # Special case: page title (document title, not an element)
                    if target == "title" and action in ("assert_visible", "assert_text"):
                        page_title = self.driver.title or ""
                        if action == "assert_visible":
                            assert page_title, "Page title is empty."
                        else:  # assert_text
                            expected = value or ""
                            assert expected in page_title, (
                                f"Expected text '{expected}' in page title '{page_title}'"
                            )
                        steps_executed.append(
                            {
                                "step": idx,
                                "action": action,
                                "target": target,
                                "value": value,
                                "status": "PASS",
                                "duration": time.time() - step_start,
                            }
                        )
                        time.sleep(0.3)
                        continue

                    if action in {
                        "type",
                        "click",
                        "assert_visible",
                        "assert_disabled",
                        "assert_text",
                    }:
                        if not target:
                            raise ValueError(
                                f"Step {idx} with action='{action}' requires a target."
                            )
                        element = self._resolve_element(target, selector_map)

                        if action == "type":
                            text = value or ""
                            element.clear()
                            element.send_keys(text)

                        elif action == "click":
                            selector = selector_map.get(target) or target
                            WebDriverWait(self.driver, self.timeout).until(
                                EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
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
                        raise ValueError(f"Unsupported action: {action}")

                    steps_executed.append(
                        {
                            "step": idx,
                            "action": action,
                            "target": target,
                            "value": value,
                            "status": "PASS",
                            "duration": time.time() - step_start,
                        }
                    )

                    # Small delay between steps
                    time.sleep(0.3)

                except Exception as step_error:
                    steps_executed.append(
                        {
                            "step": idx,
                            "action": action,
                            "target": target,
                            "value": value,
                            "status": "FAIL",
                            "error": str(step_error),
                            "duration": time.time() - step_start,
                        }
                    )
                    raise  # Re-raise to mark test as failed

        except Exception as e:
            status = "FAIL"
            error_message = str(e)

        execution_time = time.time() - start_time

        return {
            "status": status,
            "execution_time": execution_time,
            "error_message": error_message,
            "steps_executed": steps_executed,
            "total_steps": len(spec.steps),
            "passed_steps": len([s for s in steps_executed if s.get("status") == "PASS"]),
        }


def load_test_specs(file_path: Path) -> List[TestSpec]:
    """Load test specs from JSON file."""
    with file_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    # Handle wrapped format from langchain_ui_test_pipeline save
    if "test_cases" in data:
        test_cases_data = data["test_cases"]
    elif isinstance(data, list):
        test_cases_data = data
    else:
        raise ValueError(
            "Invalid test specs format. Expected {'test_cases': [...]} or list."
        )

    test_specs = []
    for tc_data in test_cases_data:
        test_specs.append(TestSpec(**tc_data))

    return test_specs


def load_ui_context(file_path: Path) -> Dict[str, Any]:
    """Load UI context from JSON or HTML file (any website)."""
    if file_path.suffix.lower() == ".html":
        try:
            from ui_context_loader import load_ui_context_from_html
        except ImportError:
            from server.ui_context_loader import load_ui_context_from_html  # type: ignore
        return load_ui_context_from_html(file_path)
    with file_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    # Handle various formats
    if "page_url" in data or "elements" in data:
        return data

    if "pages" in data and len(data["pages"]) > 0:
        # Use first page, aggregate elements from all pages
        base_page = data["pages"][0].copy()
        if "url" in base_page and "page_url" not in base_page:
            base_page["page_url"] = base_page.pop("url")

        # Aggregate elements from all pages
        all_elements = []
        seen_ids = set()

        for page_idx, page in enumerate(data["pages"]):
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
                        elif normalized_el.get("tag"):
                            normalized_el["css_selector"] = normalized_el["tag"]

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

    raise ValueError("Invalid UI context format.")


def save_execution_results(
    results: List[Dict[str, Any]],
    output_dir: Path,
    test_specs_file: Path,
) -> Path:
    """Save execution results to JSON file."""
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = output_dir / f"execution_results_{timestamp}.json"

    summary = {
        "executed_at": datetime.now().isoformat(),
        "test_specs_source": str(test_specs_file),
        "total_tests": len(results),
        "passed": len([r for r in results if r["status"] == "PASS"]),
        "failed": len([r for r in results if r["status"] == "FAIL"]),
        "total_execution_time": sum(r["execution_time"] for r in results),
        "results": results,
    }

    with output_file.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    return output_file


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Execute generated test specs with Selenium.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Execute tests in headless mode
  python execute_test_specs.py \\
      --test-specs reports/test_specs_random_org.json \\
      --ui-context reports/optimized_ui_context.json

  # Execute with visible browser
  python execute_test_specs.py \\
      --test-specs reports/test_specs_random_org.json \\
      --ui-context reports/optimized_ui_context.json \\
      --no-headless

  # Save results to custom directory
  python execute_test_specs.py \\
      --test-specs reports/test_specs_random_org.json \\
      --ui-context reports/optimized_ui_context.json \\
      --output-dir reports/execution_results
        """,
    )
    parser.add_argument(
        "--test-specs",
        required=True,
        type=Path,
        help="Path to test specs JSON file (from langchain_ui_test_pipeline)",
    )
    parser.add_argument(
        "--ui-context",
        required=True,
        type=Path,
        help="Path to UI context JSON file (for element selectors)",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        default=True,
        help="Run browser in headless mode (default: True)",
    )
    parser.add_argument(
        "--no-headless",
        dest="headless",
        action="store_false",
        help="Run browser with visible window",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("reports/execution_results"),
        help="Directory to save execution results JSON",
    )

    args = parser.parse_args()

    # Validate files
    if not args.test_specs.exists():
        print(f"❌ Test specs file not found: {args.test_specs}")
        return

    if not args.ui_context.exists():
        print(f"❌ UI context file not found: {args.ui_context}")
        return

    print("🚀 Test Execution Runner")
    print("=" * 70)

    # Load test specs
    print(f"\n📄 Loading test specs from: {args.test_specs}")
    try:
        test_specs = load_test_specs(args.test_specs)
        print(f"✅ Loaded {len(test_specs)} test cases")
    except Exception as e:
        print(f"❌ Failed to load test specs: {e}")
        return

    # Load UI context
    print(f"\n📄 Loading UI context from: {args.ui_context}")
    try:
        ui_context = load_ui_context(args.ui_context)
        print(f"✅ Loaded UI context:")
        print(f"   Page URL: {ui_context.get('page_url', 'N/A')}")
        print(f"   Elements: {len(ui_context.get('elements', []))}")
    except Exception as e:
        print(f"❌ Failed to load UI context: {e}")
        return

    # Execute tests
    print(f"\n{'='*70}")
    print("🧪 Executing Tests")
    print(f"{'='*70}")

    executor = TestExecutor(headless=args.headless)
    execution_results = []

    try:
        for idx, test_spec in enumerate(test_specs, 1):
            print(f"\n{'='*70}")
            print(f"Test Case {idx}/{len(test_specs)}: {test_spec.test_name}")
            print(f"{'='*70}")
            print(f"Description: {test_spec.description}")
            print(f"Steps: {len(test_spec.steps)}")

            result = executor.execute_test_spec(test_spec, ui_context)
            result["test_name"] = test_spec.test_name
            result["test_description"] = test_spec.description

            execution_results.append(result)

            # Print result
            status_icon = "✅" if result["status"] == "PASS" else "❌"
            print(f"\n{status_icon} Status: {result['status']}")
            print(f"   Execution time: {result['execution_time']:.2f}s")
            print(f"   Steps: {result['passed_steps']}/{result['total_steps']} passed")

            if result["error_message"]:
                print(f"   Error: {result['error_message']}")

            # Print step details
            print("\n   Step details:")
            for step_result in result["steps_executed"]:
                step_status = "✓" if step_result.get("status") == "PASS" else "✗"
                print(
                    f"     {step_status} Step {step_result['step']}: {step_result['action']} "
                    f"(target={step_result.get('target', 'N/A')}, "
                    f"duration={step_result.get('duration', 0):.2f}s)"
                )
                if step_result.get("error"):
                    print(f"       Error: {step_result['error']}")

    finally:
        executor.close()

    # Save results
    print(f"\n{'='*70}")
    print("📊 Execution Summary")
    print(f"{'='*70}")

    total = len(execution_results)
    passed = len([r for r in execution_results if r["status"] == "PASS"])
    failed = total - passed
    total_time = sum(r["execution_time"] for r in execution_results)

    print(f"Total tests: {total}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(f"Pass rate: {(passed/total*100) if total > 0 else 0:.1f}%")
    print(f"Total execution time: {total_time:.2f}s")

    # Save to file
    try:
        output_file = save_execution_results(
            execution_results, args.output_dir, args.test_specs
        )
        print(f"\n✅ Execution results saved to: {output_file}")
    except Exception as e:
        print(f"\n⚠️  Failed to save results: {e}")


if __name__ == "__main__":
    main()

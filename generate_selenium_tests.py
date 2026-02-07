"""
Generate Selenium pytest scripts from LangChain test specs.

Usage (example):
    python generate_selenium_tests.py \\
        --tests panio_test_suite.json \\
        --ui-context crawl_ui_results_20260206_172147_compressed.json \\
        --output generated_selenium_tests.py

Then run:
    pytest generated_selenium_tests.py

Expected tests JSON format (either of):
1) Suite object:
   {
     "test_cases": [
       { "test_name": "...", "description": "...", "steps": [ ... ] },
       ...
     ]
   }
2) Direct list:
   [
     { "test_name": "...", "description": "...", "steps": [ ... ] },
     ...
   ]

Each step:
   {
     "action": "navigate|type|click|assert_visible|assert_text|assert_url_contains|assert_disabled",
     "target": "logical_element_id (optional)",
     "value": "string (optional)"
   }
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional


def slugify(name: str) -> str:
    """Create a safe python identifier from a test name."""
    name = name.strip().lower()
    name = re.sub(r"[^a-z0-9]+", "_", name)
    name = re.sub(r"_+", "_", name).strip("_")
    if not name:
        return "test_case"
    if not name[0].isalpha():
        name = "test_" + name
    if not name.startswith("test_"):
        name = "test_" + name
    return name


def build_selector_map(ui_context: Dict[str, Any]) -> Dict[str, str]:
    """
    Build a map from logical target id -> CSS selector.

    Prefers explicit 'css_selector' on elements; falls back to id/name where possible.
    """
    mapping: Dict[str, str] = {}
    for el in ui_context.get("elements", []):
        logical_id: Optional[str] = None
        for key in ("id", "name", "data_testid", "data-testid", "label"):
            val = el.get(key)
            if isinstance(val, str) and val.strip():
                logical_id = val.strip()
                break

        if not logical_id:
            continue

        css = el.get("css_selector")
        if isinstance(css, str) and css.strip():
            mapping[logical_id] = css.strip()
            continue

        # Fallbacks: build a best-effort selector from id/name
        if el.get("id"):
            mapping[logical_id] = f"#{el['id']}"
        elif el.get("name"):
            mapping[logical_id] = f"[name='{el['name']}']"
        elif el.get("label"):
            # Very rough fallback: match by text, can be refined
            mapping[logical_id] = f"*[aria-label='{el['label']}'], *[title='{el['label']}']"

    return mapping


def load_test_specs(path: Path) -> List[Dict[str, Any]]:
    """Load test specs from JSON file and normalize to a list."""
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, dict) and "test_cases" in data:
        return data["test_cases"]
    if isinstance(data, list):
        return data

    raise ValueError("Unsupported test specs JSON format. Expected list or {\"test_cases\": [...]} object.")


def generate_selenium_tests(
    test_specs: List[Dict[str, Any]],
    ui_context: Dict[str, Any],
    output_path: Path,
) -> None:
    """Generate a pytest-based Selenium test file from test specs."""
    base_url = ui_context.get("page_url", "").rstrip("/")
    selector_map = build_selector_map(ui_context)

    lines: List[str] = []
    append = lines.append

    # Header and imports
    append('"""')
    append("Auto-generated Selenium tests from LangChain test specs.")
    append("")
    append("DO NOT EDIT MANUALLY – regenerate via generate_selenium_tests.py.")
    append('"""')
    append("")
    append("import time")
    append("")
    append("import pytest")
    append("from selenium import webdriver")
    append("from selenium.webdriver.common.by import By")
    append("from selenium.webdriver.support.ui import WebDriverWait")
    append("from selenium.webdriver.support import expected_conditions as EC")
    append("from webdriver_manager.chrome import ChromeDriverManager")
    append("")
    append("")
    append(f"BASE_URL = {repr(base_url or 'about:blank')}")
    append("")
    append("")
    append("@pytest.fixture(scope='session')")
    append("def driver():")
    append("    \"\"\"Session-scoped Selenium WebDriver (Chrome, headless).\"\"\"")
    append("    from selenium.webdriver.chrome.options import Options")
    append("    from selenium.webdriver.chrome.service import Service")
    append("")
    append("    options = Options()")
    append("    options.add_argument('--headless=new')")
    append("    options.add_argument('--no-sandbox')")
    append("    options.add_argument('--disable-dev-shm-usage')")
    append("    options.add_argument('--window-size=1920,1080')")
    append("")
    append("    service = Service(ChromeDriverManager().install())")
    append("    drv = webdriver.Chrome(service=service, options=options)")
    append("    drv.implicitly_wait(5)")
    append("    try:")
    append("        yield drv")
    append("    finally:")
    append("        drv.quit()")
    append("")
    append("")
    append("def _get_selector(target: str) -> str:")
    append("    mapping = {")
    for key, css in selector_map.items():
        append(f"        {repr(key)}: {repr(css)},")
    append("    }")
    append("    if target not in mapping:")
    append("        raise AssertionError(f\"No selector found for target '{target}'\")")
    append("    return mapping[target]")
    append("")
    append("")
    append("def _resolve_element(driver, target: str, timeout: int = 15):")
    append("    selector = _get_selector(target)")
    append("    wait = WebDriverWait(driver, timeout)")
    append("    return wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))")
    append("")
    append("")

    # Generate one pytest test per spec
    for spec in test_specs:
        name = spec.get("test_name") or "Unnamed test"
        desc = spec.get("description", "")
        steps = spec.get("steps", [])
        func_name = slugify(name)

        append(f"def {func_name}(driver):")
        append(f"    \"\"\"{desc}\"\"\"")
        append("")
        append("    # Start from base URL")
        append("    if BASE_URL and not driver.current_url.startswith(BASE_URL):")
        append("        driver.get(BASE_URL)")
        append("")

        append("    # Execute test steps")
        append("    for idx, step in enumerate(" + repr(list(range(len(steps)))) + "):")
        append("        step_data = " + repr(steps) + "[idx]")
        append("        action = step_data.get('action')")
        append("        target = step_data.get('target')")
        append("        value = step_data.get('value')")
        append("        # Small delay to stabilize interactions")
        append("        time.sleep(0.2)")
        append("")
        append("        if action == 'navigate':")
        append("            url = value or BASE_URL")
        append("            if url and not url.startswith('http') and BASE_URL:")
        append("                url = BASE_URL.rstrip('/') + '/' + url.lstrip('/')")
        append("            driver.get(url)")
        append("")
        append("        elif action in {'type', 'click', 'assert_visible', 'assert_disabled', 'assert_text'}:")
        append("            if not target:")
        append("                raise AssertionError(f\"Step {idx+1} with action '{action}' requires a target\")")
        append("            elem = _resolve_element(driver, target)")
        append("")
        append("            if action == 'type':")
        append("                text = value or ''")
        append("                elem.clear()")
        append("                elem.send_keys(text)")
        append("")
        append("            elif action == 'click':")
        append("                selector = _get_selector(target)")
        append("                WebDriverWait(driver, 15).until(")
        append("                    EC.element_to_be_clickable((By.CSS_SELECTOR, selector))")
        append("                )")
        append("                elem.click()")
        append("")
        append("            elif action == 'assert_visible':")
        append("                assert elem.is_displayed(), f\"Element '{target}' is not visible\"")
        append("")
        append("            elif action == 'assert_disabled':")
        append("                assert not elem.is_enabled(), f\"Element '{target}' is not disabled\"")
        append("")
        append("            elif action == 'assert_text':")
        append("                expected = value or ''")
        append("                actual = (elem.text or '').strip()")
        append("                assert expected in actual, f\"Expected text '{expected}' in '{actual}'\"")
        append("")
        append("        elif action == 'assert_url_contains':")
        append("            fragment = value or ''")
        append("            current_url = driver.current_url")
        append("            assert fragment in current_url, f\"Expected '{fragment}' in URL '{current_url}'\"")
        append("")
        append("        else:")
        append("            raise AssertionError(f\"Unsupported action: {action}\")")
        append("")
        append("")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Selenium tests from LangChain test specs.")
    parser.add_argument(
        "--tests",
        required=True,
        type=Path,
        help="Path to JSON file containing test specs (list or {\"test_cases\": [...]})",
    )
    parser.add_argument(
        "--ui-context",
        required=True,
        type=Path,
        help="Path to JSON file containing UI context (elements with selectors).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("generated_selenium_tests.py"),
        help="Output .py file path for generated tests.",
    )

    args = parser.parse_args()

    test_specs = load_test_specs(args.tests)
    with args.ui_context.open("r", encoding="utf-8") as f:
        ui_context = json.load(f)

    generate_selenium_tests(test_specs, ui_context, args.output)

    print(f"✅ Generated Selenium tests: {args.output}")
    print("   Run them with: pytest", args.output.name)


if __name__ == "__main__":
    main()


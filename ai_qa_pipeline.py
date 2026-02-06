import json
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from urllib.parse import urlparse

from openai import OpenAI
from webdriver_manager.chrome import ChromeDriverManager


@dataclass
class TestCase:
    id: str
    name: str
    description: str
    steps: List[Dict[str, str]]
    expected_result: str
    priority: str  # High, Medium, Low
    element_selectors: Dict[str, str]
    test_type: str  # functional, ui, security, performance


@dataclass
class TestResult:
    test_case: TestCase
    status: str  # PASS, FAIL, SKIPPED
    execution_time: float
    error_message: Optional[str] = None
    screenshot_path: Optional[str] = None
    dom_snapshot: Optional[str] = None


class AIQAPipeline:
    def __init__(self, openai_api_key: str):
        self.openai_api_key = openai_api_key
        self.client = OpenAI(api_key=openai_api_key)
        self.driver: Optional[webdriver.Chrome] = None
        self.test_results: List[TestResult] = []

    # ----------------------------
    # Page analysis
    # ----------------------------
    def analyze_webpage(self, url: str) -> Dict[str, Any]:
        """Analyze webpage structure and content."""
        print(f"🔍 Analyzing webpage: {url}")

        response = requests.get(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/119.0 Safari/537.36"
                )
            },
            timeout=30,
        )
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        page_info: Dict[str, Any] = {
            "url": url,
            "title": soup.title.string.strip() if soup.title and soup.title.string else "No title",
            "forms": [],
            "buttons": [],
            "links": [],
            "inputs": [],
            "images": [],
            "meta_tags": {
                meta.get("name", meta.get("property", "unknown")): meta.get("content", "")
                for meta in soup.find_all("meta")
            },
            "page_structure": self._analyze_structure(soup),
            "technologies": self._detect_technologies(soup, response.headers),
        }

        # Forms
        for form in soup.find_all("form"):
            page_info["forms"].append(
                {
                    "id": form.get("id"),
                    "action": form.get("action"),
                    "method": form.get("method", "get").lower(),
                }
            )

        # Buttons (button + input[type=button|submit])
        for button in soup.find_all(["button", "input"]):
            b_type = button.get("type", "").lower()
            if button.name == "button" or b_type in ["submit", "button"]:
                page_info["buttons"].append(
                    {
                        "text": (button.text or "").strip(),
                        "id": button.get("id"),
                        "name": button.get("name"),
                    }
                )

        # Links
        for link in soup.find_all("a", href=True):
            page_info["links"].append(
                {
                    "text": (link.text or "").strip()[:50],
                    "href": link["href"],
                }
            )

        return page_info

    def _analyze_structure(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Analyze page structure for testing."""
        return {
            "headings": {f"h{i}": len(soup.find_all(f"h{i}")) for i in range(1, 7)},
            "sections": len(soup.find_all(["section", "article", "div"])),
            "interactive_elements": len(soup.find_all(["button", "a", "input", "select"])),
        }

    def _detect_technologies(self, soup: BeautifulSoup, headers: Dict[str, str]) -> List[str]:
        """Detect web technologies used."""
        techs: List[str] = []

        # Scripts
        for script in soup.find_all("script"):
            src = script.get("src", "").lower()
            if "react" in src:
                techs.append("React")
            if "vue" in src:
                techs.append("Vue")
            if "angular" in src:
                techs.append("Angular")
            if "jquery" in src:
                techs.append("jQuery")

        # Headers
        x_powered_by = headers.get("x-powered-by")
        if x_powered_by:
            techs.append(x_powered_by)

        return sorted(set(techs))

    # ----------------------------
    # AI test generation
    # ----------------------------
    def generate_test_cases(self, page_info: Dict[str, Any], num_cases: int = 10) -> List[TestCase]:
        """Use AI to generate test cases based on page analysis."""
        print("🤖 Generating test cases with AI...")

        prompt = f"""
You are a senior QA engineer specializing in automated web testing.

Based on this webpage analysis, generate {num_cases} comprehensive test cases.

Page Title: {page_info['title']}
URL: {page_info['url']}
Technologies: {', '.join(page_info['technologies'])}

Page Structure:
- Forms: {len(page_info['forms'])}
- Buttons: {len(page_info['buttons'])}
- Links: {len(page_info['links'])}

Generate test cases covering:
1. Functional testing (form submissions, button clicks, navigation)
2. UI testing (layout, responsive design, accessibility)
3. Content validation (text, images, meta tags)
4. Error scenarios (invalid inputs, broken links)
5. Performance considerations

Format each test case as JSON with these fields:
- id: unique identifier
- name: descriptive test name
- description: what this test validates
- steps: array of objects with "action" and "element" fields
- expected_result: expected outcome
- priority: High/Medium/Low
- element_selectors: suggested CSS selectors for elements
- test_type: functional/ui/security/performance

Return ONLY a JSON array of test cases, with no extra commentary.
"""

        try:
            completion = self.client.chat.completions.create(
                model="gpt-4.1-mini",
                messages=[
                    {"role": "user", "content": prompt},
                ],
                temperature=0.7,
                max_tokens=3000,
            )

            content = completion.choices[0].message.content.strip()

            # Handle fenced JSON if the model wraps it in ```json ``` blocks
            if content.startswith("```"):
                content = content.lstrip("`")
                if content.lower().startswith("json"):
                    content = content[4:]
                content = content.strip("`").strip()

            test_cases_json = json.loads(content)
            test_cases: List[TestCase] = []

            for i, tc in enumerate(test_cases_json):
                test_cases.append(
                    TestCase(
                        id=tc.get("id", f"test_{i+1:03d}"),
                        name=tc["name"],
                        description=tc["description"],
                        steps=tc["steps"],
                        expected_result=tc["expected_result"],
                        priority=tc.get("priority", "Medium"),
                        element_selectors=tc.get("element_selectors", {}),
                        test_type=tc.get("test_type", "functional"),
                    )
                )

            print(f"✅ Generated {len(test_cases)} test cases")
            return test_cases

        except Exception as e:
            print(f"❌ Error generating test cases via OpenAI, falling back to basic set: {e}")
            return self._generate_basic_test_cases(page_info)

    def _generate_basic_test_cases(self, page_info: Dict[str, Any]) -> List[TestCase]:
        """Fallback test case generation when AI fails."""
        base_tests = [
            TestCase(
                id="test_001",
                name="Page title validation",
                description="Verify page title is present and relevant",
                steps=[{"action": "load_page", "element": "document"}],
                expected_result=f"Page title contains '{page_info['title']}'",
                priority="High",
                element_selectors={"title": "title"},
                test_type="ui",
            ),
            TestCase(
                id="test_002",
                name="Main navigation test",
                description="Verify main navigation links are clickable",
                steps=[{"action": "click", "element": "main_nav_link"}],
                expected_result="Navigation works without errors",
                priority="High",
                element_selectors={"main_nav_link": "nav a"},
                test_type="functional",
            ),
        ]
        return base_tests

    # ----------------------------
    # Selenium driver management
    # ----------------------------
    def initialize_driver(self, headless: bool = True) -> None:
        """Initialize Selenium WebDriver (Chrome)."""
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
        self.driver.implicitly_wait(10)

    # ----------------------------
    # Test execution
    # ----------------------------
    def execute_test_case(self, test_case: TestCase, url: str) -> TestResult:
        """Execute a single test case using Selenium."""
        if not self.driver:
            raise RuntimeError("Driver is not initialized. Call initialize_driver() first.")

        print(f"▶️ Executing: {test_case.name}")
        start_time = time.time()

        os.makedirs("screenshots", exist_ok=True)

        try:
            # Load the page
            self.driver.get(url)
            time.sleep(2)  # Allow page to load

            # Execute steps
            for step in test_case.steps:
                self._execute_step(step, test_case.element_selectors)

            # Take screenshot for evidence
            screenshot_path = f"screenshots/{test_case.id}_{int(time.time())}.png"
            self.driver.save_screenshot(screenshot_path)

            # Take DOM snapshot
            dom_snapshot = self.driver.page_source[:5000]  # First 5000 chars

            result = TestResult(
                test_case=test_case,
                status="PASS",
                execution_time=time.time() - start_time,
                screenshot_path=screenshot_path,
                dom_snapshot=dom_snapshot,
            )
            self.test_results.append(result)
            return result

        except Exception as e:
            screenshot_path = f"screenshots/{test_case.id}_FAIL_{int(time.time())}.png"
            try:
                if self.driver:
                    self.driver.save_screenshot(screenshot_path)
            except Exception:
                screenshot_path = None

            result = TestResult(
                test_case=test_case,
                status="FAIL",
                execution_time=time.time() - start_time,
                error_message=str(e),
                screenshot_path=screenshot_path,
            )
            self.test_results.append(result)
            return result

    def _execute_step(self, step: Dict[str, str], selectors: Dict[str, str]) -> None:
        """Execute a single test step."""
        if not self.driver:
            raise RuntimeError("Driver is not initialized.")

        action = step.get("action", "")
        element_key = step.get("element", "")

        def resolve_selector(key: str) -> str:
            return selectors.get(key, key)

        if action == "click":
            selector = resolve_selector(element_key)
            element = self.driver.find_element(By.CSS_SELECTOR, selector)
            element.click()

        elif action == "input":
            selector = resolve_selector(element_key)
            element = self.driver.find_element(By.CSS_SELECTOR, selector)
            value = step.get("value", "Test Input")
            element.clear()
            element.send_keys(value)

        elif action == "verify":
            selector = resolve_selector(element_key)
            element = self.driver.find_element(By.CSS_SELECTOR, selector)
            assert element.is_displayed()

        elif action == "navigate":
            # Navigate to a URL
            self.driver.get(element_key)

        elif action == "scroll":
            selector = resolve_selector(element_key)
            element = self.driver.find_element(By.CSS_SELECTOR, selector)
            self.driver.execute_script("arguments[0].scrollIntoView();", element)

        elif action == "wait_for":
            selector = resolve_selector(element_key)
            timeout = int(step.get("timeout", 10))
            WebDriverWait(self.driver, timeout).until(
                EC.visibility_of_element_located((By.CSS_SELECTOR, selector))
            )

        elif action == "load_page":
            # Already handled at beginning of test; keep as no-op
            pass

        time.sleep(1)  # Brief pause between steps

    # ----------------------------
    # Reporting
    # ----------------------------
    def generate_report(self, results: List[TestResult], output_format: str = "html") -> str:
        """Generate comprehensive test report."""
        print("📊 Generating test report...")

        if output_format == "html":
            return self._generate_html_report(results)
        elif output_format == "json":
            return self._generate_json_report(results)
        else:
            return self._generate_text_report(results)

    def _generate_html_report(self, results: List[TestResult]) -> str:
        """Generate HTML report with basic styling and charts."""
        from datetime import datetime

        os.makedirs("reports", exist_ok=True)

        total = len(results)
        passed = sum(1 for r in results if r.status == "PASS")
        failed = sum(1 for r in results if r.status == "FAIL")
        pass_rate = (passed / total * 100) if total > 0 else 0.0

        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8" />
            <title>AI QA Test Report</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 40px; background: #f1f3f5; }}
                .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                         color: white; padding: 30px; border-radius: 10px; }}
                .stats {{ display: flex; gap: 20px; margin: 30px 0; flex-wrap: wrap; }}
                .stat-card {{ flex: 1; min-width: 160px; padding: 20px; border-radius: 8px;
                            background: #fff; box-shadow: 0 2px 10px rgba(0,0,0,0.08); }}
                .passed {{ border-left: 5px solid #28a745; }}
                .failed {{ border-left: 5px solid #dc3545; }}
                .test-case {{ margin: 20px 0; padding: 15px; border-radius: 5px;
                            background: #fff; border-left: 4px solid #007bff;
                            box-shadow: 0 1px 4px rgba(0,0,0,0.04); }}
                .screenshot {{ max-width: 300px; border: 1px solid #ddd; margin: 10px 0; }}
                .priority-high {{ border-left-color: #dc3545; }}
                .priority-medium {{ border-left-color: #ffc107; }}
                .priority-low {{ border-left-color: #28a745; }}
                code {{ background: #f8f9fa; padding: 2px 4px; border-radius: 3px; }}
            </style>
            <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        </head>
        <body>
            <div class="header">
                <h1>🤖 AI-Powered QA Test Report</h1>
                <p>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            </div>

            <div class="stats">
                <div class="stat-card">
                    <h3>Total Tests</h3>
                    <h2>{total}</h2>
                </div>
                <div class="stat-card passed">
                    <h3>Passed</h3>
                    <h2>{passed} ({pass_rate:.1f}%)</h2>
                </div>
                <div class="stat-card failed">
                    <h3>Failed</h3>
                    <h2>{failed}</h2>
                </div>
            </div>

            <canvas id="resultsChart" width="400" height="200"></canvas>

            <h2>Detailed Results</h2>
        """

        for result in results:
            priority_class = f"priority-{result.test_case.priority.lower()}"
            status_color = "green" if result.status == "PASS" else "red"

            html += f"""
            <div class="test-case {priority_class}">
                <h3>{result.test_case.name}
                    <span style="float:right; color: {status_color}">
                        {result.status}
                    </span>
                </h3>
                <p><strong>Description:</strong> {result.test_case.description}</p>
                <p><strong>Priority:</strong> {result.test_case.priority}</p>
                <p><strong>Type:</strong> {result.test_case.test_type}</p>
                <p><strong>Execution Time:</strong> {result.execution_time:.2f}s</p>
                <p><strong>Expected:</strong> {result.test_case.expected_result}</p>
            """

            if result.error_message:
                html += f'<p style="color:red;"><strong>Error:</strong> {result.error_message}</p>'

            if result.screenshot_path:
                html += (
                    f'<img src="../{result.screenshot_path}" '
                    f'class="screenshot" alt="Test Evidence" />'
                )

            html += "</div>"

        html += """
        <script>
            const ctx = document.getElementById('resultsChart').getContext('2d');
            new Chart(ctx, {
                type: 'doughnut',
                data: {
                    labels: ['Passed', 'Failed'],
                    datasets: [{
                        data: [""" + str(passed) + """, """ + str(failed) + """],
                        backgroundColor: ['#28a745', '#dc3545']
                    }]
                },
                options: {
                    responsive: true,
                    plugins: {
                        legend: { position: 'top' },
                        title: {
                            display: true,
                            text: 'Test Results Distribution'
                        }
                    }
                }
            });
        </script>
        </body>
        </html>
        """

        from datetime import datetime

        report_filename = f"test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        report_path = os.path.join("reports", report_filename)
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(html)

        print(f"📄 Report saved to: {report_path}")
        return report_path

    def _generate_json_report(self, results: List[TestResult]) -> str:
        """Generate JSON report."""
        os.makedirs("reports", exist_ok=True)

        report_data = {
            "summary": {
                "total_tests": len(results),
                "passed": sum(1 for r in results if r.status == "PASS"),
                "failed": sum(1 for r in results if r.status == "FAIL"),
                "execution_time": sum(r.execution_time for r in results),
            },
            "results": [
                {
                    "test_id": r.test_case.id,
                    "name": r.test_case.name,
                    "status": r.status,
                    "execution_time": r.execution_time,
                    "error": r.error_message,
                    "screenshot_path": r.screenshot_path,
                }
                for r in results
            ],
        }

        report_path = os.path.join("reports", f"test_report_{int(time.time())}.json")
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report_data, f, indent=2)

        print(f"📄 JSON report saved to: {report_path}")
        return report_path

    def _generate_text_report(self, results: List[TestResult]) -> str:
        """Generate a simple text report."""
        os.makedirs("reports", exist_ok=True)

        lines: List[str] = []
        lines.append("AI QA Test Report")
        lines.append("=" * 40)
        lines.append("")

        total = len(results)
        passed = sum(1 for r in results if r.status == "PASS")
        failed = sum(1 for r in results if r.status == "FAIL")

        lines.append(f"Total tests: {total}")
        lines.append(f"Passed: {passed}")
        lines.append(f"Failed: {failed}")
        lines.append("")

        for r in results:
            lines.append(f"[{r.status}] {r.test_case.id} - {r.test_case.name}")
            if r.error_message:
                lines.append(f"  Error: {r.error_message}")

        report_path = os.path.join("reports", f"test_report_{int(time.time())}.txt")
        with open(report_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        print(f"📄 Text report saved to: {report_path}")
        return report_path

    # ----------------------------
    # Orchestration
    # ----------------------------
    def run_pipeline(self, url: str, num_tests: int = 5, headless: bool = True) -> (List[TestResult], str):
        """Complete pipeline execution."""
        print("🚀 Starting AI QA Pipeline...")

        # Step 1: Analyze webpage
        page_info = self.analyze_webpage(url)

        # Step 2: Generate test cases
        test_cases = self.generate_test_cases(page_info, num_tests)

        # Step 3: Initialize Selenium
        self.initialize_driver(headless=headless)

        # Step 4: Execute tests
        results: List[TestResult] = []
        try:
            for test_case in test_cases:
                result = self.execute_test_case(test_case, url)
                results.append(result)
                print(f"  {test_case.id}: {result.status} ({result.execution_time:.2f}s)")
        finally:
            # Always try to clean up driver
            if self.driver:
                self.driver.quit()
                self.driver = None

        # Step 5: Generate report
        report_path = self.generate_report(results, "html")

        print("\n✅ Pipeline completed!")
        print(f"📋 Test Summary: {len([r for r in results if r.status=='PASS'])}/{len(results)} passed")
        print(f"📄 Report: {report_path}")

        return results, report_path


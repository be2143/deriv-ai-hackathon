"""
Main Flask app: ingest URL + optional PRD file, run pipeline sequentially, show results.

Usage:
    export OPENAI_API_KEY=...
    export GOOGLE_API_KEY=...   # optional, for PRD extraction
    python app.py

Then open http://127.0.0.1:5000/ — enter URL, optionally upload PRD, click Start Test.
"""

import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

# Ensure project root and server are on path (for server.* and langchain_ui_test_pipeline)
_ROOT = Path(__file__).resolve().parent
_SERVER = _ROOT / "server"
for p in (_ROOT, _SERVER):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import requests
from flask import Flask, redirect, render_template, request, send_from_directory, url_for

# Server pipeline imports
from server.execute_test_specs import TestExecutor
from server.langchain_ui_test_pipeline import run_langchain_ui_test_pipeline, UITestEngineInput
from server.run_langchain_ui_pipeline import build_demo_requirements
from server.ui_context_loader import load_ui_context_from_html


app = Flask(__name__, template_folder=str(_ROOT / "templates"))
REPORTS_DIR = _ROOT / "reports"
SERVER_REPORTS = _ROOT / "server" / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)
SERVER_REPORTS.mkdir(parents=True, exist_ok=True)


def _fetch_url_as_html(url: str) -> str:
    """Fetch URL and return HTML (for static pages)."""
    resp = requests.get(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0 Safari/537.36"
            )
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.text


def _run_pipeline_sequential(url: str, prd_file_path: Optional[Path]) -> dict:
    """
    Run the full pipeline sequentially:
    1) UI context from URL (fetch HTML → parse)
    2) Requirements from PRD file or demo
    3) Generate test specs (LangChain)
    4) Execute tests (Selenium)
    5) Build report

    Returns dict with: url, total, passed, failed, report_filename, error (if any).
    """
    from langchain_openai import ChatOpenAI

    result = {
        "url": url,
        "total": 0,
        "passed": 0,
        "failed": 0,
        "report_filename": "",
        "error": None,
        "results": [],
    }

    # 1) UI context from URL
    try:
        html_content = _fetch_url_as_html(url)
    except Exception as e:
        result["error"] = f"Failed to fetch URL: {e}"
        return result

    with tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=False, encoding="utf-8") as f:
        f.write(html_content)
        temp_html = f.name
    try:
        ui_context = load_ui_context_from_html(Path(temp_html))
        ui_context["page_url"] = url
    finally:
        try:
            os.unlink(temp_html)
        except Exception:
            pass

    if not ui_context.get("elements"):
        result["error"] = "No interactive elements found on the page."
        return result

    # 2) Requirements
    if prd_file_path and prd_file_path.exists():
        try:
            from server.ai_input_processor import process_document
            reqs_data = process_document(str(prd_file_path))
            functional = reqs_data.get("functional_requirements", [])
            non_functional = reqs_data.get("non_functional_requirements", [])
            user_flow = reqs_data.get("user_flow_context", [])
            overview = reqs_data.get("overview")
            frontend_features = reqs_data.get("frontend_features")
        except Exception as e:
            functional = ["Verify page loads and key elements are usable."]
            non_functional = []
            user_flow = []
            overview = None
            frontend_features = None
    else:
        demo = build_demo_requirements()
        functional = demo.get("functional", ["Verify page loads and key elements are usable."])
        non_functional = demo.get("non_functional", [])
        user_flow = demo.get("user_flow", [])
        overview = None
        frontend_features = None

    payload = UITestEngineInput(
        ui_context=ui_context,
        functional_requirements=functional,
        non_functional_requirements=non_functional,
        user_flow_context=user_flow,
        overview=overview,
        frontend_features=frontend_features,
    )

    # 3) Generate test specs
    try:
        llm = ChatOpenAI(model="gpt-4.1-mini", temperature=0.0)
        test_specs = run_langchain_ui_test_pipeline(llm, payload, save_to_reports=False)
    except Exception as e:
        result["error"] = f"Test generation failed: {e}"
        return result

    if not test_specs:
        result["error"] = "No test cases were generated."
        return result

    # 4) Execute tests
    executor = TestExecutor(headless=True)
    execution_results = []
    try:
        for spec in test_specs:
            try:
                res = executor.execute_test_spec(spec, ui_context)
                res["test_name"] = spec.test_name
                res["description"] = getattr(spec, "description", "") or ""
                execution_results.append(res)
            except Exception as e:
                execution_results.append({
                    "test_name": spec.test_name,
                    "description": getattr(spec, "description", "") or "",
                    "status": "FAIL",
                    "error_message": str(e),
                    "execution_time": 0,
                    "steps_executed": [],
                })
    finally:
        executor.close()

    result["total"] = len(execution_results)
    result["passed"] = sum(1 for r in execution_results if r.get("status") == "PASS")
    result["failed"] = result["total"] - result["passed"]
    result["results"] = execution_results

    # 5) Save JSON results and build HTML report
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_url = url.replace("https://", "").replace("http://", "").replace("/", "_")[:60]
    report_base = f"test_report_{safe_url}_{timestamp}"
    report_json = REPORTS_DIR / f"{report_base}.json"
    report_html = REPORTS_DIR / f"{report_base}.html"

    summary = {
        "url": url,
        "executed_at": datetime.now().isoformat(),
        "total_tests": result["total"],
        "passed": result["passed"],
        "failed": result["failed"],
        "results": execution_results,
    }
    with open(report_json, "w", encoding="utf-8") as f:
        import json
        json.dump(summary, f, indent=2, ensure_ascii=False)

    html_content = _build_html_report(summary)
    report_html.write_text(html_content, encoding="utf-8")

    result["report_filename"] = report_html.name
    return result


def _build_html_report(summary: dict) -> str:
    """Build an HTML report with expandable test case details (description + step list)."""
    import html as html_module
    rows = []
    for i, r in enumerate(summary.get("results", [])):
        status = r.get("status", "UNKNOWN")
        name = html_module.escape(r.get("test_name", ""))
        err = html_module.escape((r.get("error_message") or "")[:500])
        duration = r.get("execution_time", 0)
        desc = html_module.escape((r.get("description") or "").strip())
        steps = r.get("steps_executed", [])
        total_steps = r.get("total_steps", len(steps))
        passed_steps = r.get("passed_steps", len([s for s in steps if s.get("status") == "PASS"]))
        step_lines = []
        for s in steps:
            st = s.get("status", "PASS")
            icon = "✓" if st == "PASS" else "✗"
            action = html_module.escape(s.get("action", ""))
            target = html_module.escape(str(s.get("target", "")))
            val = html_module.escape(str(s.get("value", "")))
            dur = s.get("duration", 0)
            step_err = html_module.escape(str(s.get("error", "")))
            extra = f", value={val}" if val else ""
            step_lines.append(
                f'<div class="step-row step-{st.lower()}">'
                f'<span class="step-icon">{icon}</span> '
                f'Step {s.get("step", 0)}: {action} (target={target}{extra}, duration={dur:.2f}s) '
                + (f'<span class="step-err">Error: {step_err}</span>' if step_err else "")
                + "</div>"
            )
        steps_html = "\n".join(step_lines) if step_lines else "<p class='no-steps'>No step data.</p>"
        rows.append(f"""
        <tr class="test-row" data-index="{i}" role="button" tabindex="0">
          <td class="test-name"><span class="toggle-icon" aria-hidden="true">▶</span> {name}</td>
          <td><span class="badge {'pass' if status == 'PASS' else 'fail'}">{status}</span></td>
          <td>{duration:.2f}s</td>
          <td>{err[:200] if err else '—'}</td>
        </tr>
        <tr class="details-row" id="details-{i}" hidden>
          <td colspan="4" class="details-cell">
            <div class="details-inner">
              <p class="test-desc"><strong>Description:</strong> {desc or '—'}</p>
              <p class="steps-summary">Steps: {passed_steps}/{total_steps} passed</p>
              <div class="step-details">{steps_html}</div>
              {f'<p class="test-err"><strong>Error:</strong> {err}</p>' if err else ''}
            </div>
          </td>
        </tr>""")
    rows_html = "\n".join(rows)
    url_esc = html_module.escape(summary.get("url", ""))
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Test Report - {url_esc[:50]}</title>
  <style>
    body {{ font-family: system-ui,sans-serif; margin: 24px; background: #f9fafb; }}
    h1 {{ font-size: 20px; }}
    table {{ border-collapse: collapse; width: 100%; background: #fff; border-radius: 12px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }}
    th, td {{ padding: 12px 14px; text-align: left; border-bottom: 1px solid #e5e7eb; }}
    th {{ background: #f3f4f6; font-weight: 600; }}
    .badge {{ padding: 4px 8px; border-radius: 999px; font-size: 12px; font-weight: 600; }}
    .badge.pass {{ background: #dcfce7; color: #166534; }}
    .badge.fail {{ background: #fee2e2; color: #b91c1c; }}
    .meta {{ color: #6b7280; font-size: 14px; margin-bottom: 16px; }}
    .test-row {{ cursor: pointer; }}
    .test-row:hover {{ background: #f3f4f6; }}
    .test-row.expanded .toggle-icon {{ transform: rotate(90deg); }}
    .toggle-icon {{ display: inline-block; transition: transform 0.15s ease; margin-right: 6px; font-size: 10px; }}
    .details-cell {{ background: #f9fafb; padding: 16px 14px 20px; border-bottom: 1px solid #e5e7eb; vertical-align: top; }}
    .details-inner {{ max-width: 100%; }}
    .test-desc {{ margin: 0 0 10px; font-size: 13px; color: #374151; }}
    .steps-summary {{ margin: 0 0 8px; font-size: 12px; color: #6b7280; }}
    .step-details {{ font-family: ui-monospace, monospace; font-size: 12px; }}
    .step-row {{ margin: 4px 0; padding: 6px 8px; border-radius: 6px; }}
    .step-row.step-pass {{ background: #dcfce7; color: #166534; }}
    .step-row.step-fail {{ background: #fee2e2; color: #b91c1c; }}
    .step-icon {{ font-weight: bold; }}
    .step-err {{ display: block; margin-top: 4px; color: #b91c1c; }}
    .test-err {{ margin: 10px 0 0; font-size: 12px; color: #b91c1c; }}
    .no-steps {{ margin: 0; color: #6b7280; font-size: 12px; }}
  </style>
</head>
<body>
  <h1>Test execution report</h1>
  <p class="meta">URL: {url_esc} · {summary.get('total_tests', 0)} tests · {summary.get('passed', 0)} passed, {summary.get('failed', 0)} failed</p>
  <table>
    <thead><tr><th>Test</th><th>Status</th><th>Time</th><th>Error</th></tr></thead>
    <tbody>
    {rows_html}
    </tbody>
  </table>
  <script>
    document.querySelectorAll('.test-row').forEach(function(row) {{
      row.addEventListener('click', function() {{
        var idx = this.getAttribute('data-index');
        var details = document.getElementById('details-' + idx);
        var isHidden = details.hidden;
        document.querySelectorAll('.details-row').forEach(function(r) {{ r.hidden = true; }});
        document.querySelectorAll('.test-row').forEach(function(r) {{ r.classList.remove('expanded'); }});
        if (isHidden) {{ details.hidden = false; this.classList.add('expanded'); }}
      }});
    }});
  </script>
</body>
</html>"""


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/run", methods=["POST"])
def run():
    url = (request.form.get("url") or "").strip()
    if not url:
        return render_template("index.html", error="URL is required."), 400
    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url

    prd_path = None
    prd_file = request.files.get("prd_file")
    if prd_file and prd_file.filename:
        suffix = Path(prd_file.filename).suffix or ".txt"
        fd, path = tempfile.mkstemp(suffix=suffix)
        os.close(fd)
        prd_file.save(path)
        prd_path = Path(path)

    try:
        result = _run_pipeline_sequential(url, prd_path)
    except Exception as e:
        result = {
            "url": url,
            "total": 0,
            "passed": 0,
            "failed": 0,
            "report_filename": "",
            "error": str(e),
        }
    finally:
        if prd_path and prd_path.exists():
            try:
                prd_path.unlink()
            except Exception:
                pass

    if result.get("error"):
        return render_template("index.html", error=result["error"], url=url), 400

    return redirect(
        url_for(
            "results",
            url=result["url"],
            total=result["total"],
            passed=result["passed"],
            failed=result["failed"],
            report=result["report_filename"],
        )
    )


@app.route("/results")
def results():
    url = request.args.get("url", "")
    total = request.args.get("total", "0")
    passed = request.args.get("passed", "0")
    failed = request.args.get("failed", "0")
    report_filename = request.args.get("report", "")
    return render_template(
        "results.html",
        url=url,
        total=total,
        passed=passed,
        failed=failed,
        report_filename=report_filename or "report.html",
    )


@app.route("/reports/<path:filename>")
def report_file(filename):
    return send_from_directory(REPORTS_DIR, filename, as_attachment=False)


def main():
    if not os.environ.get("OPENAI_API_KEY"):
        print("Set OPENAI_API_KEY before running.")
        sys.exit(1)
    app.run(host="0.0.0.0", port=5000, debug=False)


if __name__ == "__main__":
    main()

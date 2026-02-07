# AI-Powered UI Test Pipeline

An end-to-end system that turns a **target URL** and optional **product requirements document** into **browser tests** and **execution reports**. The backend runs a sequential pipeline: document parsing, web scraping / UI context extraction, AI-driven test generation, Selenium execution, and report generation.

---

## Features

- **Web UI**: Enter a URL and optionally upload a PRD (PDF, DOCX, MD, TXT). Start a run and get a results page with pass/fail counts and a link to a detailed HTML report.
- **Document-aware tests**: Uploaded docs are parsed and converted into structured requirements (overview, functional, non-functional, user flows) and fed into test generation.
- **Format-agnostic UI context**: Accepts JSON from any crawl tool or saved HTML; the pipeline normalizes and uses elements, headings, forms, and links from any website.
- **Structured test specs**: Tests are generated as JSON (test name, description, steps with action/target/value), validated against the UI context, then executed with Selenium.
- **Interactive reports**: HTML report with expandable rows: click a test to see description, step list, and per-step pass/fail and errors.

---

## Architecture Overview

```
User (URL + optional PRD file)
           │
           ▼
┌──────────────────────────────────────────────────────────────────┐
│  Web app (Flask) – templates/index.html, results.html             │
└──────────────────────────────────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────────────────────┐
│  Backend pipeline (sequential)                                    │
│  1. Document parser / data extractor  (optional, if PRD uploaded)  │
│  2. Web scraper / UI context builder                              │
│  3. AI test generator                                              │
│  4. Test executor                                                  │
│  5. Report generator                                               │
└──────────────────────────────────────────────────────────────────┘
           │
           ▼
  Results page + detailed HTML report (reports/*.html)
```

---

## Backend Substeps (Detailed)

### 1. Document parser & data extractor

**Role:** Turn an uploaded product requirements document into structured data for the test generator.

**Module:** `server/ai_input_processor.py`

**What it does:**

- **Text extraction** from:
  - **PDF** – `pdfplumber`
  - **DOCX** – `python-docx`
  - **Markdown** – markdown + BeautifulSoup (with fallbacks)
  - **TXT** – plain text with `chardet` for encoding
- **Preprocessing**: clean and normalize text (citations, whitespace).
- **Structured extraction** via **Google Gemini**: prompt the model to fill a fixed schema:
  - `overview` – high-level app/feature summary
  - `frontend_features` – list of UI features/components
  - `functional_requirements` – what the UI must do
  - `non_functional_requirements` – performance, accessibility, UX
  - `user_flow_context` – user flows and context

**Output:** A JSON-serializable dict matching the shape expected by the AI test generator (e.g. saved under `server/reports/extracted_requirements_*.json`).

**CLI:** Run extraction only via `server/test_ai_input_processor.py` or by calling `process_document(path)` from code.

---

### 2. Web scraper / UI context builder

**Role:** Obtain a machine-readable representation of the target page (elements, selectors, labels) for test generation and execution.

**Modules:**

- **Fetch + HTML parsing:** `app.py` uses `requests` to fetch the URL; the response HTML is written to a temp file.
- **UI context from HTML:** `server/ui_context_loader.py` – `load_ui_context_from_html(file_path)`:
  - Parses HTML with **BeautifulSoup**.
  - Collects **links** (`<a href>`), **buttons**, **inputs**, **selects**, **textareas**, `[role="button"]`, and **headings** (h1–h6).
  - For each item builds a **CSS selector** (id → `#id`, name → `[name='...']`, links → `a[href='...']`, then tag+class, then tag).
  - Outputs a single structure: `page_url`, `title`, `elements` (each with `tag`, `role`, `css_selector`, `id`/`name`/`type`/`text`/`label` as available).
- **UI context from JSON:** `server/run_langchain_ui_pipeline.py` – `load_ui_context_from_json()` supports:
  - Direct format: `{ "page_url", "elements" }`
  - Single page: `{ "pages": { "page_url", "elements", "headings", "forms" } }`
  - Multiple pages: `{ "pages": [ ... ] }` (first page + aggregated elements).

So the “web scraper” step is either **fetch URL → save HTML → parse to UI context** (Web UI / app) or **load an existing JSON/HTML file** (CLI). Crawl outputs from other tools (e.g. Selenium crawlers that produce JSON with `elements`/`headings`/`forms`) are also supported.

**Output:** A **UI context** dict: `page_url`, optional `title`, and at least one of `elements`, `headings`, `forms`, etc., with stable identifiers and `css_selector` for execution.

---

### 3. AI test generator

**Role:** Produce a structured test suite (test name, description, steps) from UI context + requirements, without writing executable code.

**Module:** `server/langchain_ui_test_pipeline.py`

**What it does:**

- **Input:** `UITestEngineInput` – `ui_context` (dict), `functional_requirements`, `non_functional_requirements`, `user_flow_context`, and optional `overview` and `frontend_features` (e.g. from the document extractor).
- **Prompting:** System + developer + user prompts instruct the LLM to:
  - Output **only** valid JSON (no markdown or commentary).
  - Generate **5–15 test cases** covering happy paths, edge cases, errors, UI validation, navigation.
  - Use **allowed actions**: `navigate`, `type`, `click`, `assert_visible`, `assert_text`, `assert_url_contains`, `assert_disabled`.
  - Use for **targets** only `id`, `css_selector`, or visible `text`/`label` from the UI context (no invented selectors).
- **Schema:** Output is parsed into Pydantic models: `TestSuite` → list of `TestSpec` (each with `test_name`, `description`, `steps: List[TestStep]`); each step has `action`, optional `target`, optional `value`.
- **Validation:** Targets in steps are checked against the UI context (elements, headings, forms, links, buttons, page `title`); invalid or “#Link Text”–style targets are rejected; optional retry with corrective prompt.
- **Model:** Uses **LangChain** with **OpenAI** (e.g. `gpt-4.1-mini`) via `with_structured_output(TestSuite)`.

**Output:** A list of `TestSpec` instances (or JSON under `server/reports/test_specs_*.json` when run via CLI).

**CLI:** `server/run_langchain_ui_pipeline.py` with `--ui-context` and `--requirements` (and optional `--execute` to run tests).

---

### 4. Test executor

**Role:** Run the generated test specs in a real browser and record pass/fail and per-step details.

**Module:** `server/execute_test_specs.py`

**What it does:**

- **TestExecutor** uses **Selenium** (Chrome, via `webdriver_manager`) in headless or headed mode.
- **Selector map:** From the same UI context used for generation, builds a mapping from target identifiers (id, name, label, text, `css_selector`, `#container_id`) to a CSS selector; supports `elements`, `headings`, and `forms[].elements` from any structure.
- **Execution:** For each `TestSpec`:
  - Navigate to `page_url`.
  - For each step: resolve `target` to a selector, then perform the action (navigate, type, click, assert_visible, assert_text, assert_url_contains, assert_disabled). Special handling for target `"title"` (page title assertions).
  - Record per-step: `step`, `action`, `target`, `value`, `status` (PASS/FAIL), `duration`, and `error` if the step failed.
- **Result:** One dict per test: `status`, `execution_time`, `error_message`, `steps_executed`, `total_steps`, `passed_steps`.

**Output:** A list of execution result dicts (and optionally JSON under `server/reports/execution_results/` when run via CLI).

**CLI:** `server/execute_test_specs.py` with `--test-specs` and `--ui-context` (JSON or HTML).

---

### 5. Report generator

**Role:** Turn execution results into a summary and a detailed, viewable report.

**Module:** `app.py` (and optionally `server/execute_test_specs.py` for JSON-only output)

**What it does:**

- **Summary:** Aggregates `total`, `passed`, `failed` from the list of execution results.
- **JSON report:** Writes a timestamped file under `reports/` with `url`, `executed_at`, `total_tests`, `passed`, `failed`, and full `results` (each with `test_name`, `description`, `status`, `error_message`, `execution_time`, `steps_executed`, etc.).
- **HTML report:** `_build_html_report(summary)`:
  - One table: Test name, Status (badge), Time, Error.
  - **Expandable rows:** Clicking a row shows:
    - Test **description**
    - **Steps: X/Y passed**
    - Per-step lines: ✓/✗, action, target, value, duration, and error if failed.
  - Writes a timestamped HTML file under `reports/` (e.g. `test_report_<url_safe>_<timestamp>.html`).

**Output:** JSON report + HTML report file; the Web UI redirects to the results page and links “View detailed HTML report” to this file.

---

## Project structure

```
deriv-ai-hackathon/
├── app.py                    # Flask app: Web UI, /run (pipeline trigger), /results, /reports/<file>
├── templates/
│   ├── index.html            # Landing: URL input, optional PRD upload, Start Test
│   └── results.html         # Results: url, total/passed/failed, link to detailed report
├── reports/                  # Generated HTML + JSON reports (and sample report)
├── server/
│   ├── ai_input_processor.py # 1) Document parser & data extractor (Gemini)
│   ├── ui_context_loader.py # 2) HTML → UI context (BeautifulSoup)
│   ├── run_langchain_ui_pipeline.py  # Loaders, demo data, SpecExecutor (minimal)
│   ├── langchain_ui_test_pipeline.py # 3) AI test generator (LangChain + OpenAI)
│   ├── execute_test_specs.py # 4) Test executor (Selenium), load UI context (JSON/HTML)
│   └── reports/              # Extracted requirements, test specs, execution results
├── docs/                     # TechnicalPlan, LangChainPipeline, UI_CONTEXT_FORMAT, etc.
├── requirements.txt
└── README.md
```

---

## Quick start (for hackathon judges)

1. **Clone and install**
   ```bash
   cd deriv-ai-hackathon
   pip install -r requirements.txt
   ```
2. **Set API key** (required for test generation)
   ```bash
   export OPENAI_API_KEY="your-openai-api-key"
   ```
   Or copy `.env.example` to `.env` and fill in `OPENAI_API_KEY`.
3. **Run the app**
   ```bash
   python app.py
   ```
4. **Open** http://127.0.0.1:5000/ — enter a URL (e.g. `https://www.random.org`), optionally upload a PRD, click **Start Test**. A full run takes about 1–2 minutes; you’ll get a results page and a detailed HTML report with expandable test details.
5. **Chrome** must be installed (Selenium uses it for execution). No API key? Use the **“View sample report”** link on the home page to see a pre-generated report (11 passed, 3 failed).

---

## Setup

- **Python:** 3.9+
- **Chrome:** Installed (for Selenium; `webdriver_manager` downloads the matching driver).

```bash
pip install -r requirements.txt
```

**Environment variables:**

- `OPENAI_API_KEY` – **required** for the AI test generator (LangChain/OpenAI).
- `GOOGLE_API_KEY` – **optional**; used by the document extractor (Gemini). If unset, PRD upload falls back to demo requirements.

---

## Running the pipeline

### Web UI (recommended)

Start the Flask app, then open the UI to enter a URL and optionally upload a PRD. The backend runs the full pipeline (fetch → UI context → optional PRD extraction → test generation → Selenium execution → report).

```bash
export OPENAI_API_KEY="your-openai-api-key"
# Optional, for PRD extraction from uploaded PDF/DOCX/MD:
export GOOGLE_API_KEY="your-google-api-key"

python app.py
```

Open **http://127.0.0.1:5000/**. Submit the form; when the run finishes, you get the results page and a link to the detailed HTML report.

### CLI (generation only)

Generate test specs from existing UI context and requirements JSON:

```bash
cd server
python run_langchain_ui_pipeline.py \
  --ui-context reports/page_improved.json \
  --requirements reports/extracted_requirements_*.json
```

### CLI (execution only)

Run existing test specs against a UI context (JSON or HTML):

```bash
cd server
python execute_test_specs.py \
  --test-specs reports/test_specs_*.json \
  --ui-context reports/page_improved.json
```

---

## Documentation

- **`docs/TechnicalPlan.md`** – Architecture, pipeline diagram, design decisions.
- **`docs/LangChainPipeline.md`** – LangChain test spec flow, input/output.
- **`docs/UI_CONTEXT_FORMAT.md`** – Accepted UI context shapes (JSON/HTML, any website).
- **`docs/AI_InputProcessor.md`** – Document extraction (supported formats, Gemini, schema).
- **`docs/AI_TestGenerator.md`** – Test generation and validation.

---

## Hackathon submission checklist

- **Web UI:** Single entry point (URL + optional PRD) with loading state and results page.
- **Pipeline:** Document parser (Gemini) → Web scraper / UI context (requests + BeautifulSoup) → AI test generator (LangChain/OpenAI) → Test executor (Selenium) → Report generator (JSON + HTML).
- **Docs:** README (this file), `docs/` (TechnicalPlan, LangChainPipeline, UI_CONTEXT_FORMAT, AI_InputProcessor, AI_TestGenerator).
- **Run:** `python app.py` then http://127.0.0.1:5000/; `.env.example` for required env vars.
- **Fallback:** “View sample report” on the home page works without API keys to show report UX.

---

## License

See repository or project root for license information.

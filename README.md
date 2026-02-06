## AI QA Pipeline (URL → Tests → Selenium → Report)

This project implements an end-to-end AI-powered QA pipeline:

- **URL input** → page analysis with `requests` + `BeautifulSoup`
- **AI test generation** via OpenAI Chat Completions
- **Selenium execution** with Chrome + `webdriver-manager`
- **HTML report** with pass/fail stats and screenshots

### Setup

- **Python**: 3.9+ recommended
- **Chrome**: Installed locally (or use the provided `Dockerfile`)

Install dependencies:

```bash
pip install -r requirements.txt
```

Set your OpenAI API key:

```bash
export OPENAI_API_KEY="your-openai-api-key"
```

### Running Locally

Basic run:

```bash
python run_qa_pipeline.py --url "https://example.com"
```

Specify number of tests and turn off headless mode:

```bash
python run_qa_pipeline.py --url "https://example.com" --tests 10 --no-headless
```

Outputs:

- Screenshots under `screenshots/`
- HTML report under `reports/` (with basic charts and per-test detail)

### Docker Usage

Build the image:

```bash
docker build -t ai-qa-pipeline .
```

Run (replace URL and API key):

```bash
docker run --rm \
  -e OPENAI_API_KEY="your-openai-api-key" \
  ai-qa-pipeline \
  python run_qa_pipeline.py --url "https://example.com"
```

You can mount a local directory to collect reports:

```bash
docker run --rm \
  -e OPENAI_API_KEY="your-openai-api-key" \
  -v "$PWD/reports:/app/reports" \
  -v "$PWD/screenshots:/app/screenshots" \
  ai-qa-pipeline \
  python run_qa_pipeline.py --url "https://example.com"
```

### GitHub Actions CI

A workflow is included at `.github/workflows/ai-qa.yml`.

- Runs daily at 09:00 UTC
- Can be triggered manually with a custom URL
- Requires a repository secret: **`OPENAI_API_KEY`**
- Uploads the generated `reports/` directory as a build artifact

### Advanced QA Features

`advanced_features.py` includes optional helpers:

- **Accessibility**: simple checks for `img` without `alt` and elements with ARIA roles
- **Performance**: basic metrics from the Navigation Timing API
- **Visual diffs**: perceptual hash comparison between current and baseline screenshots

You can import and call these from your own tests or extend `ai_qa_pipeline.py` to incorporate them into the reporting.


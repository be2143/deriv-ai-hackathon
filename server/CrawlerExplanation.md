# UI-Focused Web Crawler - Documentation

## Overview

The **UI-Focused Crawler** is a structured web crawling engine designed to extract semantic UI information from websites. It's optimized for **LLM-driven UI test generation** - transforming raw DOM structures into clean, structured JSON that AI models can reason about.

### Core Philosophy

> **We are building a DOM → Logical UI representation compiler, not a chaotic browser debugger.**

The crawler focuses on:
- ✅ **Semantic UI structure** - Forms, navigation, buttons, inputs with proper labels
- ✅ **Clean abstraction** - Normalized roles, resolved labels, hierarchical organization
- ✅ **LLM-ready output** - Structured JSON optimized for AI consumption
- ❌ **NOT** a penetration tester or robustness checker
- ❌ **NOT** focused on console errors, network failures, or low-level diagnostics

---

## What It Does

### 1. **Breadth-First Search (BFS) Crawling**
- Crawls websites starting from a seed URL
- Follows internal links to discover pages
- Respects depth limits and page limits
- Stays within the same domain (configurable)
- Normalizes URLs to avoid duplicate crawling

### 2. **Structured UI Extraction**
For each page visited, the crawler extracts:

#### **Headings** (`h1` - `h5`)
- Page structure and context
- Used to understand page hierarchy

#### **Forms**
- Form action and method
- All input fields within the form
- Form labels/headings
- Input types, names, IDs, placeholders
- Required fields and validation patterns

#### **Interactive Elements**
- **Buttons**: `<button>`, `<input type="button">`, elements with `role="button"`
- **Inputs**: Text fields, checkboxes, radio buttons, selects, textareas
- **Links**: Navigation links, footer links, main content links

#### **Element Metadata**
For each element:
- **Identifiers**: `id`, `name`, `data-testid`, `data-test`, `data-qa`, `aria-label`
- **Semantic Role**: Normalized role (button, input, link, dropdown, etc.)
- **Label**: Resolved human-readable label using multiple strategies
- **Visibility**: Whether element is visible and enabled
- **Attributes**: Type, placeholder, required status, options (for selects)

### 3. **Smart Label Resolution**
The crawler implements a priority-based label resolution system:

1. `<label for="input_id">` - Explicit label association
2. Parent `<label>` element
3. `aria-labelledby` attribute
4. `aria-label` attribute
5. `title` attribute
6. `placeholder` attribute (for inputs)
7. Preceding sibling text
8. Nearest heading
9. Fallback to `name`, `id`, or `data-testid`

### 4. **Cookie Banner & Modal Handling**
- Automatically dismisses cookie banners and consent modals
- Waits for main content to load
- Filters out overlay UI from extraction

### 5. **Performance Metrics**
Lightweight performance data per page:
- DOM content loaded time
- Load event time
- Total resources loaded

---

## Architecture

The crawler consists of two main components:

### 1. `crawler_ui.py` - Main Crawler
- **`UIFocusedCrawler`** class: Orchestrates BFS crawling and page extraction
- Handles URL normalization, domain filtering, depth control
- Manages Selenium WebDriver lifecycle
- Coordinates UI extraction

### 2. `ui_model_builder.py` - UI Extraction Engine
- **`UIModelBuilder`** class: Converts raw DOM into structured UI model
- Executes JavaScript in-browser for efficient extraction
- Handles label resolution, role normalization, deduplication
- Builds hierarchical UI representation

---

## Usage

### Method 1: Test Script (Recommended for Quick Testing)

Run the test script to crawl a website and get a JSON report:

```bash
cd server
python test_crawler_ui.py
```

**What it does:**
- Crawls `https://www.random.org/` (configurable in script)
- Extracts UI elements from each page
- Saves results to `crawl_ui_results_YYYYMMDD_HHMMSS.json`
- Prints summary and sample elements to console

**Configuration:**
Edit `test_crawler_ui.py` to change:
```python
START_URL = "https://www.random.org/"  # Change this
MAX_PAGES = 10                         # Max pages to crawl
MAX_DEPTH = 3                          # Max crawl depth
SAME_DOMAIN_ONLY = True                # Stay on same domain
HEADLESS = True                        # Run browser headless
WAIT_TIME = 3.0                        # Wait time between actions
```

### Method 2: Direct Python Usage

Use the crawler programmatically in your own scripts:

```python
from crawler_ui import UIFocusedCrawler

# Initialize crawler
crawler = UIFocusedCrawler(
    max_pages=10,
    max_depth=3,
    same_domain_only=True,
    headless=True,
    wait_time=3.0,
    page_load_timeout=30
)

# Start crawling
results = crawler.crawl("https://example.com")

# Access results
print(f"Pages crawled: {results['summary']['total_pages']}")
for page in results['pages']:
    print(f"Page: {page['page_url']}")
    print(f"  Elements: {len(page['elements'])}")
    print(f"  Forms: {len(page['forms'])}")
    print(f"  Navigation: {len(page['navigation'])}")

# Get JSON string
json_output = crawler.get_results_json()
```

### Method 3: REST API (FastAPI Service)

Start the API server:

```bash
cd server
python api.py
```

The server will start at `http://0.0.0.0:8000`

**API Endpoints:**

1. **Start a Crawl**
```bash
POST /api/v1/crawl
Content-Type: application/json

{
  "url": "https://example.com",
  "max_pages": 50,
  "max_depth": 5,
  "same_domain_only": true,
  "headless": true,
  "wait_time": 2.0
}
```

Response:
```json
{
  "crawl_id": "uuid-here",
  "status": "started",
  "message": "Crawl started successfully"
}
```

2. **Check Crawl Status**
```bash
GET /api/v1/crawl/{crawl_id}/status
```

3. **Get Crawl Results**
```bash
GET /api/v1/crawl/{crawl_id}/results
```

4. **API Documentation**
Visit `http://localhost:8000/docs` for interactive API documentation (Swagger UI)

---

## Output Format

The crawler returns a structured JSON object:

```json
{
  "crawl_info": {
    "start_url": "https://www.random.org/",
    "max_pages": 10,
    "max_depth": 3,
    "timestamp": "20260206_164117"
  },
  "pages": [
    {
      "page_url": "https://www.random.org/",
      "title": "RANDOM.ORG - True Random Number Service",
      "headings": [
        {
          "level": 1,
          "text": "True Random Number Service"
        }
      ],
      "forms": [
        {
          "id": "true-random-integer-generator",
          "action": "/integers/",
          "method": "get",
          "label": "True Random Integer Generator",
          "elements": [
            {
              "tag": "input",
              "role": "input",
              "type": "number",
              "name": "num",
              "id": "num",
              "label": "How many random integers?",
              "placeholder": null,
              "required": true
            }
          ]
        }
      ],
      "elements": [
        {
          "tag": "button",
          "role": "button",
          "id": "true-random-integer-generator-submit",
          "label": "Generate",
          "text": "Generate"
        }
      ],
      "navigation": [
        {
          "tag": "a",
          "role": "link",
          "href": "https://www.random.org/integers/",
          "text": "Integers",
          "label": "Integers"
        }
      ],
      "footer": [],
      "modals": []
    }
  ],
  "summary": {
    "total_pages": 1,
    "total_elements": 15,
    "pages_crawled": 1
  }
}
```

### Output Structure Explained

- **`crawl_info`**: Metadata about the crawl session
- **`pages`**: Array of page data, each containing:
  - **`page_url`**: Full URL of the page
  - **`title`**: Page title
  - **`headings`**: Page headings for context
  - **`forms`**: All forms with their input fields
  - **`elements`**: Main interactive elements (buttons, inputs, links)
  - **`navigation`**: Links in navigation/header sections
  - **`footer`**: Links in footer sections
  - **`modals`**: Elements in modal overlays (usually filtered out)
- **`summary`**: Aggregate statistics

---

## Configuration Options

### `UIFocusedCrawler` Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `max_pages` | int | 10 | Maximum number of pages to crawl |
| `max_depth` | int | 3 | Maximum crawl depth (BFS levels) |
| `same_domain_only` | bool | True | Only crawl pages from the same domain |
| `headless` | bool | True | Run browser in headless mode |
| `wait_time` | float | 2.0 | Wait time after page loads (seconds) |
| `page_load_timeout` | int | 30 | Page load timeout (seconds) |

### Performance Limits

The crawler includes built-in limits to prevent slowdowns:
- **Max links per page**: 100
- **Max buttons per page**: 100
- **Max inputs per page**: 100
- **Max form inputs per form**: 50

These limits ensure the crawler completes in reasonable time even on complex pages.

---

## Key Features

### ✅ What It Does Well

1. **Semantic Extraction**: Extracts meaningful UI structure, not just raw HTML
2. **Label Resolution**: Intelligently resolves human-readable labels for inputs
3. **Hierarchical Organization**: Separates navigation, footer, forms, and main content
4. **Cookie Banner Handling**: Automatically dismisses overlays
5. **BFS Crawling**: Systematic page discovery with depth control
6. **Performance Optimized**: Limits element processing to prevent hangs

### ⚠️ Limitations

1. **No Form Filling**: Does not attempt to fill forms intelligently
2. **No Login Handling**: Does not solve authentication flows
3. **No Deep Interaction**: Does not perform complex state exploration
4. **No Destructive Actions**: Does not click dangerous buttons (logout, delete, etc.)
5. **Limited SPA Support**: Basic SPA detection via DOM hash, but not full state exploration

---

## Troubleshooting

### Crawler Gets Stuck

If the crawler hangs during extraction:
1. Check the logs - progress messages show which step it's on
2. Reduce `max_pages` or element limits
3. Increase `wait_time` for slow-loading pages
4. Check if the page has excessive elements (>1000)

### Empty Results

If extraction returns few or no elements:
1. Check if cookie banner is blocking content (should auto-dismiss)
2. Verify page loaded correctly (check page source length in logs)
3. Temporarily disable visibility filters (commented out in code)
4. Check browser console for JavaScript errors

### Timeout Errors

If pages timeout:
1. Increase `page_load_timeout` parameter
2. Check if the URL is accessible
3. Verify network connectivity
4. Some SPAs may need longer load times

---

## Examples

### Example 1: Crawl a Simple Website

```python
from crawler_ui import UIFocusedCrawler

crawler = UIFocusedCrawler(max_pages=5, max_depth=2)
results = crawler.crawl("https://example.com")

print(f"Crawled {results['summary']['total_pages']} pages")
```

### Example 2: Extract Forms Only

```python
from crawler_ui import UIFocusedCrawler

crawler = UIFocusedCrawler(max_pages=1)
results = crawler.crawl("https://example.com")

for page in results['pages']:
    for form in page['forms']:
        print(f"Form: {form.get('label', 'Unnamed')}")
        for field in form['elements']:
            print(f"  - {field['label']} ({field['type']})")
```

### Example 3: Find All Buttons

```python
from crawler_ui import UIFocusedCrawler

crawler = UIFocusedCrawler(max_pages=1)
results = crawler.crawl("https://example.com")

for page in results['pages']:
    buttons = [e for e in page['elements'] if e['role'] == 'button']
    print(f"Found {len(buttons)} buttons:")
    for btn in buttons:
        print(f"  - {btn.get('label', btn.get('text', 'Unlabeled'))}")
```

---

## Integration with LLM

The crawler output is designed to be consumed by LLMs for test case generation:

1. **Structured Input**: Clean JSON format, no raw DOM
2. **Semantic Roles**: Normalized roles (button, input, link) instead of HTML tags
3. **Resolved Labels**: Human-readable labels for better understanding
4. **Hierarchical Context**: Forms, navigation, and sections provide context
5. **No Noise**: Filters out console errors, network logs, and low-level diagnostics

Example LLM prompt structure:
```
Given this UI structure:
- Page: {page_url}
- Forms: {forms with fields and labels}
- Buttons: {buttons with labels}
- Navigation: {navigation links}

Generate test cases for:
1. Form validation
2. Button interactions
3. Navigation flows
```

---

## Future Enhancements

Potential improvements:
- [ ] Full SPA state exploration
- [ ] Intelligent form filling
- [ ] Login flow detection and handling
- [ ] Screenshot capture
- [ ] Accessibility audit integration
- [ ] Performance profiling (Lighthouse integration)
- [ ] Multi-browser support

---

## Support

For issues or questions:
1. Check the logs for detailed error messages
2. Review the code comments in `crawler_ui.py` and `ui_model_builder.py`
3. Test with a simple website first (e.g., `https://example.com`)
4. Verify Chrome/ChromeDriver is properly installed

---

## License

Part of the AI-Powered Exploratory Testing Service project.

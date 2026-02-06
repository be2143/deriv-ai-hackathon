# UI-Focused Crawler Refactoring

## Overview

Refactored the crawler from a **raw robustness/debugging tool** to a **structured UI modeling engine** optimized for LLM-driven test generation.

## Architectural Changes

### Before (crawler_v2.py)
- Focus: Robustness testing, error mining
- Output: Verbose console logs, interaction graphs, crash reports
- Emphasis: Third-party errors, network failures, interaction tracking

### After (crawler_ui.py + ui_model_builder.py)
- Focus: Semantic UI structure extraction
- Output: Clean UI context per page
- Emphasis: Element identification, role normalization, label resolution

## Key Components

### 1. `ui_model_builder.py` - UI Abstraction Layer

**Purpose:** Converts raw Selenium DOM access into structured UI representation.

**Key Features:**

#### Element Extraction
- Extracts all interactive elements (buttons, inputs, selects, links, etc.)
- Filters to only visible and enabled elements
- Deduplicates elements by (tag, id)

#### Identifier Extraction
Extracts multiple identifiers per element:
- `id` - HTML id attribute
- `name` - HTML name attribute
- `data_testid` - data-testid attribute
- `data_test` - data-test attribute
- `data_qa` - data-qa attribute
- `aria_label` - aria-label attribute

#### Role Normalization
Maps HTML elements to semantic roles:
- `button` → `button`
- `input[type=text]` → `input`
- `input[type=password]` → `input`
- `input[type=checkbox]` → `checkbox`
- `input[type=radio]` → `radio`
- `select` → `dropdown`
- `textarea` → `textarea`
- `a` → `link`
- `role` attribute → use directly
- `onclick` → `button` (fallback)

#### Label Resolution (CRITICAL)
For inputs, resolves human-readable labels using priority:
1. `<label for="input_id">` - Explicit label association
2. Parent `<label>` - Label wrapping the input
3. `aria-labelledby` - ARIA label reference
4. `aria-label` - Direct ARIA label
5. `placeholder` - Placeholder text (fallback)
6. `name` attribute - Name attribute
7. `id` attribute - ID attribute
8. `data-testid` - Test ID (last resort)

### 2. `crawler_ui.py` - UI-Focused Crawler

**Purpose:** BFS crawl engine focused on UI structure extraction.

**Key Features:**

#### Reduced Logging
- Only captures internal JS errors (same-origin)
- Filters out third-party script errors
- Filters out ad script failures
- Filters out external CORS errors
- No verbose console dumps

#### BFS Crawl
- Maintains depth limit
- Maintains page limit
- Same-domain restriction
- URL normalization
- Deduplication

#### Performance Metrics
Lightweight performance tracking:
- `dom_content_loaded_ms` - DOMContentLoaded timing
- `load_event_ms` - Load event timing
- `total_resources` - Resource count

#### Clean Output
Structured JSON per page:
```json
{
  "pages": [
    {
      "ui_context": {
        "page_url": "...",
        "title": "...",
        "elements": [
          {
            "id": "...",
            "name": "...",
            "data_testid": "...",
            "aria_label": "...",
            "label": "...",
            "role": "...",
            "type": "...",
            "visible": true,
            "enabled": true
          }
        ],
        "performance": {
          "dom_content_loaded_ms": 1234,
          "load_event_ms": 2345,
          "total_resources": 50
        }
      }
    }
  ],
  "summary": {
    "total_pages": 10,
    "total_elements": 150
  }
}
```

## Output Schema

### UI Element Schema
```json
{
  "id": "username-input",
  "name": "username",
  "data_testid": "login-username",
  "data_test": null,
  "data_qa": null,
  "aria_label": "Username",
  "label": "Username",  // Resolved label
  "role": "input",      // Normalized role
  "type": "text",
  "tag": "input",
  "visible": true,
  "enabled": true,
  "text": null,
  "placeholder": "Enter username",
  "value": null
}
```

### Page Schema
```json
{
  "ui_context": {
    "page_url": "https://example.com/login",
    "title": "Login Page",
    "elements": [...],
    "performance": {...}
  },
  "performance": {...}
}
```

## What Was Removed

### Removed Features
- ❌ Verbose console error logging
- ❌ Third-party script error tracking
- ❌ Ad script failure tracking
- ❌ Full browser log dumps
- ❌ Excessive network logs
- ❌ Interaction state graphs
- ❌ Click attempt tracking
- ❌ DOM mutation tracking
- ❌ Robustness metadata

### Kept Features
- ✅ BFS crawl with limits
- ✅ URL normalization
- ✅ Same-domain restriction
- ✅ Internal JS error capture (lightweight)
- ✅ Main document HTTP status
- ✅ Navigation failure detection

## Usage

### Basic Usage

```python
from crawler_ui import UIFocusedCrawler

crawler = UIFocusedCrawler(
    max_pages=50,
    max_depth=5,
    same_domain_only=True,
    headless=True
)

results = crawler.crawl("https://example.com")
json_output = crawler.get_results_json()
```

### Test Script

```bash
cd server
python test_crawler_ui.py
```

## Design Philosophy

**Think like:** We are building a DOM → Logical UI representation compiler.

**Not:** A chaotic browser debugger.

## Acceptance Criteria ✅

- ✅ Each page has clean `ui_context`
- ✅ Each element has normalized `role`
- ✅ Each input has resolved `label`
- ✅ No verbose console spam in output
- ✅ JSON is LLM-ready without additional parsing
- ✅ `UITestEngineInput` can be constructed directly
- ✅ Clear separation between crawling and UI modeling
- ✅ Unit-testable label resolution function

## File Structure

```
server/
├── ui_model_builder.py      # UI abstraction layer
├── crawler_ui.py            # UI-focused crawler
├── test_crawler_ui.py       # Test script
└── UI_CRAWLER_REFACTOR.md   # This document
```

## Migration Guide

### From crawler_v2.py

1. **Import change:**
   ```python
   # Old
   from crawler_v2 import DeterministicCrawlerV2
   
   # New
   from crawler_ui import UIFocusedCrawler
   ```

2. **Initialization:**
   ```python
   # Old
   crawler = DeterministicCrawlerV2(
       max_pages=50,
       max_depth=5,
       max_states=100,
       max_clicks_per_page=20
   )
   
   # New
   crawler = UIFocusedCrawler(
       max_pages=50,
       max_depth=5
   )
   ```

3. **Output structure:**
   - Old: Verbose with errors, states, interaction graphs
   - New: Clean UI context per page

## Next Steps

The crawler is now ready for:
1. **Layer 2 (AI Interpretation)** - Feed UI context to LLM
2. **Test Generation** - Generate tests from UI structure
3. **UITestEngineInput** - Direct construction from UI context

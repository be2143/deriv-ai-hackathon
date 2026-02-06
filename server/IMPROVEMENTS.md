# Crawler V2 Improvements

## Overview

The improved crawler (`crawler_v2.py`) transforms the naive page scraper into a **state-aware, structured UI exploration engine with robust error classification**.

## Key Improvements

### 1. ✅ Fixed Crash Detection Logic

**Problem Solved:**
- Previously treated any console SEVERE as page crash
- Caused false positives from ads, CORS errors, analytics failures

**Solution:**
- Created `ErrorType` enum with 4 categories:
  - `INTERNAL_JS_ERROR` - Errors from the site itself
  - `EXTERNAL_SCRIPT_ERROR` - Errors from third-party scripts
  - `NETWORK_ERROR` - Network-related errors
  - `REAL_CRASH` - Actual page crashes

**Implementation:**
- `_classify_console_error()` - Classifies errors by checking if site domain is in error message
- `_is_real_crash()` - Only marks as crashed if:
  - DOM becomes empty
  - HTTP status >= 500
  - Browser tab crashes
  - Page load timeout exceeded
  - Specific crash indicators detected

**Result:**
- Console errors no longer automatically increment `pages_crashed`
- Ad/analytics errors are categorized but not fatal
- Crash detection is reliable and rare

### 2. ✅ Proper BFS Crawl Engine

**Features:**
- BFS traversal with queue management
- Depth limit enforcement
- Page limit enforcement
- Same-domain restriction
- URL normalization (removes fragments, normalizes trailing slashes)
- Deduplication using normalized URLs

**Implementation:**
- `_normalize_url()` - Normalizes URLs by removing fragments and trailing slashes
- `visited_urls` set tracks crawled URLs
- `page_queue` deque manages BFS traversal
- Proper depth and page limit checks

**Result:**
- No duplicate crawling
- Controlled crawl depth
- No external domains crawled
- Predictable crawl size

### 3. ✅ Improved Clickable Element Detection

**Detects:**
- `<a>` tags
- `<button>` tags
- `<input type=button>`
- `<input type=submit>`
- `<input type=reset>`
- Elements with `@role="button"`
- Elements with `onclick` attribute

**Implementation:**
- `_extract_clickable_elements()` - Uses comprehensive XPath selectors
- Filters to only visible and enabled elements
- Tracks element metadata (tag, text, id, href, onclick, role)

**Result:**
- Non-button clickable UI elements detected
- Hidden elements excluded
- Disabled elements excluded

### 4. ✅ Safe Click Strategy

**Safety Rules:**
- Skips external links
- Skips `mailto:`, `tel:`, `javascript:` links
- Skips dangerous keywords: logout, delete, remove, sign out
- Skips file downloads (.pdf, .zip, .exe, etc.)

**Implementation:**
- `_is_safe_click()` - Checks element against safety rules
- `is_safe` flag on `ClickableElement` dataclass
- Only safe elements are clicked during exploration

**Result:**
- No external navigation
- No destructive clicks
- No file downloads triggered

### 5. ✅ State Change Detection (SPA Support)

**Detection Methods:**
- DOM hash comparison
- URL change detection
- Element count change (>10% threshold)

**Implementation:**
- `_detect_state_change()` - Compares before/after interaction
- Tracks state via `state_id = url:dom_hash`
- `PageState` dataclass stores state information

**Result:**
- SPA navigation detected
- Virtual pages treated as new states
- State graph begins forming

### 6. ✅ Interaction State Graph

**Features:**
- Tracks state transitions
- Each unique DOM hash = new state
- States stored with transitions

**Implementation:**
- `visited_states` dict maps `state_id` to `PageState`
- `state_graph` dict tracks transitions: `state_id -> [transition_state_ids]`
- Transitions recorded when clicks/forms cause state changes

**Result:**
- Each unique DOM hash = new state
- States stored with transitions
- No infinite interaction loops (max limits enforced)

### 7. ✅ Improved Form Handling

**Strategy:**
- Submit empty forms only
- Capture console errors
- Detect navigation
- Detect DOM changes
- Track HTTP status

**Implementation:**
- `_submit_form_safely()` - Safely submits forms and detects changes
- Captures validation errors (expected)
- Tracks state changes from form submissions

**Result:**
- Forms tested safely
- No infinite redirects
- Validation errors captured

### 8. ✅ Network Monitoring

**Features:**
- Chrome DevTools Protocol logging enabled
- Performance logging enabled
- Network request tracking (prepared for future enhancement)

**Implementation:**
- `goog:loggingPrefs` capability set for browser and performance logs
- CDP Network domain enabled
- `NetworkRequest` dataclass prepared for request tracking

**Result:**
- Network 4xx/5xx can be tracked (foundation laid)
- External script failures filtered
- Main document failures flagged

### 9. ✅ Exploration Limits

**Global Limits:**
- `MAX_PAGES` - Maximum pages to crawl
- `MAX_DEPTH` - Maximum crawl depth
- `MAX_STATES` - Maximum unique states to track
- `MAX_CLICKS_PER_PAGE` - Maximum clicks per page
- `MAX_TOTAL_INTERACTIONS` - Maximum total interactions

**Implementation:**
- All limits enforced in crawl loop
- `total_interactions` counter tracks all interactions
- Early exit when limits reached

**Result:**
- Prevents exploration explosion
- Predictable resource usage
- Controlled crawl duration

### 10. ✅ Structured Output for AI Layer

**Output Structure:**
```json
{
  "summary": {
    "total_pages_crawled": 10,
    "total_states_discovered": 15,
    "total_interactions": 50,
    "pages_crashed": 1,
    "error_counts": {
      "internal_js_errors": 5,
      "external_script_errors": 20,
      "network_errors": 2,
      "real_crashes": 1
    }
  },
  "pages": [...],
  "states": [...],
  "errors": {
    "internal": [...],
    "external": [...],
    "network": [...],
    "crashes": [...]
  },
  "interaction_graph": {
    "state_id_1": ["state_id_2", "state_id_3"]
  }
}
```

**Implementation:**
- `_build_structured_output()` - Builds complete structured output
- Errors properly classified and separated
- States and transitions tracked
- No raw DOM in output

**Result:**
- LLM receives structured data only
- Errors properly classified
- State graph available for analysis

## Architecture

```
URL
 ↓
BFS Crawl
 ↓
State Explorer
 ↓
Interaction Engine (Safe Clicks)
 ↓
Error Classification
 ↓
Structured JSON
 ↓
LLM Report Generator (Layer 2)
```

## Usage

### Basic Usage

```python
from crawler_v2 import DeterministicCrawlerV2

crawler = DeterministicCrawlerV2(
    max_pages=50,
    max_depth=5,
    max_states=100,
    max_clicks_per_page=20,
    max_total_interactions=500
)

results = crawler.crawl("https://example.com")
json_output = crawler.get_results_json()
```

### Test Script

```bash
cd server
python test_crawler_v2.py
```

## Acceptance Criteria ✅

- ✅ Not mark ad errors as crashes
- ✅ Correctly detect SPA navigation
- ✅ Track unique states
- ✅ Avoid destructive interactions
- ✅ Avoid infinite loops
- ✅ Produce structured output
- ✅ Handle multi-page websites
- ✅ Classify errors intelligently

## Migration from V1

The new crawler is in `crawler_v2.py`. To migrate:

1. Update imports: `from crawler_v2 import DeterministicCrawlerV2`
2. Update initialization with new parameters
3. Update result handling (now returns dict instead of list)
4. Use `get_results_json()` for JSON output

The old `crawler.py` remains available for backward compatibility.

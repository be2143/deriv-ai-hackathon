# Layer 1: Deterministic Crawl Layer API Service

This service implements Layer 1 of the AI-powered exploratory testing system - a deterministic crawler that extracts structured data from websites and tests interactions.

## Features

### Structured Data Extraction
- **Links**: Extract all links with href, text, visibility, and clickability
- **Forms**: Extract forms with action, method, and all input fields
- **Inputs**: Extract input fields with type, name, id, required status, placeholder, and pattern
- **Buttons**: Extract buttons and clickable elements (including role='button' and onclick handlers)
- **Dropdowns**: Extract select elements with options

### Interaction Testing
- **Form Submission**: Submit empty forms and detect state changes, errors, and crashes
- **Button Clicking**: Click every button once and detect navigation, DOM changes, and errors
- **Navigation Handling**: Automatically navigate back after URL changes

### Error Detection
- **Console Errors**: Capture browser console errors (SEVERE and WARNING level)
- **Network Failures**: Detect network failures and error indicators
- **Crash Detection**: Detect page crashes, timeouts, and error states

### State Management
- **URL Tracking**: Track visited URLs to avoid infinite loops
- **DOM Hash Comparison**: Track page states using DOM hashes for SPA support
- **Depth Limiting**: Control crawl depth to prevent excessive exploration
- **Domain Filtering**: Option to crawl only same-domain pages

## API Endpoints

### Start a Crawl
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
  "message": "Crawl started for https://example.com",
  "pages_crawled": 0
}
```

### Get Crawl Status
```bash
GET /api/v1/crawl/{crawl_id}/status
```

Response:
```json
{
  "crawl_id": "uuid-here",
  "status": "completed",
  "pages_crawled": 10,
  "total_pages": 10,
  "results_available": true
}
```

### Get Crawl Results
```bash
GET /api/v1/crawl/{crawl_id}/results?format=json
```

Response:
```json
{
  "crawl_id": "uuid-here",
  "pages_crawled": 10,
  "results": "[...JSON array of crawl results...]"
}
```

## Running the Service

### Local Development
```bash
cd server
python api.py
```

The service will start on `http://0.0.0.0:8000`

### Using uvicorn directly
```bash
uvicorn server.api:app --host 0.0.0.0 --port 8000 --reload
```

### Docker
```bash
docker build -t crawler-service .
docker run -p 8000:8000 crawler-service
```

## Usage Example

```python
from crawler import DeterministicCrawler

# Initialize crawler
crawler = DeterministicCrawler(
    max_pages=50,
    max_depth=5,
    same_domain_only=True,
    headless=True,
    wait_time=2.0
)

# Start crawl
results = crawler.crawl("https://example.com")

# Get results as JSON
json_results = crawler.get_results_json()
print(json_results)
```

## Configuration Options

- **max_pages**: Maximum number of pages to crawl (default: 50)
- **max_depth**: Maximum depth to crawl (default: 5)
- **same_domain_only**: Only crawl pages from the same domain (default: True)
- **headless**: Run browser in headless mode (default: True)
- **wait_time**: Wait time after interactions in seconds (default: 2.0)

## Output Format

Each crawl result includes:
- URL and HTTP status
- Crash status and reason (if crashed)
- Extracted links, forms, buttons, dropdowns
- Console errors
- Network failures
- Form submission results (state changes, errors detected)
- Button click results (navigation, DOM changes, errors)

## Notes

- The crawler handles dynamic web apps (SPA) by comparing DOM hashes
- Form submissions are done with empty data to test validation and error handling
- Buttons are clicked once each, with automatic navigation back if URL changes
- Console errors are captured from browser logs
- Network failures are detected through page indicators (full network interception requires CDP or Playwright)

## Next Steps

This is Layer 1 of the system. Future layers will:
- **Layer 2**: AI Interpretation Layer - Feed structured data to LLM for feature inference and test case generation
- **Layer 3**: Test Case Generation - Generate Selenium test cases programmatically based on Layer 2 output

# Quick Start Guide

## Installation

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Make sure Chrome/Chromium is installed on your system.

## Running the API Service

### Option 1: Direct execution
```bash
cd server
python api.py
```

### Option 2: Using uvicorn
```bash
uvicorn server.api:app --host 0.0.0.0 --port 8000 --reload
```

The API will be available at `http://localhost:8000`

## Testing the API

### 1. Start a crawl
```bash
curl -X POST "http://localhost:8000/api/v1/crawl" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com",
    "max_pages": 10,
    "max_depth": 3,
    "same_domain_only": true,
    "headless": true,
    "wait_time": 2.0
  }'
```

Response:
```json
{
  "crawl_id": "abc123...",
  "status": "started",
  "message": "Crawl started for https://example.com",
  "pages_crawled": 0
}
```

### 2. Check status
```bash
curl "http://localhost:8000/api/v1/crawl/{crawl_id}/status"
```

### 3. Get results
```bash
curl "http://localhost:8000/api/v1/crawl/{crawl_id}/results?format=json"
```

## Using the Crawler Directly (Python)

```python
from server.crawler import DeterministicCrawler

crawler = DeterministicCrawler(
    max_pages=10,
    max_depth=3,
    same_domain_only=True,
    headless=True
)

results = crawler.crawl("https://example.com")
json_output = crawler.get_results_json()
print(json_output)
```

Or run the example:
```bash
cd server
python example_usage.py
```

## API Documentation

Once the server is running, visit:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Configuration

Key parameters:
- `max_pages`: Maximum number of pages to crawl (default: 50)
- `max_depth`: Maximum crawl depth (default: 5)
- `same_domain_only`: Only crawl same domain (default: true)
- `headless`: Run browser headless (default: true)
- `wait_time`: Wait time after interactions in seconds (default: 2.0)

## Output Structure

Each page result includes:
- URL and HTTP status
- Extracted elements (links, forms, buttons, dropdowns)
- Console errors
- Network failures
- Form submission test results
- Button click test results
- Crash detection

## Troubleshooting

### ChromeDriver issues
If you see ChromeDriver errors, the `webdriver-manager` package should automatically download the correct driver. Make sure you have internet access.

### Timeout errors
Increase `wait_time` if pages are loading slowly or if you're testing slow SPAs.

### Memory issues
Reduce `max_pages` and `max_depth` if you encounter memory issues with large sites.

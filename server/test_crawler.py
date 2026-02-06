"""
Test script for the DeterministicCrawler.

This script initiates crawling and saves results to a JSON file.
"""

import json
import sys
from pathlib import Path
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from crawler import DeterministicCrawler


def main():
    """Test the crawler and save results to JSON."""
    
    # Configuration
    START_URL = "https://optical.toys/#/"
    MAX_PAGES = 10
    MAX_DEPTH = 3
    SAME_DOMAIN_ONLY = True
    HEADLESS = True
    WAIT_TIME = 3.0  # Increased wait time for SPAs
    
    # Output file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = f"crawl_results_{timestamp}.json"
    
    print("=" * 70)
    print("Deterministic Crawler Test")
    print("=" * 70)
    print(f"Starting URL: {START_URL}")
    print(f"Max pages: {MAX_PAGES}")
    print(f"Max depth: {MAX_DEPTH}")
    print(f"Same domain only: {SAME_DOMAIN_ONLY}")
    print(f"Headless mode: {HEADLESS}")
    print(f"Wait time: {WAIT_TIME}s")
    print("=" * 70)
    print()
    
    # Initialize crawler
    print("Initializing crawler...")
    crawler = DeterministicCrawler(
        max_pages=MAX_PAGES,
        max_depth=MAX_DEPTH,
        same_domain_only=SAME_DOMAIN_ONLY,
        headless=HEADLESS,
        wait_time=WAIT_TIME,
        page_load_timeout=90  # Longer timeout for SPAs
    )
    
    # Start crawling
    print(f"Starting crawl of {START_URL}...")
    print()
    
    try:
        results = crawler.crawl(START_URL)
        
        # Get results as JSON string
        json_results = crawler.get_results_json()
        
        # Parse JSON to add metadata
        results_data = json.loads(json_results)
        
        # Add crawl metadata
        crawl_metadata = {
            "crawl_info": {
                "start_url": START_URL,
                "max_pages": MAX_PAGES,
                "max_depth": MAX_DEPTH,
                "same_domain_only": SAME_DOMAIN_ONLY,
                "headless": HEADLESS,
                "wait_time": WAIT_TIME,
                "timestamp": timestamp,
                "total_pages_crawled": len(results)
            },
            "summary": {
                "total_links": sum(len(r.links) for r in results),
                "total_forms": sum(len(r.forms) for r in results),
                "total_buttons": sum(len(r.buttons) for r in results),
                "total_dropdowns": sum(len(r.dropdowns) for r in results),
                "total_console_errors": sum(len(r.console_errors) for r in results),
                "total_network_failures": sum(len(r.network_failures) for r in results),
                "pages_crashed": sum(1 for r in results if r.crashed),
                "total_form_submissions_tested": sum(len(r.form_submission_results) for r in results),
                "total_buttons_clicked": sum(len(r.button_click_results) for r in results)
            },
            "results": results_data
        }
        
        # Save to JSON file
        output_path = Path(__file__).parent / output_file
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(crawl_metadata, f, indent=2, ensure_ascii=False)
        
        # Print summary
        print()
        print("=" * 70)
        print("Crawl Summary")
        print("=" * 70)
        print(f"Total pages crawled: {len(results)}")
        print(f"Total links found: {crawl_metadata['summary']['total_links']}")
        print(f"Total forms found: {crawl_metadata['summary']['total_forms']}")
        print(f"Total buttons found: {crawl_metadata['summary']['total_buttons']}")
        print(f"Total dropdowns found: {crawl_metadata['summary']['total_dropdowns']}")
        print(f"Total console errors: {crawl_metadata['summary']['total_console_errors']}")
        print(f"Total network failures: {crawl_metadata['summary']['total_network_failures']}")
        print(f"Pages that crashed: {crawl_metadata['summary']['pages_crashed']}")
        print(f"Form submissions tested: {crawl_metadata['summary']['total_form_submissions_tested']}")
        print(f"Buttons clicked: {crawl_metadata['summary']['total_buttons_clicked']}")
        print("=" * 70)
        print()
        print(f"✅ Results saved to: {output_path}")
        print()
        
        # Print details for each page
        print("=" * 70)
        print("Page Details")
        print("=" * 70)
        for i, result in enumerate(results, 1):
            status = "❌ CRASHED" if result.crashed else "✅ OK"
            print(f"\n{i}. {result.url}")
            print(f"   Status: {status}")
            if result.crashed:
                print(f"   Crash reason: {result.crash_reason}")
            print(f"   Links: {len(result.links)} | Forms: {len(result.forms)} | "
                  f"Buttons: {len(result.buttons)} | Dropdowns: {len(result.dropdowns)}")
            if result.console_errors:
                print(f"   Console errors: {len(result.console_errors)}")
                for err in result.console_errors[:2]:  # Show first 2
                    print(f"     - [{err.level}] {err.message[:80]}")
        
        print()
        print("=" * 70)
        print("Test completed successfully!")
        print("=" * 70)
        
        return output_path
        
    except Exception as e:
        print()
        print("=" * 70)
        print("❌ Error during crawl")
        print("=" * 70)
        print(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

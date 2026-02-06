"""
Example usage of the DeterministicCrawler.

This script demonstrates how to use the crawler directly (without the API).
"""

import json
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from crawler import DeterministicCrawler


def main():
    """Example usage of the crawler."""
    
    # Initialize crawler with custom settings
    crawler = DeterministicCrawler(
        max_pages=10,  # Limit to 10 pages for demo
        max_depth=3,   # Maximum depth of 3
        same_domain_only=True,
        headless=True,
        wait_time=2.0
    )
    
    # Start crawling
    print("Starting crawl...")
    results = crawler.crawl("https://example.com")
    
    # Print summary
    print(f"\n{'='*60}")
    print(f"Crawl Summary")
    print(f"{'='*60}")
    print(f"Total pages crawled: {len(results)}")
    
    total_links = sum(len(r.links) for r in results)
    total_forms = sum(len(r.forms) for r in results)
    total_buttons = sum(len(r.buttons) for r in results)
    total_errors = sum(len(r.console_errors) for r in results)
    crashed_pages = sum(1 for r in results if r.crashed)
    
    print(f"Total links found: {total_links}")
    print(f"Total forms found: {total_forms}")
    print(f"Total buttons found: {total_buttons}")
    print(f"Total console errors: {total_errors}")
    print(f"Pages that crashed: {crashed_pages}")
    
    # Print details for each page
    print(f"\n{'='*60}")
    print(f"Page Details")
    print(f"{'='*60}")
    
    for i, result in enumerate(results, 1):
        print(f"\nPage {i}: {result.url}")
        print(f"  Status: {'CRASHED' if result.crashed else 'OK'}")
        if result.crashed:
            print(f"  Crash reason: {result.crash_reason}")
        print(f"  Links: {len(result.links)}")
        print(f"  Forms: {len(result.forms)}")
        print(f"  Buttons: {len(result.buttons)}")
        print(f"  Dropdowns: {len(result.dropdowns)}")
        print(f"  Console errors: {len(result.console_errors)}")
        print(f"  Network failures: {len(result.network_failures)}")
        print(f"  Form submissions tested: {len(result.form_submission_results)}")
        print(f"  Buttons clicked: {len(result.button_click_results)}")
        
        # Show console errors if any
        if result.console_errors:
            print(f"  Console errors:")
            for err in result.console_errors[:3]:  # Show first 3
                print(f"    - [{err.level}] {err.message[:100]}")
    
    # Save results to JSON file
    output_file = "crawl_results.json"
    with open(output_file, 'w') as f:
        f.write(crawler.get_results_json())
    
    print(f"\n{'='*60}")
    print(f"Results saved to: {output_file}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()

"""
Test script for the improved DeterministicCrawlerV2.

This script initiates crawling and saves results to a JSON file.
"""

import json
import sys
from pathlib import Path
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from crawler_v2 import DeterministicCrawlerV2


def main():
    """Test the improved crawler and save results to JSON."""
    
    # Configuration
    START_URL = "https://optical.toys/#/"
    MAX_PAGES = 10
    MAX_DEPTH = 3
    MAX_STATES = 50
    MAX_CLICKS_PER_PAGE = 15
    MAX_TOTAL_INTERACTIONS = 200
    SAME_DOMAIN_ONLY = True
    HEADLESS = True
    WAIT_TIME = 3.0
    
    # Output file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = f"crawl_results_v2_{timestamp}.json"
    
    print("=" * 70)
    print("Improved Deterministic Crawler V2 Test")
    print("=" * 70)
    print(f"Starting URL: {START_URL}")
    print(f"Max pages: {MAX_PAGES}")
    print(f"Max depth: {MAX_DEPTH}")
    print(f"Max states: {MAX_STATES}")
    print(f"Max clicks per page: {MAX_CLICKS_PER_PAGE}")
    print(f"Max total interactions: {MAX_TOTAL_INTERACTIONS}")
    print(f"Same domain only: {SAME_DOMAIN_ONLY}")
    print(f"Headless mode: {HEADLESS}")
    print(f"Wait time: {WAIT_TIME}s")
    print("=" * 70)
    print()
    
    # Initialize crawler
    print("Initializing crawler...")
    crawler = DeterministicCrawlerV2(
        max_pages=MAX_PAGES,
        max_depth=MAX_DEPTH,
        max_states=MAX_STATES,
        max_clicks_per_page=MAX_CLICKS_PER_PAGE,
        max_total_interactions=MAX_TOTAL_INTERACTIONS,
        same_domain_only=SAME_DOMAIN_ONLY,
        headless=HEADLESS,
        wait_time=WAIT_TIME,
        page_load_timeout=90
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
                "max_states": MAX_STATES,
                "max_clicks_per_page": MAX_CLICKS_PER_PAGE,
                "max_total_interactions": MAX_TOTAL_INTERACTIONS,
                "same_domain_only": SAME_DOMAIN_ONLY,
                "headless": HEADLESS,
                "wait_time": WAIT_TIME,
                "timestamp": timestamp
            },
            **results_data
        }
        
        # Save to JSON file
        output_path = Path(__file__).parent / output_file
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(crawl_metadata, f, indent=2, ensure_ascii=False)
        
        # Print summary
        summary = results_data.get("summary", {})
        print()
        print("=" * 70)
        print("Crawl Summary")
        print("=" * 70)
        print(f"Total pages crawled: {summary.get('total_pages_crawled', 0)}")
        print(f"Total states discovered: {summary.get('total_states_discovered', 0)}")
        print(f"Total interactions: {summary.get('total_interactions', 0)}")
        print(f"Pages that crashed: {summary.get('pages_crashed', 0)}")
        print(f"Total links found: {summary.get('total_links', 0)}")
        print(f"Total forms found: {summary.get('total_forms', 0)}")
        print(f"Total clickable elements: {summary.get('total_clickable_elements', 0)}")
        print()
        print("Error Classification:")
        error_counts = summary.get('error_counts', {})
        print(f"  Internal JS errors: {error_counts.get('internal_js_errors', 0)}")
        print(f"  External script errors: {error_counts.get('external_script_errors', 0)}")
        print(f"  Network errors: {error_counts.get('network_errors', 0)}")
        print(f"  Real crashes: {error_counts.get('real_crashes', 0)}")
        print("=" * 70)
        print()
        print(f"✅ Results saved to: {output_path}")
        print()
        
        # Print page details
        print("=" * 70)
        print("Page Details")
        print("=" * 70)
        pages = results_data.get("pages", [])
        for i, page in enumerate(pages[:10], 1):  # Show first 10
            status = "❌ CRASHED" if page.get("crashed") else "✅ OK"
            print(f"\n{i}. {page.get('url', 'N/A')}")
            print(f"   Status: {status}")
            if page.get("crashed"):
                print(f"   Crash reason: {page.get('crash_reason', 'N/A')}")
            print(f"   State ID: {page.get('state_id', 'N/A')[:50]}...")
            print(f"   Links: {page.get('links_count', 0)} | Forms: {page.get('forms_count', 0)} | "
                  f"Clickables: {page.get('clickable_elements_count', 0)}")
            
            errors = page.get("errors", {})
            if errors.get("internal"):
                print(f"   Internal errors: {len(errors['internal'])}")
            if errors.get("external"):
                print(f"   External errors: {len(errors['external'])}")
            if errors.get("crashes"):
                print(f"   Crashes: {len(errors['crashes'])}")
        
        # Print state graph info
        interaction_graph = results_data.get("interaction_graph", {})
        if interaction_graph:
            print()
            print("=" * 70)
            print("State Graph")
            print("=" * 70)
            print(f"Total states with transitions: {len(interaction_graph)}")
            for state_id, transitions in list(interaction_graph.items())[:5]:
                print(f"  {state_id[:50]}... -> {len(transitions)} transitions")
        
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

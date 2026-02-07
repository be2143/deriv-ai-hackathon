"""
Simple script to open a webpage and download the entire DOM using BeautifulSoup.

The script uses Selenium to load the page (including JavaScript-rendered content)
and BeautifulSoup to parse and extract the DOM.

Usage:
    python download_dom.py <url> [--output <filename>] [--headless] [--wait <seconds>] [--no-prettify]

Example:
    python download_dom.py https://example.com
    python download_dom.py https://example.com --output dom.html --wait 5
    python download_dom.py https://example.com --no-prettify  # Faster for large pages
"""

import argparse
import sys
import time
from pathlib import Path
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup


def download_dom(url: str, output_file: str = None, headless: bool = True, wait_time: float = 3.0, prettify: bool = True):
    """
    Open a webpage and save the entire DOM to a file using BeautifulSoup.
    
    Args:
        url: The URL to open
        output_file: Output filename (default: dom_<timestamp>.html)
        headless: Run browser in headless mode
        wait_time: Seconds to wait after page load
        prettify: Format HTML with BeautifulSoup prettify (default: True, can be slow for large pages)
    """
    print(f"Opening page: {url}")
    
    # Setup Chrome options
    chrome_options = Options()
    if headless:
        chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    
    # Initialize driver
    print("Initializing Chrome driver...")
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    
    try:
        # Set page load timeout
        driver.set_page_load_timeout(60)
        
        # Navigate to page
        print(f"Loading page...")
        driver.get(url)
        
        # Wait for document ready state
        print("Waiting for document ready state...")
        WebDriverWait(driver, 30).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
        
        # Wait for JavaScript to finish executing
        print("Waiting for JavaScript to finish...")
        try:
            # Wait for jQuery to finish (if present)
            WebDriverWait(driver, 10).until(
                lambda d: d.execute_script("return typeof jQuery === 'undefined' || jQuery.active === 0")
            )
        except TimeoutException:
            print("  (jQuery check skipped or timed out)")
        
        # Wait for network requests to settle
        print("Waiting for network activity to settle...")
        network_idle_time = 2.0  # seconds of no network activity
        try:
            last_request_count = driver.execute_script("return window.performance.getEntriesByType('resource').length")
            stable_count = 0
            
            for i in range(30):  # Check for up to 6 seconds (30 * 0.2)
                time.sleep(0.2)
                current_count = driver.execute_script("return window.performance.getEntriesByType('resource').length")
                if current_count == last_request_count:
                    stable_count += 1
                    if stable_count >= (network_idle_time / 0.2):  # Stable for network_idle_time
                        print(f"  Network idle after {i * 0.2:.1f}s")
                        break
                else:
                    stable_count = 0
                    last_request_count = current_count
                    if i % 5 == 0:  # Print every second
                        print(f"  Network requests: {current_count} (waiting for stability...)")
        except Exception as e:
            print(f"  (Network monitoring unavailable: {e})")
        
        # Additional wait for dynamic content
        print(f"Waiting additional {wait_time}s for dynamic content...")
        time.sleep(wait_time)
        
        # Wait for any pending animations or transitions
        print("Waiting for animations/transitions to complete...")
        time.sleep(0.5)  # Brief wait for animations
        
        # Scroll to bottom to trigger lazy-loaded content
        print("Scrolling to trigger lazy-loaded content...")
        last_height = driver.execute_script("return document.body.scrollHeight")
        scroll_pause_time = 0.5
        
        while True:
            # Scroll down to bottom
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(scroll_pause_time)
            
            # Calculate new scroll height and compare with last scroll height
            new_height = driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                break
            last_height = new_height
        
        # Scroll back to top
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(0.5)
        
        # Final wait for any content loaded by scrolling
        time.sleep(1.0)
        
        # Get page title
        title = driver.title
        print(f"Page title: {title}")
        
        # Get the raw page source
        print("Extracting DOM with BeautifulSoup...")
        raw_html = driver.page_source
        
        # Verify DOM was loaded properly
        if len(raw_html) < 100:
            print("⚠️  WARNING: DOM seems too small, page may not have loaded properly")
        
        # Parse HTML with BeautifulSoup
        print("Parsing HTML with BeautifulSoup...")
        soup = BeautifulSoup(raw_html, 'html.parser')
        
        # Count elements for verification
        element_count = len(soup.find_all())
        print(f"  Found {element_count:,} DOM elements")
        
        # Get some stats about the parsed HTML
        tags = soup.find_all()
        unique_tags = set(tag.name for tag in tags)
        print(f"  Found {len(unique_tags)} unique tag types: {', '.join(sorted(list(unique_tags))[:10])}{'...' if len(unique_tags) > 10 else ''}")
        
        # Prettify the HTML (formatted, readable) or use string representation
        if prettify:
            print("Formatting HTML (this may take a moment for large pages)...")
            dom_content = soup.prettify()
        else:
            print("Converting to string (no formatting)...")
            dom_content = str(soup)
        
        # Generate output filename if not provided
        if output_file is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            # Create safe filename from URL
            safe_url = url.replace("https://", "").replace("http://", "").replace("/", "_").replace("?", "_").replace("#", "_")[:50]
            output_file = f"dom_{safe_url}_{timestamp}.html"
        
        # Ensure output directory exists
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Save DOM to file
        print(f"Saving DOM to: {output_path}")
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(dom_content)
        
        # Print stats
        dom_size = len(dom_content)
        print(f"\n✅ DOM downloaded successfully!")
        print(f"   File: {output_path.absolute()}")
        print(f"   Size: {dom_size:,} bytes ({dom_size / 1024:.2f} KB)")
        print(f"   Lines: {dom_content.count(chr(10)):,}")
        print(f"   Elements: {element_count:,}")
        
        return str(output_path.absolute())
        
    except Exception as e:
        print(f"\n❌ Error downloading DOM: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
        
    finally:
        driver.quit()
        print("\nBrowser closed.")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Download the entire DOM from a webpage",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python download_dom.py https://example.com
  python download_dom.py https://example.com --output my_page.html
  python download_dom.py https://example.com --no-headless --wait 5
  python download_dom.py https://example.com --no-prettify  # Faster for large pages
        """
    )
    
    parser.add_argument(
        "url",
        help="URL of the webpage to download"
    )
    
    parser.add_argument(
        "--output", "-o",
        help="Output filename (default: dom_<url>_<timestamp>.html)"
    )
    
    parser.add_argument(
        "--no-headless",
        action="store_true",
        help="Run browser in visible mode (default: headless)"
    )
    
    parser.add_argument(
        "--wait", "-w",
        type=float,
        default=3.0,
        help="Seconds to wait after page load (default: 3.0)"
    )
    
    parser.add_argument(
        "--no-prettify",
        action="store_true",
        help="Skip HTML prettification (faster for large pages, but less readable)"
    )
    
    args = parser.parse_args()
    
    download_dom(
        url=args.url,
        output_file=args.output,
        headless=not args.no_headless,
        wait_time=args.wait,
        prettify=not args.no_prettify
    )


if __name__ == "__main__":
    main()

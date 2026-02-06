"""
Test script for UI-focused crawler.

Tests structured UI modeling engine optimized for LLM consumption.
"""

import json
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

from crawler_ui import UIFocusedCrawler


def main():
    # Configuration
    START_URL = "https://www.random.org/"
    MAX_PAGES = 10
    MAX_DEPTH = 3
    SAME_DOMAIN_ONLY = True
    HEADLESS = True
    WAIT_TIME = 3.0

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = Path(__file__).parent / f"crawl_ui_results_{timestamp}.json"

    print("=" * 70)
    print("UI-Focused Crawler Test")
    print("=" * 70)
    print(f"URL:        {START_URL}")
    print(f"Max pages:  {MAX_PAGES}")
    print(f"Max depth:  {MAX_DEPTH}")
    print(f"Headless:   {HEADLESS}")
    print(f"Wait time:  {WAIT_TIME}s")
    print("=" * 70)
    print()

    crawler = UIFocusedCrawler(
        max_pages=MAX_PAGES,
        max_depth=MAX_DEPTH,
        same_domain_only=SAME_DOMAIN_ONLY,
        headless=HEADLESS,
        wait_time=WAIT_TIME,
        page_load_timeout=90,
    )

    try:
        results = crawler.crawl(START_URL)

        # Add crawl metadata
        output = {
            "crawl_info": {
                "start_url": START_URL,
                "max_pages": MAX_PAGES,
                "max_depth": MAX_DEPTH,
                "timestamp": timestamp,
            },
            **results,
        }

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)

        # ---- summary ----
        summary = results.get("summary", {})
        print()
        print("=" * 70)
        print("Crawl Summary")
        print("=" * 70)
        print(f"Pages crawled:     {summary.get('total_pages', 0)}")
        print(f"Total elements:    {summary.get('total_elements', 0)}")
        print()

        # ---- per-page details ----
        for i, page in enumerate(results.get("pages", [])[:5], 1):
            url = page.get("page_url", "N/A")
            title = page.get("title", "")
            elements = page.get("elements", [])
            forms = page.get("forms", [])
            nav = page.get("navigation", [])
            foot = page.get("footer", [])
            modals = page.get("modals", [])
            headings = page.get("headings", [])

            print(f"{i}. {url}")
            print(f"   Title: {title}")
            print(f"   Headings: {[h.get('text','') for h in headings[:5]]}")
            print(f"   Elements: {len(elements)}  |  Forms: {len(forms)}  |  "
                  f"Nav: {len(nav)}  |  Footer: {len(foot)}  |  Modals: {len(modals)}")

            # role breakdown
            roles = {}
            for e in elements:
                r = e.get("role", "?")
                roles[r] = roles.get(r, 0) + 1
            if roles:
                print(f"   Roles: {dict(roles)}")

            # show a few elements with their labels
            print(f"   Sample elements:")
            for e in elements[:5]:
                label = e.get("label") or e.get("text") or e.get("placeholder") or e.get("name") or "—"
                role = e.get("role", "?")
                print(f"     [{role}] {label[:60]}")

            if forms:
                print(f"   Forms:")
                for fi, form in enumerate(forms):
                    fl = form.get("label") or form.get("action") or f"form #{fi}"
                    print(f"     Form: {fl}  ({len(form.get('elements', []))} fields)")
                    for fe in form.get("elements", [])[:4]:
                        fl2 = fe.get("label") or fe.get("placeholder") or fe.get("name") or "—"
                        print(f"       [{fe.get('role','?')}] {fl2[:50]}")
            print()

        print("=" * 70)
        print(f"Results saved to: {output_file}")
        print("=" * 70)

    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

"""
Quick test to verify JavaScript extraction works.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from ui_model_builder import UIModelBuilder

def test_extraction():
    print("Initializing Chrome driver...")
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    
    try:
        print("Loading page: https://www.random.org/")
        driver.get("https://www.random.org/")
        driver.implicitly_wait(5)
        
        print("Testing basic JS execution...")
        title = driver.execute_script("return document.title;")
        print(f"Page title: {title}")
        
        # Test simple selector
        count = driver.execute_script(
            "return document.querySelectorAll('button, input, select, textarea, a[href]').length;"
        )
        print(f"Found {count} interactive elements with simple selector")
        
        print("\nRunning full UI extraction...")
        builder = UIModelBuilder(driver)
        ui = builder.build_ui_context("https://www.random.org/")
        
        print(f"\nExtraction result:")
        print(f"  Type: {type(ui)}")
        print(f"  Keys: {list(ui.keys()) if isinstance(ui, dict) else 'N/A'}")
        print(f"  Elements: {len(ui.get('elements', []))}")
        print(f"  Forms: {len(ui.get('forms', []))}")
        print(f"  Navigation: {len(ui.get('navigation', []))}")
        print(f"  Footer: {len(ui.get('footer', []))}")
        print(f"  Modals: {len(ui.get('modals', []))}")
        
        if len(ui.get('elements', [])) == 0:
            print("\n⚠️  WARNING: No elements extracted!")
            print("Checking browser console logs...")
            try:
                logs = driver.get_log('browser')
                for log in logs[-10:]:
                    print(f"  [{log['level']}] {log['message']}")
            except Exception as e:
                print(f"  Could not get logs: {e}")
        
    finally:
        driver.quit()
        print("\nDone.")

if __name__ == "__main__":
    test_extraction()

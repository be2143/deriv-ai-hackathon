import io
from typing import Dict, Any

from PIL import Image
import imagehash
from selenium.webdriver.common.by import By


class AdvancedQAFunctions:
    """Additional advanced QA features (accessibility, performance, visual diffs)."""

    @staticmethod
    def check_accessibility(driver) -> Dict[str, Any]:
        """
        Run very basic accessibility checks.

        Returns:
            dict with counts of images without alt, elements with ARIA roles, etc.
        """
        images = driver.find_elements(By.TAG_NAME, "img")
        missing_alt = [img for img in images if not img.get_attribute("alt")]

        interactive = driver.find_elements(By.XPATH, "//*[@role]")

        return {
            "images_without_alt": len(missing_alt),
            "aria_roles_present": len(interactive),
            # Placeholder; a real implementation would integrate with axe-core or similar.
            "contrast_issues": 0,
        }

    @staticmethod
    def check_performance(driver, url: str) -> Dict[str, Any]:
        """
        Check basic performance metrics using Navigation Timing API.

        Returns:
            dict with page load and DOM content loaded times in seconds.
        """
        timing = driver.execute_script("return window.performance.timing;")

        navigation_start = timing.get("navigationStart", 0)
        load_event_end = timing.get("loadEventEnd", 0)
        dom_content_loaded_end = timing.get("domContentLoadedEventEnd", 0)

        def seconds(end: int) -> float:
            if not navigation_start or not end or end < navigation_start:
                return 0.0
            return (end - navigation_start) / 1000.0

        return {
            "page_load_time": seconds(load_event_end),
            "dom_content_loaded": seconds(dom_content_loaded_end),
        }

    @staticmethod
    def compare_with_baseline(driver, baseline_screenshot_path: str) -> Dict[str, Any]:
        """
        Compare current page screenshot with a baseline screenshot using perceptual hashing.

        Args:
            driver: Selenium WebDriver instance.
            baseline_screenshot_path: Path to baseline PNG/JPEG screenshot.

        Returns:
            dict with 'visual_difference' (int) and 'changed' (bool) fields.
        """
        current_png = driver.get_screenshot_as_png()
        current_img = Image.open(io.BytesIO(current_png))
        baseline_img = Image.open(baseline_screenshot_path)

        hash_current = imagehash.phash(current_img)
        hash_baseline = imagehash.phash(baseline_img)
        difference = hash_current - hash_baseline

        return {
            "visual_difference": int(difference),
            "changed": difference > 5,  # Threshold; tune as needed.
        }


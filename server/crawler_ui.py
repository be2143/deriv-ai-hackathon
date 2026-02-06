"""
UI-Focused Crawler - Simple, Reliable Version

BFS crawl with straightforward Selenium element extraction.
"""

import json
import logging
import time
from collections import deque
from typing import Dict, List, Set
from urllib.parse import urljoin, urlparse, urlunparse

from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(name)s:%(message)s')


class UIFocusedCrawler:
    """
    Simple crawler that extracts UI elements using basic Selenium methods.
    """

    def __init__(
        self,
        max_pages: int = 10,
        max_depth: int = 3,
        same_domain_only: bool = True,
        headless: bool = True,
        wait_time: float = 2.0,
        page_load_timeout: int = 30,
    ):
        self.max_pages = max_pages
        self.max_depth = max_depth
        self.same_domain_only = same_domain_only
        self.headless = headless
        self.wait_time = wait_time
        self.page_load_timeout = page_load_timeout

        self.driver: webdriver.Chrome = None
        self.base_url: str = None
        self.base_domain: str = None
        self.visited_urls: Set[str] = set()
        self.page_queue: deque = deque()
        self.page_results: List[Dict] = []

    def _init_driver(self):
        """Initialize Chrome driver."""
        chrome_options = Options()
        if self.headless:
            chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-logging"])

        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=chrome_options)
        self.driver.set_page_load_timeout(self.page_load_timeout)
        self.driver.implicitly_wait(5)

    def _extract_domain(self, url: str) -> str:
        """Extract domain from URL."""
        try:
            parsed = urlparse(url)
            return f"{parsed.scheme}://{parsed.netloc}"
        except Exception:
            return ""

    def _normalize_url(self, url: str, base: str = None) -> str:
        """Normalize URL."""
        if not url:
            return ""
        if url.startswith("javascript:") or url.startswith("mailto:") or url.startswith("#"):
            return ""
        if base:
            url = urljoin(base, url)
        parsed = urlparse(url)
        # Remove fragment
        normalized = urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, parsed.query, ""))
        return normalized.rstrip("/") or normalized

    def _is_same_domain(self, url: str) -> bool:
        """Check if URL is same domain."""
        if not self.same_domain_only:
            return True
        try:
            url_domain = self._extract_domain(url)
            return url_domain == self.base_domain
        except Exception:
            return False

    def _wait_ready(self, timeout: int = 10):
        """Wait for page to be ready."""
        try:
            # Wait for body to be present
            WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            # Wait for ready state
            WebDriverWait(self.driver, timeout).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
            time.sleep(2.0)  # Extra wait for JS hydration
            logger.debug(f"Page ready: {self.driver.current_url}")
        except TimeoutException:
            logger.warning("Page load timeout, continuing anyway")
            time.sleep(2.0)
        except Exception as e:
            logger.debug(f"Wait ready error: {e}")
            time.sleep(2.0)

    def _dismiss_modals(self):
        """Try to dismiss cookie banners and modals."""
        try:
            # Common cookie/consent button selectors
            selectors = [
                "//button[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'accept')]",
                "//button[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'allow')]",
                "//button[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'agree')]",
                "//button[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'ok')]",
                "//button[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'dismiss')]",
                "//button[@id='cookie-accept']",
                "//button[@id='accept-cookies']",
                "//button[@class*='cookie']",
                "//button[@class*='consent']",
            ]
            
            dismissed = 0
            for selector in selectors:
                try:
                    buttons = self.driver.find_elements(By.XPATH, selector)
                    for btn in buttons[:3]:  # Try first 3 matches
                        try:
                            if btn.is_displayed():
                                btn.click()
                                dismissed += 1
                                logger.debug("Dismissed modal/cookie banner")
                                time.sleep(1.0)
                                break
                        except Exception:
                            continue
                    if dismissed > 0:
                        break
                except Exception:
                    continue
            
            if dismissed > 0:
                time.sleep(1.5)  # Wait for modal to disappear
        except Exception as e:
            logger.debug(f"Error dismissing modals: {e}")

    def _extract_elements(self) -> Dict:
        """Extract UI elements from current page using simple Selenium methods."""
        try:
            # Wait for page to be ready
            self._wait_ready()
            
            # Dismiss modals/cookie banners
            self._dismiss_modals()

            # Get basic page info
            title = self.driver.title
            current_url = self.driver.current_url
            page_source_len = len(self.driver.page_source)
            
            logger.info(f"[EXTRACT] Page: {current_url}")
            logger.info(f"[EXTRACT] Title: {title}")
            logger.info(f"[EXTRACT] Page source length: {page_source_len} chars")

            # Extract headings (no visibility filter for debugging)
            headings = []
            for tag in ["h1", "h2", "h3", "h4", "h5"]:
                try:
                    found = self.driver.find_elements(By.TAG_NAME, tag)
                    logger.debug(f"[EXTRACT] Found {len(found)} {tag} elements")
                    for heading in found:
                        try:
                            text = heading.text.strip()
                            if text:
                                headings.append({"level": int(tag[1]), "text": text})
                        except Exception:
                            continue
                except Exception as e:
                    logger.debug(f"Error extracting {tag}: {e}")
                    continue
            
            logger.info(f"[EXTRACT] Extracted {len(headings)} headings")

            # Extract forms (relaxed visibility check)
            forms = []
            try:
                all_forms = self.driver.find_elements(By.TAG_NAME, "form")
                logger.debug(f"[EXTRACT] Found {len(all_forms)} form elements")
            except Exception as e:
                logger.debug(f"Error finding forms: {e}")
                all_forms = []
                
            for form_el in all_forms:
                try:
                    # Temporarily disable visibility check for debugging
                    # if not form_el.is_displayed():
                    #     continue

                    form_data = {
                        "action": form_el.get_attribute("action") or "",
                        "method": (form_el.get_attribute("method") or "get").lower(),
                        "elements": [],
                    }
                    if form_el.get_attribute("id"):
                        form_data["id"] = form_el.get_attribute("id")

                            # Get form label/heading (simplified)
                    try:
                        # Try simpler selectors first
                        for tag in ["legend", "h1", "h2", "h3"]:
                            try:
                                label_el = form_el.find_element(By.TAG_NAME, tag)
                                if label_el:
                                    form_data["label"] = label_el.text.strip()
                                    break
                            except Exception:
                                continue
                    except Exception:
                        pass

                    # Extract form inputs (relaxed checks, limit to prevent slowdown)
                    try:
                        form_inputs = form_el.find_elements(By.XPATH, ".//input | .//select | .//textarea | .//button")
                        logger.debug(f"[EXTRACT] Form has {len(form_inputs)} input elements")
                    except Exception as e:
                        logger.debug(f"Error finding form inputs: {e}")
                        form_inputs = []
                    
                    # Limit form inputs to prevent slowdown
                    max_form_inputs = 50
                    for i, input_el in enumerate(form_inputs[:max_form_inputs]):
                        try:
                            # Temporarily disable visibility/enabled checks
                            # if not input_el.is_displayed() or not input_el.is_enabled():
                            #     continue

                            input_data = self._extract_input_data(input_el)
                            if input_data:
                                form_data["elements"].append(input_data)
                        except Exception as e:
                            logger.debug(f"Error extracting form input {i}: {e}")
                            continue

                    if form_data["elements"]:
                        forms.append(form_data)
                except Exception as e:
                    logger.debug(f"Error processing form: {e}")
                    continue
            
            logger.info(f"[EXTRACT] Extracted {len(forms)} forms")
            logger.info(f"[EXTRACT] Starting link extraction...")

            # Extract links (navigation and footer) - limit to prevent slowdown
            navigation = []
            footer = []
            main_links = []
            
            try:
                all_links = self.driver.find_elements(By.TAG_NAME, "a")
                logger.debug(f"[EXTRACT] Found {len(all_links)} link elements")
            except Exception as e:
                logger.debug(f"Error finding links: {e}")
                all_links = []
            
            max_links_to_check = 100  # Limit links checked per page
            logger.info(f"[EXTRACT] Processing {min(len(all_links), max_links_to_check)} of {len(all_links)} links")

            for i, link in enumerate(all_links[:max_links_to_check]):
                
                try:
                    # Temporarily disable visibility check
                    # if not link.is_displayed():
                    #     continue

                    href = link.get_attribute("href")
                    if not href or href.startswith("javascript:") or href.startswith("mailto:") or href.startswith("#"):
                        continue

                    text = link.text.strip()
                    link_data = {
                        "tag": "a",
                        "role": "link",
                        "href": href,
                        "text": text or None,
                        "label": text or None,
                    }
                    if link.get_attribute("id"):
                        link_data["id"] = link.get_attribute("id")
                    if link.get_attribute("name"):
                        link_data["name"] = link.get_attribute("name")

                    # Categorize links (simplified - check parent elements directly)
                    # Skip expensive ancestor queries for now
                    parent_tag = None
                    try:
                        parent = link.find_element(By.XPATH, "./..")
                        parent_tag = parent.tag_name.lower() if parent else None
                    except Exception:
                        pass
                    
                    # Simple categorization based on parent tag
                    if parent_tag in ['nav', 'header']:
                        navigation.append(link_data)
                        continue
                    elif parent_tag == 'footer':
                        footer.append(link_data)
                        continue
                    
                    # Check parent's role attribute
                    try:
                        parent = link.find_element(By.XPATH, "./..")
                        parent_role = parent.get_attribute("role")
                        if parent_role in ['navigation']:
                            navigation.append(link_data)
                            continue
                        elif parent_role == 'contentinfo':
                            footer.append(link_data)
                            continue
                    except Exception:
                        pass

                    main_links.append(link_data)
                except Exception as e:
                    logger.debug(f"Error processing link {i}: {e}")
                    continue
                
                # Progress logging every 20 links
                if (i + 1) % 20 == 0:
                    logger.debug(f"[EXTRACT] Processed {i + 1}/{min(len(all_links), max_links_to_check)} links")
            
            logger.info(f"[EXTRACT] Extracted {len(navigation)} nav links, {len(footer)} footer links, {len(main_links)} main links")
            logger.info(f"[EXTRACT] Starting button extraction...")

            # Extract buttons
            buttons = []
            try:
                all_buttons = self.driver.find_elements(By.XPATH, "//button | //input[@type='button'] | //input[@type='submit'] | //*[@role='button']")
                logger.debug(f"[EXTRACT] Found {len(all_buttons)} button elements")
            except Exception as e:
                logger.debug(f"Error finding buttons: {e}")
                all_buttons = []
            
            # Limit buttons to prevent slowdown
            max_buttons = 100
            logger.info(f"[EXTRACT] Processing {min(len(all_buttons), max_buttons)} of {len(all_buttons)} buttons")
                
            for i, button in enumerate(all_buttons[:max_buttons]):
                try:
                    # Temporarily disable visibility/enabled checks
                    # if not button.is_displayed() or not button.is_enabled():
                    #     continue

                    button_data = {
                        "tag": button.tag_name.lower(),
                        "role": "button",
                        "text": button.text.strip() or None,
                        "label": button.text.strip() or None,
                    }
                    if button.get_attribute("id"):
                        button_data["id"] = button.get_attribute("id")
                    if button.get_attribute("name"):
                        button_data["name"] = button.get_attribute("name")
                    if button.get_attribute("type"):
                        button_data["type"] = button.get_attribute("type")
                    if button.get_attribute("onclick"):
                        button_data["onclick"] = True

                    # Try to get label from associated label element (simplified, skip if slow)
                    try:
                        button_id = button.get_attribute("id")
                        if button_id:
                            # Use simpler selector, limit search
                            try:
                                label_el = self.driver.find_element(By.CSS_SELECTOR, f"label[for='{button_id}']")
                                if label_el:
                                    button_data["label"] = label_el.text.strip()
                            except Exception:
                                pass
                    except Exception:
                        pass

                    buttons.append(button_data)
                except Exception as e:
                    logger.debug(f"Error processing button {i}: {e}")
                    continue
            
            logger.info(f"[EXTRACT] Extracted {len(buttons)} buttons")
            logger.info(f"[EXTRACT] Starting standalone input extraction...")

            # Extract other inputs (not in forms)
            inputs = []
            try:
                all_inputs = self.driver.find_elements(By.TAG_NAME, "input")
                logger.debug(f"[EXTRACT] Found {len(all_inputs)} input elements")
            except Exception as e:
                logger.debug(f"Error finding inputs: {e}")
                all_inputs = []
            
            # Limit inputs to prevent slowdown
            max_inputs = 100
            logger.info(f"[EXTRACT] Processing {min(len(all_inputs), max_inputs)} of {len(all_inputs)} standalone inputs")
                
            for i, input_el in enumerate(all_inputs[:max_inputs]):
                try:
                    # Skip if already in a form (simplified check)
                    try:
                        parent = input_el.find_element(By.XPATH, "./..")
                        if parent.tag_name.lower() == 'form':
                            continue  # Already processed in forms
                    except Exception:
                        pass  # Not in a form, process it

                    # Temporarily disable visibility/enabled checks
                    # if not input_el.is_displayed() or not input_el.is_enabled():
                    #     continue

                    input_type = input_el.get_attribute("type") or "text"
                    if input_type in ["hidden", "submit", "button"]:
                        continue

                    input_data = self._extract_input_data(input_el)
                    if input_data:
                        inputs.append(input_data)
                except Exception as e:
                    logger.debug(f"Error processing input: {e}")
                    continue
            
            logger.info(f"[EXTRACT] Extracted {len(inputs)} standalone inputs")

            # Combine main elements
            elements = buttons + inputs + main_links
            
            total_elements = len(elements) + len(forms) + len(navigation) + len(footer)
            logger.info(f"[EXTRACT] TOTAL: {total_elements} elements ({len(elements)} main, {len(forms)} forms, {len(navigation)} nav, {len(footer)} footer)")

            return {
                "page_url": current_url,
                "title": title,
                "headings": headings,
                "forms": forms,
                "elements": elements,
                "navigation": navigation,
                "footer": footer,
            }

        except Exception as e:
            logger.error(f"Error extracting elements: {e}", exc_info=True)
            return {
                "page_url": self.driver.current_url if self.driver else "",
                "title": self.driver.title if self.driver else "",
                "headings": [],
                "forms": [],
                "elements": [],
                "navigation": [],
                "footer": [],
            }

    def _extract_input_data(self, input_el) -> Dict:
        """Extract data from an input element."""
        try:
            tag = input_el.tag_name.lower()
            input_type = input_el.get_attribute("type") or "text"
            name = input_el.get_attribute("name") or ""
            input_id = input_el.get_attribute("id") or ""

            input_data = {
                "tag": tag,
                "role": "input" if tag == "input" else tag,
                "type": input_type.lower(),
            }

            if input_id:
                input_data["id"] = input_id
            if name:
                input_data["name"] = name

            # Get label (simplified to avoid slow XPath)
            label_text = None
            if input_id:
                try:
                    # Use CSS selector instead of XPath for speed
                    label_el = self.driver.find_element(By.CSS_SELECTOR, f"label[for='{input_id}']")
                    label_text = label_el.text.strip()
                except Exception:
                    pass

            if not label_text:
                # Check parent label (simplified)
                try:
                    parent = input_el.find_element(By.XPATH, "./..")
                    if parent.tag_name.lower() == 'label':
                        label_text = parent.text.strip()
                except Exception:
                    pass

            if not label_text:
                label_text = input_el.get_attribute("aria-label") or input_el.get_attribute("placeholder")

            input_data["label"] = label_text or name or input_id or None

            if input_el.get_attribute("placeholder"):
                input_data["placeholder"] = input_el.get_attribute("placeholder")
            if input_el.get_attribute("required"):
                input_data["required"] = True

            # For select elements
            if tag == "select":
                options = []
                for option in input_el.find_elements(By.TAG_NAME, "option"):
                    options.append({
                        "value": option.get_attribute("value") or "",
                        "text": option.text.strip(),
                    })
                if options:
                    input_data["options"] = options

            return input_data

        except Exception as e:
            logger.debug(f"Error extracting input data: {e}")
            return None

    def _crawl_page(self, url: str, depth: int) -> Dict:
        """Crawl a single page."""
        norm = self._normalize_url(url, self.base_url)

        try:
            logger.info(f"[CRAWL] Visiting {norm} (depth {depth})")
            
            # Set a shorter timeout for page load
            self.driver.set_page_load_timeout(15)  # Reduced from default
            self.driver.get(norm)
            self._wait_ready()
            
            logger.info(f"[CRAWL] Page loaded: {self.driver.title}")
            logger.info(f"[CRAWL] Page source length: {len(self.driver.page_source)} chars")

            # Extract UI elements
            page_data = self._extract_elements()
            
            # ALWAYS return page data, even if empty
            if not page_data:
                logger.warning(f"[CRAWL] Extraction returned None for {norm}, creating empty page data")
                page_data = {
                    "page_url": norm,
                    "title": self.driver.title,
                    "headings": [],
                    "forms": [],
                    "elements": [],
                    "navigation": [],
                    "footer": [],
                }

            # Extract links for BFS
            all_links = []
            for link_list in [page_data.get("navigation", []), page_data.get("footer", []), page_data.get("elements", [])]:
                for el in link_list:
                    href = el.get("href")
                    if href:
                        all_links.append(href)

            # Enqueue internal links (limit to prevent queue explosion)
            if depth < self.max_depth and len(self.visited_urls) < self.max_pages:
                links_added = 0
                max_links_per_page = 20  # Limit links per page
                for link_url in all_links:
                    if links_added >= max_links_per_page:
                        break
                    normalized = self._normalize_url(link_url, self.base_url)
                    if normalized and normalized not in self.visited_urls:
                        if self._is_same_domain(normalized):
                            # Check queue size to prevent explosion
                            if len(self.page_queue) < 100:  # Max queue size
                                self.page_queue.append((normalized, depth + 1))
                                links_added += 1

            elem_count = (
                len(page_data.get("elements", []))
                + sum(len(f.get("elements", [])) for f in page_data.get("forms", []))
                + len(page_data.get("navigation", []))
                + len(page_data.get("footer", []))
            )

            logger.info(f"  -> {elem_count} elements, {len(page_data.get('forms', []))} forms, "
                       f"{len(page_data.get('navigation', []))} nav links")

            return page_data

        except TimeoutException:
            logger.warning(f"[CRAWL] Timeout loading {norm}")
            # Return empty page data instead of None
            return {
                "page_url": norm,
                "title": "",
                "headings": [],
                "forms": [],
                "elements": [],
                "navigation": [],
                "footer": [],
                "error": "timeout",
            }
        except Exception as e:
            logger.error(f"[CRAWL] Error crawling {norm}: {e}", exc_info=True)
            # Return empty page data instead of None
            return {
                "page_url": norm,
                "title": "",
                "headings": [],
                "forms": [],
                "elements": [],
                "navigation": [],
                "footer": [],
                "error": str(e),
            }

    def crawl(self, start_url: str) -> Dict:
        """Start crawling from start_url."""
        logger.info(f"Starting crawl: {start_url}")
        self.base_url = start_url
        self.base_domain = self._extract_domain(start_url)
        self.visited_urls.clear()
        self.page_queue.clear()
        self.page_results.clear()

        self._init_driver()

        try:
            self.page_queue.append((self._normalize_url(start_url), 0))
            max_iterations = self.max_pages * 2  # Safety limit
            iterations = 0

            while self.page_queue and len(self.visited_urls) < self.max_pages:
                iterations += 1
                if iterations > max_iterations:
                    logger.warning(f"Reached max iterations ({max_iterations}), stopping crawl")
                    break

                url, depth = self.page_queue.popleft()
                if url in self.visited_urls:
                    continue
                if not self._is_same_domain(url):
                    continue
                if depth > self.max_depth:
                    continue

                self.visited_urls.add(url)
                logger.info(f"[CRAWL] Page {len(self.visited_urls)}/{self.max_pages}: {url} (depth {depth})")

                try:
                    result = self._crawl_page(url, depth)
                    # ALWAYS append result, even if empty
                    if result:
                        self.page_results.append(result)
                        logger.info(f"[CRAWL] Page added to results. Total pages: {len(self.page_results)}")
                    else:
                        # Create empty page entry if result is None
                        logger.warning(f"[CRAWL] Result was None for {url}, creating empty entry")
                        self.page_results.append({
                            "page_url": url,
                            "title": "",
                            "headings": [],
                            "forms": [],
                            "elements": [],
                            "navigation": [],
                            "footer": [],
                        })
                except Exception as e:
                    logger.error(f"[CRAWL] Error processing page {url}: {e}", exc_info=True)
                    # Add empty entry even on error
                    self.page_results.append({
                        "page_url": url,
                        "title": "",
                        "headings": [],
                        "forms": [],
                        "elements": [],
                        "navigation": [],
                        "footer": [],
                        "error": str(e),
                    })

                logger.info(f"Progress: {len(self.visited_urls)}/{self.max_pages} pages, queue size: {len(self.page_queue)}")
                
                # Safety check: if queue is huge, stop adding more
                if len(self.page_queue) > 200:
                    logger.warning("Queue too large, stopping BFS expansion")
                    break
        finally:
            if self.driver:
                try:
                    self.driver.quit()
                except Exception:
                    pass
                self.driver = None

        logger.info(f"Crawl completed: {len(self.page_results)} pages extracted")
        return self._build_output()

    def _build_output(self) -> Dict:
        """Build final output."""
        total_el = 0
        for p in self.page_results:
            total_el += len(p.get("elements", []))
            total_el += sum(len(f.get("elements", [])) for f in p.get("forms", []))
            total_el += len(p.get("navigation", []))
            total_el += len(p.get("footer", []))

        return {
            "pages": self.page_results,
            "summary": {
                "total_pages": len(self.page_results),
                "total_elements": total_el,
                "pages_crawled": len(self.visited_urls),
            },
        }

    def get_results_json(self) -> str:
        """Get results as JSON string."""
        return json.dumps(self._build_output(), indent=2)

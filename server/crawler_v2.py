"""
Layer 1: Deterministic Crawl Layer (Selenium) - Improved Version

State-aware, structured UI exploration engine with robust error classification.
"""

import hashlib
import json
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple, Any
from urllib.parse import urljoin, urlparse, urlunparse

from selenium import webdriver
from selenium.common.exceptions import (
    TimeoutException,
    WebDriverException,
    NoSuchElementException,
    ElementNotInteractableException,
    StaleElementReferenceException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ErrorType(Enum):
    """Error classification types."""
    INTERNAL_JS_ERROR = "internal_js_error"
    EXTERNAL_SCRIPT_ERROR = "external_script_error"
    NETWORK_ERROR = "network_error"
    REAL_CRASH = "real_crash"


@dataclass
class ClassifiedError:
    """Classified error with type and metadata."""
    error_type: ErrorType
    message: str
    level: str
    timestamp: float
    source: Optional[str] = None
    url: Optional[str] = None


@dataclass
class LinkData:
    """Structured data for a link."""
    href: str
    text: str
    is_visible: bool
    is_clickable: bool
    absolute_url: str = ""
    is_external: bool = False


@dataclass
class InputData:
    """Structured data for an input field."""
    type: str
    name: Optional[str]
    id: Optional[str]
    required: bool
    placeholder: Optional[str]
    pattern: Optional[str]
    value: Optional[str] = None


@dataclass
class FormData:
    """Structured data for a form."""
    action: Optional[str]
    method: str
    inputs: List[InputData] = field(default_factory=list)
    id: Optional[str] = None
    absolute_action_url: str = ""


@dataclass
class ClickableElement:
    """Structured data for clickable elements."""
    tag: str
    text: Optional[str]
    type: Optional[str]
    id: Optional[str]
    href: Optional[str] = None
    is_visible: bool = False
    is_enabled: bool = False
    is_safe: bool = True
    onclick: Optional[str] = None
    role: Optional[str] = None


@dataclass
class PageState:
    """Represents a page state for SPA navigation."""
    state_id: str
    url: str
    dom_hash: str
    depth: int
    clickable_elements: List[ClickableElement] = field(default_factory=list)
    forms: List[FormData] = field(default_factory=list)
    element_count: int = 0
    timestamp: float = field(default_factory=time.time)
    transitions: List[str] = field(default_factory=list)  # List of state_ids reached from this state


@dataclass
class NetworkRequest:
    """Network request information."""
    url: str
    status_code: Optional[int]
    method: Optional[str] = None
    is_main_document: bool = False
    error_type: Optional[str] = None


@dataclass
class CrawlResult:
    """Result of crawling a single page/state."""
    url: str
    state_id: str
    dom_hash: str
    depth: int
    http_status: Optional[int] = None
    
    # Extracted data
    links: List[LinkData] = field(default_factory=list)
    forms: List[FormData] = field(default_factory=list)
    clickable_elements: List[ClickableElement] = field(default_factory=list)
    dropdowns: List[Dict[str, Any]] = field(default_factory=list)
    
    # Errors (classified)
    errors: Dict[str, List[ClassifiedError]] = field(default_factory=lambda: {
        "internal": [],
        "external": [],
        "network": [],
        "crashes": []
    })
    
    # Network requests
    network_requests: List[NetworkRequest] = field(default_factory=list)
    
    # Interaction results
    form_submission_results: List[Dict[str, Any]] = field(default_factory=list)
    click_results: List[Dict[str, Any]] = field(default_factory=list)
    
    # State tracking
    crashed: bool = False
    crash_reason: Optional[str] = None
    state_changed: bool = False


class DeterministicCrawlerV2:
    """
    Improved Layer 1: Deterministic Crawl Layer
    
    State-aware crawler with robust error classification and BFS traversal.
    """

    def __init__(
        self,
        max_pages: int = 50,
        max_depth: int = 5,
        max_states: int = 100,
        max_clicks_per_page: int = 20,
        max_total_interactions: int = 500,
        same_domain_only: bool = True,
        headless: bool = True,
        wait_time: float = 2.0,
        page_load_timeout: int = 60,
    ):
        """
        Initialize the crawler.
        
        Args:
            max_pages: Maximum number of pages to crawl
            max_depth: Maximum depth to crawl
            max_states: Maximum unique states to track
            max_clicks_per_page: Maximum clicks per page
            max_total_interactions: Maximum total interactions across all pages
            same_domain_only: Only crawl pages from the same domain
            headless: Run browser in headless mode
            wait_time: Wait time after interactions (seconds)
            page_load_timeout: Page load timeout in seconds
        """
        self.max_pages = max_pages
        self.max_depth = max_depth
        self.max_states = max_states
        self.max_clicks_per_page = max_clicks_per_page
        self.max_total_interactions = max_total_interactions
        self.same_domain_only = same_domain_only
        self.headless = headless
        self.wait_time = wait_time
        self.page_load_timeout = page_load_timeout
        
        self.driver: Optional[webdriver.Chrome] = None
        self.base_domain: Optional[str] = None
        self.base_url: Optional[str] = None
        
        # BFS crawl tracking
        self.visited_urls: Set[str] = set()
        self.visited_states: Dict[str, PageState] = {}  # state_id -> PageState
        self.state_graph: Dict[str, List[str]] = {}  # state_id -> [transition_state_ids]
        self.page_queue: deque = deque()
        
        # Interaction tracking
        self.total_interactions: int = 0
        
        # Results
        self.crawl_results: List[CrawlResult] = []
    
    def _normalize_url(self, url: str, base_url: Optional[str] = None) -> str:
        """
        Normalize URL by removing fragments, trailing slashes, and optionally query params.
        
        Args:
            url: URL to normalize
            base_url: Base URL for relative URL resolution
            
        Returns:
            Normalized absolute URL
        """
        if not url:
            return ""
        
        # Handle relative URLs
        if base_url:
            url = urljoin(base_url, url)
        
        # Parse URL
        parsed = urlparse(url)
        
        # Remove fragment
        normalized = urlunparse((
            parsed.scheme,
            parsed.netloc,
            parsed.path.rstrip('/') or '/',  # Normalize trailing slash
            parsed.params,
            parsed.query,  # Keep query params for now
            ''  # Remove fragment
        ))
        
        return normalized
    
    def _extract_domain(self, url: str) -> str:
        """Extract domain from URL."""
        parsed = urlparse(url)
        return parsed.netloc.lower()
    
    def _is_same_domain(self, url: str) -> bool:
        """Check if URL belongs to the same domain."""
        if not self.same_domain_only or not self.base_domain:
            return True
        return self._extract_domain(url) == self.base_domain
    
    def _is_driver_alive(self) -> bool:
        """Check if the driver session is still alive."""
        if not self.driver:
            return False
        try:
            _ = self.driver.current_url
            return True
        except Exception:
            return False
    
    def _initialize_driver(self) -> None:
        """Initialize Selenium WebDriver with console logging enabled."""
        chrome_options = Options()
        if self.headless:
            chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        
        # Enable console and performance logging
        chrome_options.set_capability('goog:loggingPrefs', {
            'browser': 'ALL',
            'performance': 'ALL'
        })
        
        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(
            service=service,
            options=chrome_options
        )
        self.driver.set_page_load_timeout(self.page_load_timeout)
        self.driver.implicitly_wait(5)
        
        # Enable network domain for CDP
        try:
            self.driver.execute_cdp_cmd('Network.enable', {})
        except Exception as e:
            logger.warning(f"Could not enable CDP network domain: {e}")
    
    def _compute_dom_hash(self, dom_source: str) -> str:
        """Compute hash of DOM for state comparison."""
        return hashlib.md5(dom_source.encode('utf-8')).hexdigest()
    
    def _classify_console_error(self, log_entry: Dict[str, Any], base_url: str) -> ClassifiedError:
        """
        Classify a console error as internal, external, or network error.
        
        Args:
            log_entry: Log entry from driver.get_log('browser')
            base_url: Base URL of the current page
            
        Returns:
            ClassifiedError object
        """
        message = log_entry.get('message', '')
        level = log_entry.get('level', '').upper()
        timestamp = log_entry.get('timestamp', time.time())
        source = log_entry.get('source', None)
        
        # Extract domain from base URL
        site_domain = self._extract_domain(base_url)
        
        # Check if error is from the site itself
        if site_domain in message.lower():
            error_type = ErrorType.INTERNAL_JS_ERROR
        elif any(keyword in message.lower() for keyword in ['network', 'failed', 'timeout', 'connection']):
            error_type = ErrorType.NETWORK_ERROR
        else:
            error_type = ErrorType.EXTERNAL_SCRIPT_ERROR
        
        return ClassifiedError(
            error_type=error_type,
            message=message,
            level=level,
            timestamp=timestamp,
            source=source,
            url=base_url
        )
    
    def _is_real_crash(self) -> Tuple[bool, Optional[str]]:
        """
        Detect if page has actually crashed (not just console errors).
        
        Returns:
            Tuple of (is_crashed, reason)
        """
        if not self._is_driver_alive():
            return True, "driver_session_lost"
        
        try:
            page_source = self.driver.page_source
            
            # Empty DOM
            if not page_source or len(page_source.strip()) < 100:
                return True, "empty_dom"
            
            # Check for crash indicators in page content
            page_lower = page_source.lower()
            crash_indicators = [
                "this site can't be reached",
                "this page isn't working",
                "err_connection",
                "err_name_not_resolved",
                "500 internal server error",
                "502 bad gateway",
                "503 service unavailable",
            ]
            
            for indicator in crash_indicators:
                if indicator in page_lower:
                    return True, f"crash_indicator: {indicator}"
            
            # Check title
            try:
                title = self.driver.title.lower()
                if any(keyword in title for keyword in ['error', 'not found', '500', '503']):
                    return True, f"error_title: {title[:50]}"
            except:
                pass
            
            # Check URL for error codes
            try:
                current_url = self.driver.current_url
                if '/500' in current_url or '/error' in current_url.lower():
                    return True, "error_url"
            except:
                pass
            
            return False, None
            
        except TimeoutException:
            return True, "timeout"
        except WebDriverException as e:
            if "Connection refused" in str(e) or "session" in str(e).lower():
                return True, f"driver_connection_lost: {str(e)}"
            return True, f"webdriver_exception: {str(e)}"
        except Exception as e:
            logger.debug(f"Error detecting crash: {e}")
            return False, None
    
    def _capture_and_classify_errors(self, base_url: str) -> Dict[str, List[ClassifiedError]]:
        """
        Capture console errors and classify them.
        
        Returns:
            Dictionary with classified errors
        """
        errors = {
            "internal": [],
            "external": [],
            "network": [],
            "crashes": []
        }
        
        try:
            logs = self.driver.get_log('browser')
            for log_entry in logs:
                level = log_entry.get('level', '').upper()
                # Only capture SEVERE and WARNING
                if level in ['SEVERE', 'WARNING']:
                    classified = self._classify_console_error(log_entry, base_url)
                    
                    if classified.error_type == ErrorType.INTERNAL_JS_ERROR:
                        errors["internal"].append(classified)
                    elif classified.error_type == ErrorType.EXTERNAL_SCRIPT_ERROR:
                        errors["external"].append(classified)
                    elif classified.error_type == ErrorType.NETWORK_ERROR:
                        errors["network"].append(classified)
        except Exception as e:
            logger.debug(f"Error capturing console logs: {e}")
        
        # Check for real crash
        crashed, crash_reason = self._is_real_crash()
        if crashed:
            errors["crashes"].append(ClassifiedError(
                error_type=ErrorType.REAL_CRASH,
                message=crash_reason or "Page crashed",
                level="CRITICAL",
                timestamp=time.time(),
                url=base_url
            ))
        
        return errors
    
    def _extract_links(self, base_url: str) -> List[LinkData]:
        """Extract all links from the current page."""
        links = []
        try:
            link_elements = self.driver.find_elements(By.TAG_NAME, "a")
            for elem in link_elements:
                try:
                    href = elem.get_attribute("href")
                    if not href:
                        continue
                    
                    text = elem.text.strip()
                    is_visible = elem.is_displayed()
                    is_clickable = False
                    
                    try:
                        if is_visible:
                            WebDriverWait(self.driver, 1).until(
                                EC.element_to_be_clickable(elem)
                            )
                            is_clickable = True
                    except:
                        pass
                    
                    absolute_url = self._normalize_url(href, base_url)
                    is_external = not self._is_same_domain(absolute_url)
                    
                    links.append(LinkData(
                        href=href,
                        text=text,
                        is_visible=is_visible,
                        is_clickable=is_clickable,
                        absolute_url=absolute_url,
                        is_external=is_external
                    ))
                except StaleElementReferenceException:
                    continue
                except Exception as e:
                    logger.debug(f"Error extracting link: {e}")
                    continue
        except Exception as e:
            logger.warning(f"Error extracting links: {e}")
        
        return links
    
    def _extract_clickable_elements(self, base_url: str) -> List[ClickableElement]:
        """
        Extract all clickable elements using comprehensive detection strategy.
        
        Detects:
        - <a> tags
        - <button> tags
        - <input type=button>
        - <input type=submit>
        - Elements with @role="button"
        - Elements with onclick
        - Elements with pointer cursor (if detectable)
        """
        clickables = []
        
        # XPath to find all clickable elements
        xpath_selectors = [
            "//a",
            "//button",
            "//input[@type='button']",
            "//input[@type='submit']",
            "//input[@type='reset']",
            "//*[@role='button']",
            "//*[@onclick]",
        ]
        
        found_elements = set()  # Track by (tag, id, text) to avoid duplicates
        
        for xpath in xpath_selectors:
            try:
                elements = self.driver.find_elements(By.XPATH, xpath)
                for elem in elements:
                    try:
                        # Get element properties
                        tag = elem.tag_name
                        elem_id = elem.get_attribute("id")
                        text = elem.text.strip() or elem.get_attribute("value") or ""
                        href = elem.get_attribute("href")
                        onclick = elem.get_attribute("onclick")
                        role = elem.get_attribute("role")
                        elem_type = elem.get_attribute("type")
                        
                        # Create unique key
                        key = (tag, elem_id, text[:50])
                        if key in found_elements:
                            continue
                        found_elements.add(key)
                        
                        # Check visibility and enabled state
                        is_visible = elem.is_displayed()
                        is_enabled = True
                        try:
                            is_enabled = elem.is_enabled()
                        except:
                            pass
                        
                        # Check if safe to click
                        is_safe = self._is_safe_click(elem, text, href, base_url)
                        
                        clickables.append(ClickableElement(
                            tag=tag,
                            text=text,
                            type=elem_type,
                            id=elem_id,
                            href=href,
                            is_visible=is_visible,
                            is_enabled=is_enabled,
                            is_safe=is_safe,
                            onclick=onclick,
                            role=role
                        ))
                    except StaleElementReferenceException:
                        continue
                    except Exception as e:
                        logger.debug(f"Error extracting clickable element: {e}")
                        continue
            except Exception as e:
                logger.debug(f"Error with XPath {xpath}: {e}")
                continue
        
        # Filter to only visible and enabled elements
        return [c for c in clickables if c.is_visible and c.is_enabled]
    
    def _is_safe_click(self, element, text: str, href: Optional[str], base_url: str) -> bool:
        """
        Determine if it's safe to click an element.
        
        Skips:
        - External links
        - mailto: links
        - Dangerous keywords (logout, delete, etc.)
        - File downloads
        """
        text_lower = text.lower()
        
        # Dangerous keywords
        dangerous_keywords = [
            "logout", "log out", "sign out", "signout",
            "delete", "remove", "destroy",
            "download", "export", "save as"
        ]
        
        if any(keyword in text_lower for keyword in dangerous_keywords):
            return False
        
        # Check href
        if href:
            href_lower = href.lower()
            
            # Skip external links
            if not self._is_same_domain(href):
                return False
            
            # Skip mailto, tel, etc.
            if href_lower.startswith(('mailto:', 'tel:', 'javascript:')):
                return False
            
            # Skip file downloads
            if any(ext in href_lower for ext in ['.pdf', '.zip', '.exe', '.dmg', '.csv', '.xlsx']):
                return False
        
        return True
    
    def _extract_forms(self, base_url: str) -> List[FormData]:
        """Extract all forms from the current page."""
        forms = []
        try:
            form_elements = self.driver.find_elements(By.TAG_NAME, "form")
            for form_elem in form_elements:
                try:
                    action = form_elem.get_attribute("action")
                    method = form_elem.get_attribute("method") or "get"
                    form_id = form_elem.get_attribute("id")
                    
                    inputs = []
                    try:
                        input_elements = form_elem.find_elements(By.TAG_NAME, "input")
                        for inp in input_elements:
                            try:
                                inputs.append(InputData(
                                    type=inp.get_attribute("type") or "text",
                                    name=inp.get_attribute("name"),
                                    id=inp.get_attribute("id"),
                                    required=inp.get_attribute("required") is not None,
                                    placeholder=inp.get_attribute("placeholder"),
                                    pattern=inp.get_attribute("pattern"),
                                    value=inp.get_attribute("value")
                                ))
                            except:
                                continue
                    except:
                        pass
                    
                    absolute_action_url = ""
                    if action:
                        absolute_action_url = self._normalize_url(action, base_url)
                    
                    forms.append(FormData(
                        action=action,
                        method=method.lower(),
                        inputs=inputs,
                        id=form_id,
                        absolute_action_url=absolute_action_url
                    ))
                except StaleElementReferenceException:
                    continue
                except Exception as e:
                    logger.debug(f"Error extracting form: {e}")
                    continue
        except Exception as e:
            logger.warning(f"Error extracting forms: {e}")
        
        return forms
    
    def _detect_state_change(self, old_hash: str, old_url: str, old_element_count: int) -> Tuple[bool, str, int]:
        """
        Detect if state has changed after an interaction.
        
        Returns:
            Tuple of (state_changed, new_hash, new_element_count)
        """
        if not self._is_driver_alive():
            return False, old_hash, old_element_count
        
        try:
            new_url = self.driver.current_url
            new_dom = self.driver.page_source
            new_hash = self._compute_dom_hash(new_dom)
            
            # Count elements
            try:
                new_element_count = len(self.driver.find_elements(By.XPATH, "//*"))
            except:
                new_element_count = old_element_count
            
            # Check for changes
            url_changed = (new_url != old_url)
            dom_changed = (new_hash != old_hash)
            
            # Significant element count change (>10% difference)
            element_change_threshold = max(10, old_element_count * 0.1)
            element_count_changed = abs(new_element_count - old_element_count) > element_change_threshold
            
            state_changed = url_changed or dom_changed or element_count_changed
            
            return state_changed, new_hash, new_element_count
            
        except Exception as e:
            logger.debug(f"Error detecting state change: {e}")
            return False, old_hash, old_element_count
    
    def _click_element_safely(self, element: ClickableElement, element_index: int, 
                              current_state_id: str) -> Dict[str, Any]:
        """
        Safely click an element and detect state changes.
        
        Returns:
            Dictionary with click results
        """
        result = {
            "element_index": element_index,
            "element_id": element.id,
            "element_text": element.text,
            "state_changed": False,
            "new_state_id": None,
            "url_changed": False,
            "dom_changed": False,
            "error_detected": False,
            "success": False,
            "error_message": None
        }
        
        if not element.is_safe:
            result["error_message"] = "Element marked as unsafe to click"
            return result
        
        if not self._is_driver_alive():
            result["error_message"] = "Driver session lost"
            return result
        
        try:
            # Capture initial state
            old_url = self.driver.current_url
            old_dom = self.driver.page_source
            old_hash = self._compute_dom_hash(old_dom)
            try:
                old_element_count = len(self.driver.find_elements(By.XPATH, "//*"))
            except:
                old_element_count = 0
            
            # Find and click the element
            elem = None
            if element.id:
                try:
                    elem = self.driver.find_element(By.ID, element.id)
                except:
                    pass
            
            if not elem and element.text:
                try:
                    # Try XPath by text
                    xpath = f"//{element.tag}[contains(text(), '{element.text[:50]}')]"
                    elem = self.driver.find_element(By.XPATH, xpath)
                except:
                    pass
            
            if not elem:
                # Try by tag and type
                try:
                    if element.tag == "button":
                        buttons = self.driver.find_elements(By.TAG_NAME, "button")
                        if element_index < len(buttons):
                            elem = buttons[element_index]
                    elif element.tag == "input":
                        buttons = self.driver.find_elements(
                            By.XPATH,
                            f"//input[@type='{element.type}']"
                        )
                        if element_index < len(buttons):
                            elem = buttons[element_index]
                except:
                    pass
            
            if not elem:
                result["error_message"] = "Element not found"
                return result
            
            # Click the element
            try:
                elem.click()
            except ElementNotInteractableException:
                result["error_message"] = "Element not interactable"
                return result
            except Exception as e:
                result["error_message"] = f"Error clicking: {str(e)}"
                return result
            
            # Wait for potential changes
            time.sleep(self.wait_time)
            
            # Check if driver is still alive
            if not self._is_driver_alive():
                result["error_message"] = "Driver session lost after click"
                result["error_detected"] = True
                return result
            
            # Detect state change
            state_changed, new_hash, new_element_count = self._detect_state_change(
                old_hash, old_url, old_element_count
            )
            
            result["state_changed"] = state_changed
            result["url_changed"] = (self.driver.current_url != old_url)
            result["dom_changed"] = (new_hash != old_hash)
            
            # If state changed, create or find new state
            if state_changed:
                new_state_id = f"{self.driver.current_url}:{new_hash}"
                result["new_state_id"] = new_state_id
                
                # If URL changed and it's external, try to go back
                if result["url_changed"] and not self._is_same_domain(self.driver.current_url):
                    try:
                        self.driver.back()
                        time.sleep(1)
                    except:
                        pass
            
            # Check for errors
            if self._is_driver_alive():
                errors = self._capture_and_classify_errors(self.driver.current_url)
                if errors["crashes"]:
                    result["error_detected"] = True
                    result["error_message"] = errors["crashes"][0].message
            
            result["success"] = True
            
        except Exception as e:
            result["error_message"] = str(e)
            result["error_detected"] = True
            logger.warning(f"Error clicking element: {e}")
        
        return result
    
    def _submit_form_safely(self, form: FormData, form_index: int, 
                           current_state_id: str) -> Dict[str, Any]:
        """
        Safely submit an empty form and detect state changes.
        
        Returns:
            Dictionary with submission results
        """
        result = {
            "form_index": form_index,
            "action": form.action,
            "method": form.method,
            "state_changed": False,
            "new_state_id": None,
            "url_changed": False,
            "dom_changed": False,
            "error_detected": False,
            "success": False,
            "error_message": None
        }
        
        if not self._is_driver_alive():
            result["error_message"] = "Driver session lost"
            return result
        
        try:
            # Capture initial state
            old_url = self.driver.current_url
            old_dom = self.driver.page_source
            old_hash = self._compute_dom_hash(old_dom)
            try:
                old_element_count = len(self.driver.find_elements(By.XPATH, "//*"))
            except:
                old_element_count = 0
            
            # Find form element
            form_elem = None
            if form.id:
                try:
                    form_elem = self.driver.find_element(By.ID, form.id)
                except:
                    pass
            
            if not form_elem:
                forms = self.driver.find_elements(By.TAG_NAME, "form")
                if form_index < len(forms):
                    form_elem = forms[form_index]
            
            if not form_elem:
                result["error_message"] = "Form element not found"
                return result
            
            # Submit form (empty)
            try:
                form_elem.submit()
            except Exception as e:
                result["error_message"] = f"Could not submit form: {str(e)}"
                return result
            
            # Wait for changes
            time.sleep(self.wait_time)
            
            # Check if driver is still alive
            if not self._is_driver_alive():
                result["error_message"] = "Driver session lost after submission"
                result["error_detected"] = True
                return result
            
            # Detect state change
            state_changed, new_hash, new_element_count = self._detect_state_change(
                old_hash, old_url, old_element_count
            )
            
            result["state_changed"] = state_changed
            result["url_changed"] = (self.driver.current_url != old_url)
            result["dom_changed"] = (new_hash != old_hash)
            
            if state_changed:
                new_state_id = f"{self.driver.current_url}:{new_hash}"
                result["new_state_id"] = new_state_id
            
            # Check for errors
            if self._is_driver_alive():
                errors = self._capture_and_classify_errors(self.driver.current_url)
                if errors["crashes"]:
                    result["error_detected"] = True
                    result["error_message"] = errors["crashes"][0].message
                elif errors["internal"]:
                    # Internal errors might indicate validation failures (expected)
                    result["error_detected"] = True
            
            result["success"] = True
            
        except Exception as e:
            result["error_message"] = str(e)
            result["error_detected"] = True
            logger.warning(f"Error submitting form: {e}")
        
        return result
    
    def _wait_for_page_ready(self, timeout: int = 30) -> bool:
        """Wait for page to be ready (for SPAs)."""
        try:
            WebDriverWait(self.driver, timeout).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
            time.sleep(2)  # Additional wait for SPAs
            return True
        except TimeoutException:
            logger.warning("Page ready state timeout, continuing anyway")
            return False
        except Exception as e:
            logger.debug(f"Error waiting for page ready: {e}")
            return False
    
    def _crawl_page(self, url: str, depth: int = 0) -> CrawlResult:
        """Crawl a single page and extract structured data."""
        logger.info(f"Crawling page: {url} (depth: {depth})")
        
        # Normalize URL
        normalized_url = self._normalize_url(url, self.base_url)
        
        result = CrawlResult(
            url=normalized_url,
            state_id="",
            dom_hash="",
            depth=depth
        )
        
        try:
            # Navigate to page
            try:
                self.driver.get(normalized_url)
            except TimeoutException:
                logger.warning(f"Page load timeout for {normalized_url}, attempting to continue")
                if not self._is_driver_alive():
                    result.crashed = True
                    result.crash_reason = "timeout_and_driver_lost"
                    return result
                time.sleep(3)
            
            # Wait for page ready
            self._wait_for_page_ready(timeout=20)
            time.sleep(self.wait_time)
            
            if not self._is_driver_alive():
                result.crashed = True
                result.crash_reason = "driver_lost_after_load"
                return result
            
            # Get HTTP status
            try:
                status = self.driver.execute_script(
                    "return window.performance.getEntriesByType('navigation')[0].responseStatus || 200;"
                )
                result.http_status = status
            except:
                pass
            
            # Check for real crash
            crashed, crash_reason = self._is_real_crash()
            if crashed:
                result.crashed = True
                result.crash_reason = crash_reason
                logger.warning(f"Page crashed: {crash_reason}")
                return result
            
            # Get current URL and compute state
            try:
                current_url = self.driver.current_url
                dom_source = self.driver.page_source
                dom_hash = self._compute_dom_hash(dom_source)
                state_id = f"{current_url}:{dom_hash}"
                
                result.state_id = state_id
                result.dom_hash = dom_hash
            except Exception as e:
                logger.warning(f"Could not compute state: {e}")
                return result
            
            # Extract structured data
            result.links = self._extract_links(current_url)
            result.forms = self._extract_forms(current_url)
            result.clickable_elements = self._extract_clickable_elements(current_url)
            
            # Capture and classify errors
            result.errors = self._capture_and_classify_errors(current_url)
            
            # Extract dropdowns
            try:
                selects = self.driver.find_elements(By.TAG_NAME, "select")
                for sel in selects:
                    try:
                        options = [opt.text for opt in sel.find_elements(By.TAG_NAME, "option")]
                        result.dropdowns.append({
                            "id": sel.get_attribute("id"),
                            "name": sel.get_attribute("name"),
                            "options": options,
                            "is_visible": sel.is_displayed()
                        })
                    except:
                        continue
            except:
                pass
            
            # Submit forms (if within interaction limits)
            safe_forms = [f for f in result.forms if f.method.lower() in ['post', 'get']]
            for i, form in enumerate(safe_forms[:5]):  # Limit forms per page
                if self.total_interactions >= self.max_total_interactions:
                    break
                if not self._is_driver_alive():
                    break
                
                submission_result = self._submit_form_safely(form, i, state_id)
                result.form_submission_results.append(submission_result)
                self.total_interactions += 1
                
                # If state changed, track it
                if submission_result.get("new_state_id"):
                    if state_id not in self.state_graph:
                        self.state_graph[state_id] = []
                    if submission_result["new_state_id"] not in self.state_graph[state_id]:
                        self.state_graph[state_id].append(submission_result["new_state_id"])
            
            # Click safe elements (if within limits)
            safe_clickables = [c for c in result.clickable_elements if c.is_safe]
            clicks_to_attempt = min(len(safe_clickables), self.max_clicks_per_page)
            
            for i in range(clicks_to_attempt):
                if self.total_interactions >= self.max_total_interactions:
                    break
                if not self._is_driver_alive():
                    break
                
                element = safe_clickables[i]
                click_result = self._click_element_safely(element, i, state_id)
                result.click_results.append(click_result)
                self.total_interactions += 1
                
                # If state changed, track it
                if click_result.get("new_state_id"):
                    if state_id not in self.state_graph:
                        self.state_graph[state_id] = []
                    if click_result["new_state_id"] not in self.state_graph[state_id]:
                        self.state_graph[state_id].append(click_result["new_state_id"])
            
            # Store state
            if state_id not in self.visited_states:
                element_count = len(self.driver.find_elements(By.XPATH, "//*"))
                page_state = PageState(
                    state_id=state_id,
                    url=current_url,
                    dom_hash=dom_hash,
                    depth=depth,
                    clickable_elements=result.clickable_elements,
                    forms=result.forms,
                    element_count=element_count
                )
                self.visited_states[state_id] = page_state
            
            # Add internal links to queue
            if depth < self.max_depth and len(self.visited_urls) < self.max_pages:
                for link in result.links:
                    if (link.is_clickable and 
                        link.absolute_url and 
                        not link.is_external and
                        self._normalize_url(link.absolute_url) not in self.visited_urls):
                        
                        normalized_link = self._normalize_url(link.absolute_url)
                        if normalized_link not in self.visited_urls:
                            self.page_queue.append((normalized_link, depth + 1))
            
            logger.info(f"Extracted {len(result.links)} links, {len(result.forms)} forms, "
                       f"{len(result.clickable_elements)} clickable elements")
            
        except TimeoutException:
            # Try to extract partial content
            if self._is_driver_alive():
                try:
                    current_url = self.driver.current_url
                    result.links = self._extract_links(current_url)
                    result.forms = self._extract_forms(current_url)
                    result.clickable_elements = self._extract_clickable_elements(current_url)
                    result.errors = self._capture_and_classify_errors(current_url)
                    if len(result.links) > 0 or len(result.forms) > 0 or len(result.clickable_elements) > 0:
                        result.crashed = False
                    else:
                        result.crashed = True
                        result.crash_reason = "timeout_no_content"
                except:
                    result.crashed = True
                    result.crash_reason = "timeout_and_extraction_failed"
            else:
                result.crashed = True
                result.crash_reason = "timeout_and_driver_lost"
        except Exception as e:
            result.crashed = True
            result.crash_reason = str(e)
            logger.error(f"Error crawling page {url}: {e}")
        
        return result
    
    def crawl(self, start_url: str) -> Dict[str, Any]:
        """
        Start crawling from a given URL using BFS traversal.
        
        Args:
            start_url: Starting URL for the crawl
            
        Returns:
            Structured crawl results dictionary
        """
        logger.info(f"Starting crawl from: {start_url}")
        
        self.base_url = start_url
        self.base_domain = self._extract_domain(start_url)
        self.visited_urls.clear()
        self.visited_states.clear()
        self.state_graph.clear()
        self.page_queue.clear()
        self.crawl_results.clear()
        self.total_interactions = 0
        
        # Initialize driver
        self._initialize_driver()
        
        try:
            # Add starting URL to queue
            normalized_start = self._normalize_url(start_url)
            self.page_queue.append((normalized_start, 0))
            
            # BFS crawl loop
            while self.page_queue and len(self.visited_urls) < self.max_pages:
                url, depth = self.page_queue.popleft()
                
                # Skip if already visited
                if url in self.visited_urls:
                    continue
                
                # Skip if not same domain
                if not self._is_same_domain(url):
                    continue
                
                # Skip if depth exceeded
                if depth > self.max_depth:
                    continue
                
                # Skip if max states reached
                if len(self.visited_states) >= self.max_states:
                    logger.info(f"Max states ({self.max_states}) reached, stopping crawl")
                    break
                
                # Mark as visited
                self.visited_urls.add(url)
                
                # Crawl the page
                result = self._crawl_page(url, depth)
                self.crawl_results.append(result)
                
                logger.info(f"Progress: {len(self.visited_urls)}/{self.max_pages} pages, "
                           f"{len(self.visited_states)} states, {self.total_interactions} interactions")
        
        finally:
            if self.driver:
                self.driver.quit()
                self.driver = None
        
        # Build structured output
        return self._build_structured_output()
    
    def _build_structured_output(self) -> Dict[str, Any]:
        """Build structured output for AI layer."""
        
        # Aggregate errors
        all_errors = {
            "internal": [],
            "external": [],
            "network": [],
            "crashes": []
        }
        
        for result in self.crawl_results:
            for error_type in all_errors.keys():
                all_errors[error_type].extend(result.errors.get(error_type, []))
        
        # Build states list
        states_list = []
        for state_id, state in self.visited_states.items():
            states_list.append({
                "state_id": state.state_id,
                "url": state.url,
                "dom_hash": state.dom_hash,
                "depth": state.depth,
                "element_count": state.element_count,
                "clickable_count": len(state.clickable_elements),
                "form_count": len(state.forms),
                "transitions": state.transitions
            })
        
        # Build summary
        total_pages = len(self.visited_urls)
        total_states = len(self.visited_states)
        crashed_pages = sum(1 for r in self.crawl_results if r.crashed)
        
        summary = {
            "total_pages_crawled": total_pages,
            "total_states_discovered": total_states,
            "total_interactions": self.total_interactions,
            "pages_crashed": crashed_pages,
            "total_links": sum(len(r.links) for r in self.crawl_results),
            "total_forms": sum(len(r.forms) for r in self.crawl_results),
            "total_clickable_elements": sum(len(r.clickable_elements) for r in self.crawl_results),
            "error_counts": {
                "internal_js_errors": len(all_errors["internal"]),
                "external_script_errors": len(all_errors["external"]),
                "network_errors": len(all_errors["network"]),
                "real_crashes": len(all_errors["crashes"])
            }
        }
        
        # Serialize results
        def serialize_error(err: ClassifiedError) -> dict:
            return {
                "type": err.error_type.value,
                "message": err.message,
                "level": err.level,
                "timestamp": err.timestamp,
                "source": err.source,
                "url": err.url
            }
        
        def serialize_result(result: CrawlResult) -> dict:
            return {
                "url": result.url,
                "state_id": result.state_id,
                "dom_hash": result.dom_hash,
                "depth": result.depth,
                "http_status": result.http_status,
                "crashed": result.crashed,
                "crash_reason": result.crash_reason,
                "links_count": len(result.links),
                "forms_count": len(result.forms),
                "clickable_elements_count": len(result.clickable_elements),
                "errors": {
                    k: [serialize_error(e) for e in v]
                    for k, v in result.errors.items()
                },
                "form_submissions": len(result.form_submission_results),
                "clicks_attempted": len(result.click_results)
            }
        
        return {
            "summary": summary,
            "pages": [serialize_result(r) for r in self.crawl_results],
            "states": states_list,
            "errors": {
                k: [serialize_error(e) for e in v]
                for k, v in all_errors.items()
            },
            "interaction_graph": {
                state_id: transitions
                for state_id, transitions in self.state_graph.items()
            }
        }
    
    def get_results_json(self) -> str:
        """Get crawl results as JSON string."""
        results = self._build_structured_output()
        return json.dumps(results, indent=2)

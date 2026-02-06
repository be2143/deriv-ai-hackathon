"""
Layer 1: Deterministic Crawl Layer (Selenium)

This module implements a structured web crawler that:
- Extracts structured UI data (links, forms, inputs, buttons, dropdowns)
- Captures console errors, network failures, HTTP status codes
- Tests interactions (clicks buttons, submits empty forms)
- Detects crashes and anomalies
- Handles dynamic web apps (SPA) with state memory
"""

import hashlib
import json
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple, Any
from urllib.parse import urljoin, urlparse

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


@dataclass
class LinkData:
    """Structured data for a link."""
    href: str
    text: str
    is_visible: bool
    is_clickable: bool
    absolute_url: str = ""


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
class ButtonData:
    """Structured data for a button."""
    tag: str  # 'button', 'input', 'div', etc.
    text: Optional[str]
    type: Optional[str]
    id: Optional[str]
    is_visible: bool
    is_clickable: bool
    onclick: Optional[str] = None


@dataclass
class DropdownData:
    """Structured data for a dropdown/select."""
    id: Optional[str]
    name: Optional[str]
    options: List[str] = field(default_factory=list)
    is_visible: bool = False


@dataclass
class ConsoleError:
    """Captured console error."""
    level: str
    message: str
    timestamp: float
    source: Optional[str] = None


@dataclass
class NetworkFailure:
    """Captured network failure."""
    url: str
    status_code: Optional[int]
    error_type: str
    timestamp: float


@dataclass
class PageState:
    """Represents a page state for SPA navigation."""
    url: str
    dom_hash: str
    depth: int
    clickable_elements: List[ButtonData] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)


@dataclass
class CrawlResult:
    """Result of crawling a single page."""
    url: str
    links: List[LinkData] = field(default_factory=list)
    forms: List[FormData] = field(default_factory=list)
    buttons: List[ButtonData] = field(default_factory=list)
    dropdowns: List[DropdownData] = field(default_factory=list)
    console_errors: List[ConsoleError] = field(default_factory=list)
    network_failures: List[NetworkFailure] = field(default_factory=list)
    crashed: bool = False
    crash_reason: Optional[str] = None
    form_submission_results: List[Dict[str, Any]] = field(default_factory=list)
    button_click_results: List[Dict[str, Any]] = field(default_factory=list)
    http_status: Optional[int] = None


class DeterministicCrawler:
    """
    Layer 1: Deterministic Crawl Layer
    
    Crawls websites with structured data extraction and interaction testing.
    """

    def __init__(
        self,
        max_pages: int = 50,
        max_depth: int = 5,
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
            same_domain_only: Only crawl pages from the same domain
            headless: Run browser in headless mode
            wait_time: Wait time after interactions (seconds)
            page_load_timeout: Page load timeout in seconds (default: 60)
        """
        self.max_pages = max_pages
        self.max_depth = max_depth
        self.same_domain_only = same_domain_only
        self.headless = headless
        self.wait_time = wait_time
        self.page_load_timeout = page_load_timeout
        
        self.driver: Optional[webdriver.Chrome] = None
        self.base_domain: Optional[str] = None
        self.visited_urls: Set[str] = set()
        self.visited_states: Set[str] = set()  # DOM hash states for SPA
        self.crawl_results: List[CrawlResult] = []
        self.page_queue: deque = deque()
        
    def _is_driver_alive(self) -> bool:
        """Check if the driver session is still alive."""
        if not self.driver:
            return False
        try:
            # Try to get the current URL - if this fails, driver is dead
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
        
        # Enable console logging (Selenium 4.x syntax)
        chrome_options.set_capability('goog:loggingPrefs', {'browser': 'ALL'})
        
        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(
            service=service,
            options=chrome_options
        )
        # Set timeout for SPAs that take time to load
        self.driver.set_page_load_timeout(self.page_load_timeout)
        self.driver.implicitly_wait(5)
        
        # Enable network domain for CDP (Chrome DevTools Protocol)
        try:
            self.driver.execute_cdp_cmd('Network.enable', {})
        except Exception as e:
            logger.warning(f"Could not enable CDP network domain: {e}")
    
    def _get_domain(self, url: str) -> str:
        """Extract domain from URL."""
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}"
    
    def _is_same_domain(self, url: str) -> bool:
        """Check if URL belongs to the same domain."""
        if not self.same_domain_only:
            return True
        if not self.base_domain:
            return True
        return self._get_domain(url) == self.base_domain
    
    def _normalize_url(self, url: str, base_url: str) -> str:
        """Normalize URL to absolute form."""
        if url.startswith('http://') or url.startswith('https://'):
            return url
        if url.startswith('//'):
            parsed_base = urlparse(base_url)
            return f"{parsed_base.scheme}:{url}"
        if url.startswith('/'):
            return urljoin(base_url, url)
        return urljoin(base_url, url)
    
    def _compute_dom_hash(self, dom_source: str) -> str:
        """Compute hash of DOM for state comparison."""
        return hashlib.md5(dom_source.encode('utf-8')).hexdigest()
    
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
                        # Check if element is clickable
                        if is_visible:
                            WebDriverWait(self.driver, 1).until(
                                EC.element_to_be_clickable(elem)
                            )
                            is_clickable = True
                    except:
                        pass
                    
                    absolute_url = self._normalize_url(href, base_url)
                    
                    links.append(LinkData(
                        href=href,
                        text=text,
                        is_visible=is_visible,
                        is_clickable=is_clickable,
                        absolute_url=absolute_url
                    ))
                except StaleElementReferenceException:
                    continue
                except Exception as e:
                    logger.debug(f"Error extracting link: {e}")
                    continue
        except Exception as e:
            logger.warning(f"Error extracting links: {e}")
        
        return links
    
    def _extract_inputs(self, form_element) -> List[InputData]:
        """Extract input fields from a form element."""
        inputs = []
        try:
            input_elements = form_element.find_elements(By.TAG_NAME, "input")
            for elem in input_elements:
                try:
                    inputs.append(InputData(
                        type=elem.get_attribute("type") or "text",
                        name=elem.get_attribute("name"),
                        id=elem.get_attribute("id"),
                        required=elem.get_attribute("required") is not None,
                        placeholder=elem.get_attribute("placeholder"),
                        pattern=elem.get_attribute("pattern"),
                        value=elem.get_attribute("value")
                    ))
                except StaleElementReferenceException:
                    continue
                except Exception as e:
                    logger.debug(f"Error extracting input: {e}")
                    continue
        except Exception as e:
            logger.debug(f"Error extracting inputs from form: {e}")
        
        return inputs
    
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
                    
                    inputs = self._extract_inputs(form_elem)
                    
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
    
    def _extract_buttons(self) -> List[ButtonData]:
        """Extract all buttons and clickable elements."""
        buttons = []
        
        # Standard button elements
        try:
            button_elements = self.driver.find_elements(By.TAG_NAME, "button")
            for elem in button_elements:
                try:
                    is_visible = elem.is_displayed()
                    is_clickable = False
                    
                    if is_visible:
                        try:
                            WebDriverWait(self.driver, 1).until(
                                EC.element_to_be_clickable(elem)
                            )
                            is_clickable = True
                        except:
                            pass
                    
                    buttons.append(ButtonData(
                        tag="button",
                        text=elem.text.strip() or elem.get_attribute("value"),
                        type=elem.get_attribute("type"),
                        id=elem.get_attribute("id"),
                        is_visible=is_visible,
                        is_clickable=is_clickable
                    ))
                except StaleElementReferenceException:
                    continue
                except Exception as e:
                    logger.debug(f"Error extracting button: {e}")
                    continue
        except Exception as e:
            logger.debug(f"Error extracting buttons: {e}")
        
        # Input buttons (submit, button types)
        try:
            input_buttons = self.driver.find_elements(
                By.XPATH, 
                "//input[@type='button' or @type='submit' or @type='reset']"
            )
            for elem in input_buttons:
                try:
                    is_visible = elem.is_displayed()
                    is_clickable = False
                    
                    if is_visible:
                        try:
                            WebDriverWait(self.driver, 1).until(
                                EC.element_to_be_clickable(elem)
                            )
                            is_clickable = True
                        except:
                            pass
                    
                    buttons.append(ButtonData(
                        tag="input",
                        text=elem.get_attribute("value"),
                        type=elem.get_attribute("type"),
                        id=elem.get_attribute("id"),
                        is_visible=is_visible,
                        is_clickable=is_clickable
                    ))
                except StaleElementReferenceException:
                    continue
                except Exception as e:
                    logger.debug(f"Error extracting input button: {e}")
                    continue
        except Exception as e:
            logger.debug(f"Error extracting input buttons: {e}")
        
        # Elements with role='button'
        try:
            role_buttons = self.driver.find_elements(
                By.XPATH, 
                "//*[@role='button']"
            )
            for elem in role_buttons:
                try:
                    is_visible = elem.is_displayed()
                    is_clickable = False
                    
                    if is_visible:
                        try:
                            WebDriverWait(self.driver, 1).until(
                                EC.element_to_be_clickable(elem)
                            )
                            is_clickable = True
                        except:
                            pass
                    
                    buttons.append(ButtonData(
                        tag=elem.tag_name,
                        text=elem.text.strip(),
                        type=None,
                        id=elem.get_attribute("id"),
                        is_visible=is_visible,
                        is_clickable=is_clickable
                    ))
                except StaleElementReferenceException:
                    continue
                except Exception as e:
                    logger.debug(f"Error extracting role button: {e}")
                    continue
        except Exception as e:
            logger.debug(f"Error extracting role buttons: {e}")
        
        # Elements with onclick attribute
        try:
            onclick_elements = self.driver.find_elements(
                By.XPATH, 
                "//*[@onclick]"
            )
            for elem in onclick_elements:
                try:
                    # Skip if already added
                    if any(b.id == elem.get_attribute("id") for b in buttons if b.id):
                        continue
                    
                    is_visible = elem.is_displayed()
                    is_clickable = False
                    
                    if is_visible:
                        try:
                            WebDriverWait(self.driver, 1).until(
                                EC.element_to_be_clickable(elem)
                            )
                            is_clickable = True
                        except:
                            pass
                    
                    buttons.append(ButtonData(
                        tag=elem.tag_name,
                        text=elem.text.strip(),
                        type=None,
                        id=elem.get_attribute("id"),
                        is_visible=is_visible,
                        is_clickable=is_clickable,
                        onclick=elem.get_attribute("onclick")
                    ))
                except StaleElementReferenceException:
                    continue
                except Exception as e:
                    logger.debug(f"Error extracting onclick element: {e}")
                    continue
        except Exception as e:
            logger.debug(f"Error extracting onclick elements: {e}")
        
        return buttons
    
    def _extract_dropdowns(self) -> List[DropdownData]:
        """Extract all dropdown/select elements."""
        dropdowns = []
        try:
            select_elements = self.driver.find_elements(By.TAG_NAME, "select")
            for elem in select_elements:
                try:
                    is_visible = elem.is_displayed()
                    options = []
                    
                    option_elements = elem.find_elements(By.TAG_NAME, "option")
                    for opt in option_elements:
                        try:
                            options.append(opt.text.strip() or opt.get_attribute("value") or "")
                        except:
                            continue
                    
                    dropdowns.append(DropdownData(
                        id=elem.get_attribute("id"),
                        name=elem.get_attribute("name"),
                        options=options,
                        is_visible=is_visible
                    ))
                except StaleElementReferenceException:
                    continue
                except Exception as e:
                    logger.debug(f"Error extracting dropdown: {e}")
                    continue
        except Exception as e:
            logger.warning(f"Error extracting dropdowns: {e}")
        
        return dropdowns
    
    def _capture_console_errors(self) -> List[ConsoleError]:
        """Capture console errors from browser logs."""
        errors = []
        try:
            logs = self.driver.get_log('browser')
            for log_entry in logs:
                level = log_entry.get('level', '').upper()
                if level in ['SEVERE', 'WARNING']:
                    errors.append(ConsoleError(
                        level=level,
                        message=log_entry.get('message', ''),
                        timestamp=log_entry.get('timestamp', time.time()),
                        source=log_entry.get('source', None)
                    ))
        except Exception as e:
            logger.debug(f"Error capturing console logs: {e}")
        
        return errors
    
    def _detect_network_failures(self) -> List[NetworkFailure]:
        """Detect network failures (basic implementation)."""
        failures = []
        # Note: Full network interception requires CDP or Playwright
        # This is a basic implementation that checks for common error indicators
        try:
            # Check page title for error indicators
            title = self.driver.title.lower()
            if any(keyword in title for keyword in ['error', 'not found', '500', '503', '502']):
                failures.append(NetworkFailure(
                    url=self.driver.current_url,
                    status_code=None,
                    error_type="page_error_indicator",
                    timestamp=time.time()
                ))
        except Exception as e:
            logger.debug(f"Error detecting network failures: {e}")
        
        return failures
    
    def _detect_crash(self) -> Tuple[bool, Optional[str]]:
        """Detect if page has crashed."""
        # First check if driver is alive
        if not self._is_driver_alive():
            return True, "driver_session_lost"
        
        try:
            # Check for blank page
            page_source = self.driver.page_source
            if len(page_source.strip()) < 100:
                return True, "blank_page"
            
            # Check title for crash indicators
            title = self.driver.title.lower()
            crash_indicators = [
                'this page isn\'t working',
                'page not found',
                '500 internal server error',
                '502 bad gateway',
                '503 service unavailable',
                'error',
                'crash'
            ]
            
            for indicator in crash_indicators:
                if indicator in title:
                    return True, f"crash_indicator: {indicator}"
            
            # Check URL for error codes
            current_url = self.driver.current_url
            if '/500' in current_url or '/error' in current_url.lower():
                return True, "error_url"
            
            return False, None
        except TimeoutException:
            return True, "timeout"
        except WebDriverException as e:
            return True, f"webdriver_exception: {str(e)}"
        except Exception as e:
            # If we can't access driver properties, driver is likely dead
            if "Connection refused" in str(e) or "session" in str(e).lower():
                return True, f"driver_connection_lost: {str(e)}"
            logger.warning(f"Error detecting crash: {e}")
            return False, None
    
    def _submit_empty_form(self, form_data: FormData, form_index: int) -> Dict[str, Any]:
        """Submit an empty form and observe behavior."""
        result = {
            "form_index": form_index,
            "action": form_data.action,
            "method": form_data.method,
            "url_changed": False,
            "dom_changed": False,
            "error_detected": False,
            "success": False,
            "error_message": None
        }
        
        # Check if driver is still alive
        if not self._is_driver_alive():
            result["error_message"] = "Driver session lost"
            return result
        
        try:
            # Capture initial state
            try:
                old_url = self.driver.current_url
                old_dom = self.driver.page_source
                old_dom_hash = self._compute_dom_hash(old_dom)
            except (WebDriverException, Exception) as e:
                result["error_message"] = f"Could not capture initial state: {str(e)}"
                return result
            
            # Find the form element
            form_elem = None
            if form_data.id:
                try:
                    form_elem = self.driver.find_element(By.ID, form_data.id)
                except:
                    pass
            
            if not form_elem:
                # Try to find by action or method
                forms = self.driver.find_elements(By.TAG_NAME, "form")
                if form_index < len(forms):
                    form_elem = forms[form_index]
            
            if not form_elem:
                result["error_message"] = "Form element not found"
                return result
            
            # Find submit button
            submit_button = None
            try:
                submit_button = form_elem.find_element(
                    By.XPATH, 
                    ".//button[@type='submit'] | .//input[@type='submit']"
                )
            except:
                pass
            
            if not submit_button:
                # Try to submit form directly
                try:
                    form_elem.submit()
                except Exception as e:
                    result["error_message"] = f"Could not submit form: {str(e)}"
                    return result
            else:
                try:
                    submit_button.click()
                except ElementNotInteractableException:
                    result["error_message"] = "Submit button not interactable"
                    return result
                except Exception as e:
                    result["error_message"] = f"Error clicking submit: {str(e)}"
                    return result
            
            # Wait for potential changes
            time.sleep(self.wait_time)
            
            # Check if driver is still alive after submission
            if not self._is_driver_alive():
                result["error_message"] = "Driver session lost after form submission"
                result["error_detected"] = True
                return result
            
            # Check for changes
            try:
                new_url = self.driver.current_url
                new_dom = self.driver.page_source
                new_dom_hash = self._compute_dom_hash(new_dom)
                
                result["url_changed"] = (new_url != old_url)
                result["dom_changed"] = (new_dom_hash != old_dom_hash)
            except (WebDriverException, Exception) as e:
                result["error_message"] = f"Could not check state after submission: {str(e)}"
                result["error_detected"] = True
                return result
            
            # Check for error messages in DOM (only if driver is alive)
            if self._is_driver_alive():
                error_indicators = [
                    "error",
                    "invalid",
                    "required",
                    "validation",
                    "failed"
                ]
                
                page_text = new_dom.lower()
                for indicator in error_indicators:
                    if indicator in page_text:
                        # Check if it's actually an error message (not just in code)
                        # Simple heuristic: check if it appears in visible text
                        try:
                            body_text = self.driver.find_element(By.TAG_NAME, "body").text.lower()
                            if indicator in body_text:
                                result["error_detected"] = True
                                break
                        except:
                            pass
                
                # Check console errors
                try:
                    console_errors = self._capture_console_errors()
                    if console_errors:
                        result["error_detected"] = True
                except Exception as e:
                    logger.debug(f"Error capturing console errors: {e}")
                
                # Check for crash
                crashed, crash_reason = self._detect_crash()
                if crashed:
                    result["error_detected"] = True
                    result["error_message"] = crash_reason
            
            result["success"] = True
            
        except (WebDriverException, Exception) as e:
            result["error_message"] = str(e)
            result["error_detected"] = True
            logger.warning(f"Error submitting form: {e}")
        
        return result
    
    def _click_button(self, button_data: ButtonData, button_index: int) -> Dict[str, Any]:
        """Click a button and observe behavior."""
        result = {
            "button_index": button_index,
            "button_id": button_data.id,
            "button_text": button_data.text,
            "url_changed": False,
            "dom_changed": False,
            "navigation_occurred": False,
            "error_detected": False,
            "success": False,
            "error_message": None
        }
        
        # Check if driver is still alive
        if not self._is_driver_alive():
            result["error_message"] = "Driver session lost"
            return result
        
        if not button_data.is_clickable or not button_data.is_visible:
            result["error_message"] = "Button not clickable or not visible"
            return result
        
        try:
            # Capture initial state
            try:
                original_url = self.driver.current_url
                old_dom = self.driver.page_source
                old_dom_hash = self._compute_dom_hash(old_dom)
            except (WebDriverException, Exception) as e:
                result["error_message"] = f"Could not capture initial state: {str(e)}"
                return result
            
            # Find and click the button
            button_elem = None
            
            if button_data.id:
                try:
                    button_elem = self.driver.find_element(By.ID, button_data.id)
                except:
                    pass
            
            if not button_elem and button_data.text:
                try:
                    # Try to find by text (XPath)
                    button_elem = self.driver.find_element(
                        By.XPATH,
                        f"//{button_data.tag}[contains(text(), '{button_data.text[:50]}')]"
                    )
                except:
                    pass
            
            if not button_elem:
                # Try to find by index
                try:
                    if button_data.tag == "button":
                        buttons = self.driver.find_elements(By.TAG_NAME, "button")
                    elif button_data.tag == "input":
                        buttons = self.driver.find_elements(
                            By.XPATH,
                            f"//input[@type='{button_data.type}']"
                        )
                    else:
                        buttons = []
                    
                    if button_index < len(buttons):
                        button_elem = buttons[button_index]
                except:
                    pass
            
            if not button_elem:
                result["error_message"] = "Button element not found"
                return result
            
            # Click the button
            try:
                button_elem.click()
            except ElementNotInteractableException:
                result["error_message"] = "Button not interactable"
                return result
            except Exception as e:
                result["error_message"] = f"Error clicking button: {str(e)}"
                return result
            
            # Wait for potential changes
            time.sleep(self.wait_time)
            
            # Check if driver is still alive after click
            if not self._is_driver_alive():
                result["error_message"] = "Driver session lost after click"
                result["error_detected"] = True
                return result
            
            # Check for changes
            try:
                new_url = self.driver.current_url
                new_dom = self.driver.page_source
                new_dom_hash = self._compute_dom_hash(new_dom)
                
                result["url_changed"] = (new_url != original_url)
                result["dom_changed"] = (new_dom_hash != old_dom_hash)
                result["navigation_occurred"] = result["url_changed"] or result["dom_changed"]
            except (WebDriverException, Exception) as e:
                result["error_message"] = f"Could not check state after click: {str(e)}"
                result["error_detected"] = True
                return result
            
            # If URL changed, try to go back
            if result["url_changed"]:
                try:
                    if self._is_driver_alive():
                        self.driver.back()
                        time.sleep(1)
                except Exception as e:
                    logger.warning(f"Could not navigate back: {e}")
            
            # Check for errors (only if driver is still alive)
            if self._is_driver_alive():
                try:
                    console_errors = self._capture_console_errors()
                    if console_errors:
                        result["error_detected"] = True
                    
                    crashed, crash_reason = self._detect_crash()
                    if crashed:
                        result["error_detected"] = True
                        result["error_message"] = crash_reason
                except Exception as e:
                    logger.debug(f"Error checking for errors: {e}")
            
            result["success"] = True
            
        except (WebDriverException, Exception) as e:
            result["error_message"] = str(e)
            result["error_detected"] = True
            logger.warning(f"Error clicking button: {e}")
        
        return result
    
    def _wait_for_page_ready(self, timeout: int = 30) -> bool:
        """Wait for page to be ready (for SPAs)."""
        try:
            # Wait for document ready state
            WebDriverWait(self.driver, timeout).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
            
            # Additional wait for SPAs - wait a bit more for dynamic content
            time.sleep(2)
            
            # Try to wait for common SPA indicators
            try:
                # Wait for body to be present and have some content
                WebDriverWait(self.driver, 5).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )
            except:
                pass
            
            return True
        except TimeoutException:
            logger.warning("Page ready state timeout, continuing anyway")
            return False
        except Exception as e:
            logger.debug(f"Error waiting for page ready: {e}")
            return False
    
    def _extract_content_safely(self, result: CrawlResult, base_url: str) -> bool:
        """Safely extract content from page, handling errors gracefully."""
        try:
            result.links = self._extract_links(base_url)
            result.forms = self._extract_forms(base_url)
            result.buttons = self._extract_buttons()
            result.dropdowns = self._extract_dropdowns()
            result.console_errors = self._capture_console_errors()
            result.network_failures = self._detect_network_failures()
            return True
        except Exception as e:
            logger.warning(f"Error extracting content: {e}")
            return False
    
    def _crawl_page(self, url: str, depth: int = 0) -> CrawlResult:
        """Crawl a single page and extract structured data."""
        logger.info(f"Crawling page: {url} (depth: {depth})")
        
        result = CrawlResult(url=url)
        
        try:
            # Navigate to page with timeout handling
            try:
                self.driver.get(url)
            except TimeoutException:
                # Page load timed out, but try to continue if page partially loaded
                logger.warning(f"Page load timeout for {url}, attempting to continue with partial content")
                if not self._is_driver_alive():
                    result.crashed = True
                    result.crash_reason = "timeout_and_driver_lost"
                    return result
                # Give it a moment and try to extract what we can
                time.sleep(3)
            
            # Wait for page to be ready (especially important for SPAs)
            # Use shorter timeout since we already waited during get()
            self._wait_for_page_ready(timeout=20)
            
            # Additional wait for dynamic content (SPAs often need more time)
            time.sleep(self.wait_time)
            
            # Check if driver is still alive
            if not self._is_driver_alive():
                result.crashed = True
                result.crash_reason = "driver_lost_after_load"
                return result
            
            # Get HTTP status (if available)
            try:
                # Try to get status from JavaScript
                status = self.driver.execute_script(
                    "return window.performance.getEntriesByType('navigation')[0].responseStatus || 200;"
                )
                result.http_status = status
            except:
                pass
            
            # Check for crash
            crashed, crash_reason = self._detect_crash()
            if crashed:
                # Even if crashed, try to extract what we can
                logger.warning(f"Page may have issues: {crash_reason}, attempting partial extraction")
            
            try:
                base_url = self.driver.current_url
            except Exception as e:
                logger.warning(f"Could not get current URL: {e}")
                base_url = url
            
            # Extract structured data (safely)
            if not self._extract_content_safely(result, base_url):
                # If extraction failed, mark as crashed
                result.crashed = True
                result.crash_reason = "content_extraction_failed"
                return result
            
            # Submit empty forms - stop if driver crashes
            for i, form in enumerate(result.forms):
                if not self._is_driver_alive():
                    logger.warning("Driver session lost during form submission, stopping")
                    result.crashed = True
                    result.crash_reason = "Driver session lost during interaction"
                    break
                
                if form.method.lower() in ['post', 'get']:
                    submission_result = self._submit_empty_form(form, i)
                    result.form_submission_results.append(submission_result)
                    
                    # If driver crashed during submission, stop submitting more forms
                    if not self._is_driver_alive():
                        logger.warning("Driver session lost after form submission, stopping")
                        result.crashed = True
                        result.crash_reason = "Driver session lost after form submission"
                        break
            
            # Click buttons (once each) - stop if driver crashes
            for i, button in enumerate(result.buttons):
                if not self._is_driver_alive():
                    logger.warning("Driver session lost during button clicking, stopping")
                    result.crashed = True
                    result.crash_reason = "Driver session lost during interaction"
                    break
                
                if button.is_clickable and button.is_visible:
                    click_result = self._click_button(button, i)
                    result.button_click_results.append(click_result)
                    
                    # If driver crashed during click, stop clicking more buttons
                    if not self._is_driver_alive():
                        logger.warning("Driver session lost after button click, stopping")
                        result.crashed = True
                        result.crash_reason = "Driver session lost after button click"
                        break
            
            # Compute DOM hash for state tracking (SPA support) - only if driver is alive
            if self._is_driver_alive():
                try:
                    dom_hash = self._compute_dom_hash(self.driver.page_source)
                except Exception as e:
                    logger.warning(f"Could not compute DOM hash: {e}")
                    dom_hash = ""
            else:
                dom_hash = ""
            state_key = f"{url}:{dom_hash}"
            
            if dom_hash and state_key not in self.visited_states:
                self.visited_states.add(state_key)
                
                # Add new links to queue if within limits
                if depth < self.max_depth and self._is_driver_alive():
                    for link in result.links:
                        if (link.is_clickable and 
                            link.absolute_url and 
                            self._is_same_domain(link.absolute_url) and
                            link.absolute_url not in self.visited_urls):
                            
                            self.page_queue.append((link.absolute_url, depth + 1))
            
            logger.info(f"Extracted {len(result.links)} links, {len(result.forms)} forms, "
                       f"{len(result.buttons)} buttons, {len(result.dropdowns)} dropdowns")
            
        except TimeoutException:
            # Check if driver is still alive despite timeout
            if self._is_driver_alive():
                # Page might have partially loaded, try to extract what we can
                logger.warning(f"Timeout loading page: {url}, attempting partial extraction")
                try:
                    base_url = self.driver.current_url
                    result.links = self._extract_links(base_url)
                    result.forms = self._extract_forms(base_url)
                    result.buttons = self._extract_buttons()
                    result.dropdowns = self._extract_dropdowns()
                    result.console_errors = self._capture_console_errors()
                    result.network_failures = self._detect_network_failures()
                    # Don't mark as crashed if we got some data
                    if len(result.links) > 0 or len(result.forms) > 0 or len(result.buttons) > 0:
                        result.crashed = False
                        result.crash_reason = None
                    else:
                        result.crashed = True
                        result.crash_reason = "timeout_no_content"
                except Exception as e2:
                    result.crashed = True
                    result.crash_reason = f"timeout_and_extraction_failed: {str(e2)}"
            else:
                result.crashed = True
                result.crash_reason = "timeout_and_driver_lost"
                logger.warning(f"Timeout loading page: {url}")
        except Exception as e:
            result.crashed = True
            result.crash_reason = str(e)
            logger.error(f"Error crawling page {url}: {e}")
        
        return result
    
    def crawl(self, start_url: str) -> List[CrawlResult]:
        """
        Start crawling from a given URL.
        
        Args:
            start_url: Starting URL for the crawl
            
        Returns:
            List of crawl results for each page visited
        """
        logger.info(f"Starting crawl from: {start_url}")
        
        self.base_domain = self._get_domain(start_url)
        self.visited_urls.clear()
        self.visited_states.clear()
        self.crawl_results.clear()
        self.page_queue.clear()
        
        # Initialize driver
        self._initialize_driver()
        
        try:
            # Add starting URL to queue
            self.page_queue.append((start_url, 0))
            
            # Process queue
            pages_crawled = 0
            while self.page_queue and pages_crawled < self.max_pages:
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
                
                # Mark as visited
                self.visited_urls.add(url)
                
                # Crawl the page
                result = self._crawl_page(url, depth)
                self.crawl_results.append(result)
                pages_crawled += 1
                
                logger.info(f"Progress: {pages_crawled}/{self.max_pages} pages crawled")
        
        finally:
            # Clean up
            if self.driver:
                self.driver.quit()
                self.driver = None
        
        logger.info(f"Crawl completed. Visited {len(self.crawl_results)} pages.")
        return self.crawl_results
    
    def get_results_json(self) -> str:
        """Get crawl results as JSON string."""
        def serialize_result(result: CrawlResult) -> dict:
            return {
                "url": result.url,
                "http_status": result.http_status,
                "crashed": result.crashed,
                "crash_reason": result.crash_reason,
                "links": [
                    {
                        "href": link.href,
                        "text": link.text,
                        "is_visible": link.is_visible,
                        "is_clickable": link.is_clickable,
                        "absolute_url": link.absolute_url
                    }
                    for link in result.links
                ],
                "forms": [
                    {
                        "action": form.action,
                        "method": form.method,
                        "id": form.id,
                        "absolute_action_url": form.absolute_action_url,
                        "inputs": [
                            {
                                "type": inp.type,
                                "name": inp.name,
                                "id": inp.id,
                                "required": inp.required,
                                "placeholder": inp.placeholder,
                                "pattern": inp.pattern
                            }
                            for inp in form.inputs
                        ]
                    }
                    for form in result.forms
                ],
                "buttons": [
                    {
                        "tag": btn.tag,
                        "text": btn.text,
                        "type": btn.type,
                        "id": btn.id,
                        "is_visible": btn.is_visible,
                        "is_clickable": btn.is_clickable,
                        "onclick": btn.onclick
                    }
                    for btn in result.buttons
                ],
                "dropdowns": [
                    {
                        "id": dd.id,
                        "name": dd.name,
                        "options": dd.options,
                        "is_visible": dd.is_visible
                    }
                    for dd in result.dropdowns
                ],
                "console_errors": [
                    {
                        "level": err.level,
                        "message": err.message,
                        "timestamp": err.timestamp,
                        "source": err.source
                    }
                    for err in result.console_errors
                ],
                "network_failures": [
                    {
                        "url": nf.url,
                        "status_code": nf.status_code,
                        "error_type": nf.error_type,
                        "timestamp": nf.timestamp
                    }
                    for nf in result.network_failures
                ],
                "form_submission_results": result.form_submission_results,
                "button_click_results": result.button_click_results
            }
        
        results_dict = [serialize_result(r) for r in self.crawl_results]
        return json.dumps(results_dict, indent=2)

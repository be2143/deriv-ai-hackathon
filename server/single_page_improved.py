"""
Single-Page Scraper – Scrape one URL only (no BFS, no link following).

Extracts UI elements with:
- Unique identifiers: id, hierarchical css_selector, xpath (e.g. ul#navigation > li > a[href*='login'])
- Attributes: id, class, data-testid, data-qa, etc.
- Container context: parent scope (header, footer, nav, main) for resilient locators
- Interactivity state: is_displayed, is_enabled, is_hidden (for explicit waits)
- Input validation: maxlength, required, pattern, min, max
- Iframe context: frame info when element is inside an iframe
"""

import json
import logging
import time
from typing import Any, Dict, List, Optional

from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")

# JavaScript to compute unique selector, xpath, container, and interactivity state for an element.
# Pass the element as arguments[0]. Returns object with unique_css_selector, unique_xpath, container, is_displayed, is_enabled, is_hidden.
_ELEMENT_ENRICHMENT_JS = """
var el = arguments[0];
function escapeId(id) {
  return id.replace(/\\\\/g, '\\\\\\\\').replace(/'/g, "\\\\'");
}
function getUniqueCss(el) {
  if (el.id && document.querySelectorAll('#' + CSS.escape(el.id)).length === 1)
    return '#' + CSS.escape(el.id);
  var path = [];
  var current = el;
  while (current && current.nodeType === 1) {
    var part = current.tagName.toLowerCase();
    if (current.id && document.querySelectorAll('#' + CSS.escape(current.id)).length === 1) {
      path.unshift('#' + CSS.escape(current.id));
      break;
    }
    if (current.className && typeof current.className === 'string') {
      var classes = current.className.trim().split(/\\s+/).filter(Boolean);
      if (classes.length) part += '.' + classes.map(function(c) { return CSS.escape(c); }).join('.');
    }
    var sibs = current.parentElement ? Array.prototype.filter.call(current.parentElement.children, function(n) { return n.tagName === current.tagName; }) : [];
    if (sibs.length > 1) part += ':nth-of-type(' + (Array.prototype.indexOf.call(sibs, current) + 1) + ')';
    path.unshift(part);
    current = current.parentElement;
    if (current && current.tagName === 'BODY') break;
  }
  return path.join(' > ');
}
function getUniqueXPath(el) {
  if (el.id && document.querySelectorAll('#' + CSS.escape(el.id)).length === 1)
    return "//*[@id='" + escapeId(el.id) + "']";
  var path = [];
  var current = el;
  while (current && current.nodeType === 1 && current !== document.body) {
    var tag = current.tagName.toLowerCase();
    var sibs = current.parentElement ? Array.prototype.filter.call(current.parentElement.children, function(n) { return n.tagName === current.tagName; }) : [];
    var idx = sibs.length > 1 ? Array.prototype.indexOf.call(sibs, current) + 1 : 1;
    path.unshift(tag + '[' + idx + ']');
    current = current.parentElement;
  }
  return '//' + path.join('/');
}
function getContainer(el) {
  var current = el.parentElement;
  while (current && current !== document.body) {
    var role = (current.getAttribute('role') || '').toLowerCase();
    var tag = current.tagName.toLowerCase();
    if (current.id || (current.className && current.className.trim()) || role === 'navigation' || role === 'banner' || role === 'contentinfo' || role === 'main' || tag === 'header' || tag === 'footer' || tag === 'nav' || tag === 'main') {
      var ctx = null;
      if (tag === 'header' || role === 'banner') ctx = 'header';
      else if (tag === 'footer' || role === 'contentinfo') ctx = 'footer';
      else if (tag === 'nav' || role === 'navigation') ctx = 'navigation';
      else if (tag === 'main' || role === 'main') ctx = 'main';
      return { tag: tag, id: current.id || null, class: current.className ? current.className.trim() : null, role: role || null, context_label: ctx };
    }
    current = current.parentElement;
  }
  return { tag: 'body', id: null, class: null, role: null, context_label: null };
}
var style = window.getComputedStyle(el);
var isDisplayed = el.offsetParent !== null && style.display !== 'none' && style.visibility !== 'hidden' && parseFloat(style.opacity) > 0;
var isHidden = style.display === 'none' || style.visibility === 'hidden' || (el.offsetParent === null && style.position !== 'fixed');
return {
  unique_css_selector: getUniqueCss(el),
  unique_xpath: getUniqueXPath(el),
  container: getContainer(el),
  is_displayed: isDisplayed,
  is_enabled: !el.disabled && el.getAttribute('aria-disabled') !== 'true',
  is_hidden: isHidden
};
"""


def _escape_css_string(s: str) -> str:
    """Escape a string for use inside a CSS attribute selector."""
    if not s:
        return s
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _xpath_by_text(tag: str, text: str, max_len: int = 50) -> Optional[str]:
    """Build an XPath that matches by visible text (for links/buttons)."""
    if not text or not text.strip():
        return None
    t = text.strip()[:max_len].replace("\\", "\\\\").replace('"', '\\"')
    if not t:
        return None
    return f'//{tag}[contains(normalize-space(), "{t}")]'


def _get_attributes_dict(el: WebElement) -> Dict[str, str]:
    """Build attributes dict (id, class, data-testid, etc.) for test generation."""
    attrs: Dict[str, str] = {}
    for attr in ("id", "class", "name", "type", "role", "aria-label", "data-testid", "data-test", "data-qa", "placeholder"):
        val = el.get_attribute(attr)
        if val is not None and str(val).strip():
            attrs[attr] = str(val).strip()
    return attrs


def _enrich_element_with_js(driver: webdriver.Chrome, el: WebElement, base_data: Dict) -> Dict:
    """Run JS enrichment (unique selector, container, interactivity) and merge into base_data."""
    try:
        result = driver.execute_script(_ELEMENT_ENRICHMENT_JS, el)
        if not result:
            return base_data
        base_data["css_selector"] = result.get("unique_css_selector") or base_data.get("css_selector")
        base_data["xpath"] = result.get("unique_xpath") or base_data.get("xpath")
        base_data["is_displayed"] = result.get("is_displayed", True)
        base_data["is_enabled"] = result.get("is_enabled", True)
        base_data["is_hidden"] = result.get("is_hidden", False)
        container = result.get("container")
        if container:
            base_data["container"] = {k: v for k, v in container.items() if v is not None}
        return base_data
    except Exception as e:
        logger.debug("JS enrichment failed: %s", e)
        base_data.setdefault("is_displayed", True)
        base_data.setdefault("is_enabled", True)
        base_data.setdefault("is_hidden", False)
        return base_data


def _selector_info(el: WebElement, tag: str) -> Dict:
    """
    Build selector-related fields: id, class, data-* attributes, and fallback
    css_selector / xpath (overridden by JS enrichment when available).
    """
    out: Dict = {}

    eid = el.get_attribute("id")
    if eid and eid.strip():
        out["id"] = eid.strip()

    cls = el.get_attribute("class")
    if cls and cls.strip():
        out["class"] = cls.strip()
        out["classes"] = [c.strip() for c in cls.split() if c.strip()]

    for attr, key in [
        ("data-testid", "data_testid"),
        ("data-test", "data_test"),
        ("data-qa", "data_qa"),
    ]:
        val = el.get_attribute(attr)
        if val and val.strip():
            out[key] = val.strip()

    name = el.get_attribute("name")
    if name and name.strip():
        out["name"] = name.strip()

    role = el.get_attribute("role")
    if role and role.strip():
        out["role"] = role.strip()

    aria_label = el.get_attribute("aria-label")
    if aria_label and aria_label.strip():
        out["aria_label"] = aria_label.strip()

    out["attributes"] = _get_attributes_dict(el)

    # Fallback selectors (JS will replace with unique when available)
    if eid and eid.strip():
        out["css_selector"] = f"#{_escape_css_string(eid.strip())}"
        out["xpath"] = f"//*[@id='{eid.strip()}']"
    else:
        dtid = el.get_attribute("data-testid")
        if dtid and dtid.strip():
            out["css_selector"] = f'[data-testid="{_escape_css_string(dtid.strip())}"]'
            out["xpath"] = f"//*[@data-testid='{dtid.strip()}']"
        elif name and name.strip() and tag in ("input", "select", "textarea", "button"):
            out["css_selector"] = f'{tag}[name="{_escape_css_string(name.strip())}"]'
            out["xpath"] = f"//{tag}[@name='{name.strip()}']"
        elif cls and cls.strip():
            first_class = cls.split()[0].strip()
            out["css_selector"] = f"{tag}.{_escape_css_string(first_class)}"
            out["xpath"] = f"//{tag}"
        else:
            out["css_selector"] = tag
            out["xpath"] = f"//{tag}"

    return out


class SinglePageScraper:
    """
    Scrapes a single page only: loads the given URL and extracts UI elements
    with selectors suitable for automatic test case generation.
    """

    def __init__(
        self,
        headless: bool = True,
        wait_time: float = 2.0,
        page_load_timeout: int = 30,
    ):
        self.headless = headless
        self.wait_time = wait_time
        self.page_load_timeout = page_load_timeout
        self.driver: Optional[webdriver.Chrome] = None

    def _init_driver(self) -> None:
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

    def _wait_ready(self, timeout: int = 10) -> None:
        try:
            WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            WebDriverWait(self.driver, timeout).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
            time.sleep(max(0, self.wait_time))
        except TimeoutException:
            logger.warning("Page load timeout, continuing anyway")
            time.sleep(max(0, self.wait_time))
        except Exception as e:
            logger.debug("Wait ready error: %s", e)
            time.sleep(max(0, self.wait_time))

    def _dismiss_modals(self) -> None:
        try:
            selectors = [
                "//button[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'accept')]",
                "//button[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'allow')]",
                "//button[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'agree')]",
                "//button[@class*='cookie']",
                "//button[@class*='consent']",
            ]
            for selector in selectors:
                try:
                    buttons = self.driver.find_elements(By.XPATH, selector)
                    for btn in buttons[:3]:
                        try:
                            if btn.is_displayed():
                                btn.click()
                                time.sleep(1.0)
                                break
                        except Exception:
                            continue
                except Exception:
                    continue
        except Exception as e:
            logger.debug("Error dismissing modals: %s", e)

    def _extract_input_data(self, input_el: WebElement) -> Optional[Dict]:
        try:
            tag = input_el.tag_name.lower()
            input_type = (input_el.get_attribute("type") or "text").lower()
            name = input_el.get_attribute("name") or ""
            input_id = input_el.get_attribute("id") or ""

            input_data: Dict = {
                "tag": tag,
                "role": "input" if tag == "input" else tag,
                "type": input_type,
            }

            input_data.update(_selector_info(input_el, tag))

            if input_id:
                input_data["id"] = input_id
            if name:
                input_data["name"] = name

            label_text = None
            if input_id:
                try:
                    label_el = self.driver.find_element(By.CSS_SELECTOR, f"label[for='{input_id}']")
                    label_text = label_el.text.strip()
                except Exception:
                    pass
            if not label_text:
                try:
                    parent = input_el.find_element(By.XPATH, "./..")
                    if parent.tag_name.lower() == "label":
                        label_text = parent.text.strip()
                except Exception:
                    pass
            if not label_text:
                label_text = (
                    input_el.get_attribute("aria-label")
                    or input_el.get_attribute("placeholder")
                )
            input_data["label"] = label_text or name or input_id or None

            if input_el.get_attribute("placeholder"):
                input_data["placeholder"] = input_el.get_attribute("placeholder")
            if input_el.get_attribute("required"):
                input_data["required"] = True
            # Input validation metadata for test generation
            for attr in ("maxlength", "min", "max", "pattern", "step"):
                val = input_el.get_attribute(attr)
                if val is not None and str(val).strip():
                    input_data[attr] = str(val).strip()

            if tag == "select":
                options = []
                for option in input_el.find_elements(By.TAG_NAME, "option"):
                    options.append({
                        "value": option.get_attribute("value") or "",
                        "text": option.text.strip(),
                    })
                if options:
                    input_data["options"] = options

            input_data = _enrich_element_with_js(self.driver, input_el, input_data)
            return input_data
        except Exception as e:
            logger.debug("Error extracting input data: %s", e)
            return None

    def _set_frame_on_element(self, data: Dict, frame_info: Optional[Dict]) -> None:
        """Set frame context on element (null for main content, dict when inside iframe)."""
        data["frame"] = frame_info
        # Hint for test generation: explicit wait or switch_to.frame may be needed
        if frame_info or data.get("is_hidden"):
            data["requires_wait"] = True

    def _extract_elements(self, frame_info: Optional[Dict] = None) -> Dict:
        try:
            if frame_info is None:
                self._wait_ready()
                self._dismiss_modals()

            title = self.driver.title
            current_url = self.driver.current_url

            # Headings
            headings: List[Dict] = []
            for tag in ["h1", "h2", "h3", "h4", "h5"]:
                try:
                    for heading in self.driver.find_elements(By.TAG_NAME, tag):
                        try:
                            text = heading.text.strip()
                            if text:
                                h = {"level": int(tag[1]), "text": text}
                                h.update(_selector_info(heading, tag))
                                h = _enrich_element_with_js(self.driver, heading, h)
                                self._set_frame_on_element(h, frame_info)
                                headings.append(h)
                        except Exception:
                            continue
                except Exception:
                    continue

            # Forms
            forms: List[Dict] = []
            for form_el in self.driver.find_elements(By.TAG_NAME, "form"):
                try:
                    form_data: Dict = {
                        "action": form_el.get_attribute("action") or "",
                        "method": (form_el.get_attribute("method") or "get").lower(),
                        "elements": [],
                    }
                    form_data.update(_selector_info(form_el, "form"))
                    form_data = _enrich_element_with_js(self.driver, form_el, form_data)
                    self._set_frame_on_element(form_data, frame_info)
                    if form_el.get_attribute("id"):
                        form_data["id"] = form_el.get_attribute("id")
                    try:
                        for t in ["legend", "h1", "h2", "h3"]:
                            try:
                                label_el = form_el.find_element(By.TAG_NAME, t)
                                if label_el:
                                    form_data["label"] = label_el.text.strip()
                                    break
                            except Exception:
                                continue
                    except Exception:
                        pass

                    for input_el in form_el.find_elements(
                        By.XPATH, ".//input | .//select | .//textarea | .//button"
                    ):
                        try:
                            itype = input_el.get_attribute("type") or "text"
                            if itype in ("hidden", "submit", "button"):
                                continue
                            if input_el.tag_name.lower() == "button":
                                continue
                            data = self._extract_input_data(input_el)
                            if data:
                                self._set_frame_on_element(data, frame_info)
                                form_data["elements"].append(data)
                        except Exception:
                            continue

                    if form_data["elements"]:
                        forms.append(form_data)
                except Exception:
                    continue

            # Links
            navigation: List[Dict] = []
            footer: List[Dict] = []
            main_links: List[Dict] = []

            for link in self.driver.find_elements(By.TAG_NAME, "a"):
                try:
                    href = link.get_attribute("href")
                    if not href or href.startswith("javascript:") or href.startswith("mailto:") or href.startswith("#"):
                        continue
                    text = link.text.strip()
                    link_data: Dict = {
                        "tag": "a",
                        "role": "link",
                        "href": href,
                        "text": text or None,
                        "label": text or None,
                        "expected_navigation": href,  # For test: expected URL after click
                    }
                    link_data.update(_selector_info(link, "a"))
                    xpath_text = _xpath_by_text("a", text)
                    if xpath_text:
                        link_data["xpath_by_text"] = xpath_text
                    link_data = _enrich_element_with_js(self.driver, link, link_data)
                    self._set_frame_on_element(link_data, frame_info)

                    parent_tag = None
                    try:
                        parent = link.find_element(By.XPATH, "./..")
                        parent_tag = parent.tag_name.lower() if parent else None
                    except Exception:
                        pass
                    if parent_tag in ("nav", "header"):
                        navigation.append(link_data)
                    elif parent_tag == "footer":
                        footer.append(link_data)
                    else:
                        try:
                            parent = link.find_element(By.XPATH, "./..")
                            parent_role = parent.get_attribute("role")
                            if parent_role == "navigation":
                                navigation.append(link_data)
                            elif parent_role == "contentinfo":
                                footer.append(link_data)
                            else:
                                main_links.append(link_data)
                        except Exception:
                            main_links.append(link_data)
                except Exception:
                    continue

            # Buttons
            buttons: List[Dict] = []
            for button in self.driver.find_elements(
                By.XPATH,
                "//button | //input[@type='button'] | //input[@type='submit'] | //*[@role='button']",
            ):
                try:
                    button_data: Dict = {
                        "tag": button.tag_name.lower(),
                        "role": "button",
                        "text": button.text.strip() or None,
                        "label": button.text.strip() or None,
                    }
                    button_data.update(_selector_info(button, button.tag_name.lower()))
                    if button.get_attribute("type"):
                        button_data["type"] = button.get_attribute("type")
                    if button.get_attribute("onclick"):
                        button_data["onclick"] = True
                    btn_text = button.text.strip() if button.text else ""
                    xpath_btn = _xpath_by_text(button.tag_name.lower(), btn_text)
                    if xpath_btn:
                        button_data["xpath_by_text"] = xpath_btn
                    button_data = _enrich_element_with_js(self.driver, button, button_data)
                    self._set_frame_on_element(button_data, frame_info)
                    buttons.append(button_data)
                except Exception:
                    continue

            # Standalone inputs
            inputs: List[Dict] = []
            for input_el in self.driver.find_elements(By.TAG_NAME, "input"):
                try:
                    try:
                        parent = input_el.find_element(By.XPATH, "./..")
                        if parent.tag_name.lower() == "form":
                            continue
                    except Exception:
                        pass
                    itype = input_el.get_attribute("type") or "text"
                    if itype in ("hidden", "submit", "button"):
                        continue
                    data = self._extract_input_data(input_el)
                    if data:
                        self._set_frame_on_element(data, frame_info)
                        inputs.append(data)
                except Exception:
                    continue

            elements = buttons + inputs + main_links

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
            logger.error("Error extracting elements: %s", e, exc_info=True)
            return {
                "page_url": self.driver.current_url if self.driver else "",
                "title": self.driver.title if self.driver else "",
                "headings": [],
                "forms": [],
                "elements": [],
                "navigation": [],
                "footer": [],
            }

    def _merge_page_data(self, into: Dict, from_frame: Dict) -> None:
        """Merge frame page data into main page data (elements, forms, navigation, footer, headings)."""
        into.setdefault("elements", []).extend(from_frame.get("elements", []))
        into.setdefault("forms", []).extend(from_frame.get("forms", []))
        into.setdefault("navigation", []).extend(from_frame.get("navigation", []))
        into.setdefault("footer", []).extend(from_frame.get("footer", []))
        into.setdefault("headings", []).extend(from_frame.get("headings", []))

    def scrape(self, url: str, include_iframes: bool = True) -> Dict:
        """
        Load the given URL (no following links) and return extracted page data
        with selectors for test generation. Optionally extracts elements inside iframes
        and tags them with frame context (so tests can switch_to.frame before interacting).
        """
        logger.info("Single-page scrape: %s", url)
        self._init_driver()
        try:
            self.driver.set_page_load_timeout(self.page_load_timeout)
            self.driver.get(url)
            page_data = self._extract_elements(frame_info=None)

            if include_iframes:
                try:
                    iframes = self.driver.find_elements(By.TAG_NAME, "iframe")
                    for i, iframe_el in enumerate(iframes):
                        try:
                            frame_info: Dict[str, Any] = {
                                "index": i,
                                "name": iframe_el.get_attribute("name") or None,
                                "id": iframe_el.get_attribute("id") or None,
                                "src": iframe_el.get_attribute("src") or None,
                            }
                            self.driver.switch_to.frame(iframe_el)
                            frame_page = self._extract_elements(frame_info=frame_info)
                            self._merge_page_data(page_data, frame_page)
                            logger.info("Extracted %s elements from iframe %s", i, frame_info.get("src") or frame_info.get("id"))
                        except Exception as e:
                            logger.debug("Error extracting iframe %s: %s", i, e)
                        finally:
                            self.driver.switch_to.default_content()
                except Exception as e:
                    logger.debug("Error during iframe extraction: %s", e)

            total = (
                len(page_data.get("elements", []))
                + sum(len(f.get("elements", [])) for f in page_data.get("forms", []))
                + len(page_data.get("navigation", []))
                + len(page_data.get("footer", []))
            )
            logger.info("Extracted %s elements from %s", total, url)
            return {
                "page": page_data,
                "summary": {
                    "total_elements": total,
                    "forms": len(page_data.get("forms", [])),
                    "navigation_links": len(page_data.get("navigation", [])),
                    "footer_links": len(page_data.get("footer", [])),
                },
            }
        finally:
            if self.driver:
                try:
                    self.driver.quit()
                except Exception:
                    pass
                self.driver = None

    def get_results_json(self, data: Dict) -> str:
        return json.dumps(data, indent=2)


def main():
    import sys
    from pathlib import Path

    if len(sys.argv) < 2:
        print("Usage: python single_page_scraper.py <url> [--output file.json]")
        sys.exit(1)

    url = sys.argv[1]
    output = None
    if "--output" in sys.argv:
        i = sys.argv.index("--output")
        if i + 1 < len(sys.argv):
            output = sys.argv[i + 1]

    scraper = SinglePageScraper(headless=True, wait_time=2.0)
    result = scraper.scrape(url)

    if output:
        out_path = Path(output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(scraper.get_results_json(result))
        print("Wrote", out_path)
    else:
        print(scraper.get_results_json(result))


if __name__ == "__main__":
    main()

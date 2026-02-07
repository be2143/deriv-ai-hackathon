"""
Single-Page Scraper – Scrape one URL only (no BFS, no link following).

Extracts UI elements with unique selectors, interactivity state, container context,
input validation metadata, and iframe awareness for robust test generation.
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

# JavaScript to compute unique selectors, container, and state for an element.
# Receives one DOM element as arguments[0]. Returns an object.
_ELEMENT_METADATA_JS = """
(function(el) {
    if (!el || !el.tagName) return null;
    function escapeCssId(id) {
        return id.replace(/\\\\/g, '\\\\\\\\').replace(/([#;\\[\\]\\,.~:>+])/g, '\\\\$1');
    }
    function getUniqueCssPath(node) {
        var parts = [];
        var n = node;
        while (n && n.nodeType === 1) {
            var part = n.tagName.toLowerCase();
            if (n.id && /^[a-zA-Z][\\w-]*$/.test(n.id) && !/[\\s.]/.test(n.id)) {
                parts.unshift('#' + escapeCssId(n.id));
                break;
            }
            if (n.className && typeof n.className === 'string') {
                var classes = n.className.trim().split(/\\s+/).filter(Boolean);
                if (classes.length > 0)
                    part += '.' + classes.slice(0, 2).map(function(c){ return escapeCssId(c); }).join('.');
            }
            var parent = n.parentElement;
            if (parent) {
                var siblings = Array.prototype.filter.call(parent.children, function(c) {
                    return c.tagName === n.tagName && (n.className === c.className || (n.className && c.className && n.className.trim() === c.className.trim()));
                });
                if (siblings.length > 1) {
                    var idx = siblings.indexOf(n) + 1;
                    part += ':nth-of-type(' + idx + ')';
                }
            }
            parts.unshift(part);
            n = parent;
            if (n && n.id && /^[a-zA-Z][\\w-]*$/.test(n.id)) break;
        }
        return parts.join(' > ');
    }
    function getUniqueXPath(node) {
        if (node.id && /^[a-zA-Z][\\w-]*$/.test(node.id))
            return "//*[@id='" + node.id.replace(/'/g, "', \"'\", '") + "']";
        var tag = node.tagName.toLowerCase();
        var text = (node.textContent || '').trim().substring(0, 50);
        var href = node.getAttribute('href');
        if (href) href = href.replace(/'/g, "', \"'\", '");
        if (text && text.length > 0 && text.length < 100)
            return "//" + tag + "[contains(normalize-space(text()), '" + text.replace(/'/g, "', \"'\", '") + "')]";
        if (href)
            return "//" + tag + "[@href='" + href + "']";
        if (node.name && (tag === 'input' || tag === 'select' || tag === 'textarea'))
            return "//" + tag + "[@name='" + (node.name || '').replace(/'/g, "', \"'\", '") + "']";
        var dataTestId = node.getAttribute('data-testid');
        if (dataTestId)
            return "//*[@data-testid='" + dataTestId.replace(/'/g, "', \"'\", '") + "']";
        return "//" + tag;
    }
    function getContainer(node) {
        var n = node.parentElement;
        while (n && n.nodeType === 1) {
            var tag = n.tagName ? n.tagName.toLowerCase() : '';
            var role = (n.getAttribute('role') || '').toLowerCase();
            if (tag === 'header' || role === 'banner') return { semantic: 'header', id: n.id || null, class: n.className && n.className.trim() ? n.className.trim() : null };
            if (tag === 'footer' || role === 'contentinfo') return { semantic: 'footer', id: n.id || null, class: n.className && n.className.trim() ? n.className.trim() : null };
            if (tag === 'nav' || role === 'navigation') return { semantic: 'nav', id: n.id || null, class: n.className && n.className.trim() ? n.className.trim() : null };
            if (tag === 'main' || role === 'main') return { semantic: 'main', id: n.id || null, class: n.className && n.className.trim() ? n.className.trim() : null };
            if (n.id) return { semantic: null, id: n.id, class: n.className && n.className.trim() ? n.className.trim() : null };
            n = n.parentElement;
        }
        return { semantic: null, id: null, class: null };
    }
    function getIframeInfo(node) {
        var win = node.ownerDocument && node.ownerDocument.defaultView;
        if (!win || win === window) return { in_iframe: false, frame_index: null, frame_selector: null };
        var frames = window.frames;
        for (var i = 0; i < frames.length; i++) {
            try {
                if (frames[i] === win) {
                    var iframe = document.querySelectorAll('iframe')[i];
                    var sel = iframe && iframe.id ? '#' + escapeCssId(iframe.id) : (iframe && iframe.name ? 'iframe[name="' + iframe.name + '"]' : 'iframe:nth-of-type(' + (i + 1) + ')');
                    return { in_iframe: true, frame_index: i, frame_selector: sel };
                }
            } catch (e) {}
        }
        return { in_iframe: true, frame_index: null, frame_selector: null };
    }
    var style = window.getComputedStyle ? window.getComputedStyle(el) : null;
    var isVisible = style && style.display !== 'none' && style.visibility !== 'hidden' && parseFloat(style.opacity) !== 0;
    var rect = el.getBoundingClientRect && el.getBoundingClientRect();
    var hasSize = !rect || (rect.width > 0 || rect.height > 0);
    var is_displayed = isVisible && hasSize;
    var is_enabled = !el.disabled && el.getAttribute('aria-disabled') !== 'true';
    var iframeInfo = getIframeInfo(el);
    return {
        css_selector: getUniqueCssPath(el),
        xpath: getUniqueXPath(el),
        container: getContainer(el),
        is_displayed: !!is_displayed,
        is_enabled: !!is_enabled,
        is_hidden: !is_displayed,
        might_need_wait: !!iframeInfo.in_iframe,
        iframe: iframeInfo
    };
})(arguments[0]);
"""


def _escape_css_string(s: str) -> str:
    """Escape a string for use inside a CSS attribute selector."""
    if not s:
        return s
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _get_element_metadata(driver: webdriver.Chrome, el: WebElement) -> Optional[Dict]:
    """Get unique selectors, container, and state for an element via JS."""
    try:
        result = driver.execute_script(_ELEMENT_METADATA_JS, el)
        return result if isinstance(result, dict) else None
    except Exception as e:
        logger.debug("Element metadata JS failed: %s", e)
        return None


def _selector_info(el: WebElement, tag: str) -> Dict:
    """Build selector-related and attributes fields for an element."""
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

    # Explicit attributes object for test generation
    attrs: Dict[str, str] = {}
    if eid and eid.strip():
        attrs["id"] = eid.strip()
    if cls and cls.strip():
        attrs["class"] = cls.strip()
    dtid = el.get_attribute("data-testid")
    if dtid and dtid.strip():
        attrs["data-testid"] = dtid.strip()
    if attrs:
        out["attributes"] = attrs

    # Fallback selectors (overwritten by JS if available)
    if eid and eid.strip():
        out["css_selector"] = f"#{_escape_css_string(eid.strip())}"
    else:
        dtid = el.get_attribute("data-testid")
        if dtid and dtid.strip():
            out["css_selector"] = f'[data-testid="{_escape_css_string(dtid.strip())}"]'
        elif name and name.strip() and tag in ("input", "select", "textarea", "button"):
            out["css_selector"] = f'{tag}[name="{_escape_css_string(name.strip())}"]'
        elif cls and cls.strip():
            first = cls.split()[0].strip()
            if first:
                out["css_selector"] = f"{tag}.{_escape_css_string(first)}"
        else:
            out["css_selector"] = tag

    xpath = f"//{tag}"
    if eid and eid.strip():
        xpath = f"//{tag}[@id='{eid.strip()}']"
    elif name and name.strip() and tag in ("input", "select", "textarea", "button"):
        xpath = f"//{tag}[@name='{name.strip()}']"
    else:
        if dtid and dtid.strip():
            xpath = f"//*[@data-testid='{dtid.strip()}']"
    out["xpath"] = xpath

    return out


def _enrich_element(
    driver: webdriver.Chrome,
    el: WebElement,
    base: Dict,
    tag: str,
    element_id: str,
) -> Dict:
    """Merge base element data with JS-derived metadata (unique selectors, state, container, iframe)."""
    base["element_id"] = element_id
    meta = _get_element_metadata(driver, el)
    if meta:
        base["css_selector"] = meta.get("css_selector") or base.get("css_selector", tag)
        base["xpath"] = meta.get("xpath") or base.get("xpath", "//" + tag)
        base["is_displayed"] = meta.get("is_displayed", True)
        base["is_enabled"] = meta.get("is_enabled", True)
        base["is_hidden"] = meta.get("is_hidden", False)
        base["might_need_wait"] = meta.get("might_need_wait", False)
        base["container"] = meta.get("container") or {}
        if meta.get("iframe"):
            base["iframe"] = meta["iframe"]
    else:
        base.setdefault("is_displayed", True)
        base.setdefault("is_enabled", True)
        base.setdefault("is_hidden", False)
        base.setdefault("might_need_wait", False)
        base.setdefault("container", {})
    return base


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
            ml = input_el.get_attribute("maxlength")
            if ml is not None:
                try:
                    input_data["maxlength"] = int(ml)
                except ValueError:
                    input_data["maxlength"] = ml
            pat = input_el.get_attribute("pattern")
            if pat and pat.strip():
                input_data["pattern"] = pat.strip()
            min_attr = input_el.get_attribute("min")
            if min_attr is not None and min_attr != "":
                input_data["min"] = min_attr
            max_attr = input_el.get_attribute("max")
            if max_attr is not None and max_attr != "":
                input_data["max"] = max_attr
            step = input_el.get_attribute("step")
            if step is not None and step != "":
                input_data["step"] = step

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
            logger.debug("Error extracting input data: %s", e)
            return None

    def _extract_elements(self) -> Dict:
        try:
            self._wait_ready()
            self._dismiss_modals()

            title = self.driver.title
            current_url = self.driver.current_url

            _next_id = 0

            def next_el_id() -> str:
                nonlocal _next_id
                _next_id += 1
                return "el_%d" % _next_id

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
                                _enrich_element(self.driver, heading, h, tag, next_el_id())
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
                    _enrich_element(self.driver, form_el, form_data, "form", next_el_id())
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
                                _enrich_element(
                                    self.driver,
                                    input_el,
                                    data,
                                    input_el.tag_name.lower(),
                                    next_el_id(),
                                )
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
                        "expected_after_click": {"url": href},
                    }
                    link_data.update(_selector_info(link, "a"))

                    parent_tag = None
                    parent_role = None
                    try:
                        parent = link.find_element(By.XPATH, "./..")
                        parent_tag = parent.tag_name.lower() if parent else None
                        parent_role = parent.get_attribute("role") if parent else None
                    except Exception:
                        pass

                    if parent_tag in ("nav", "header"):
                        target_list, semantic = navigation, "header"
                    elif parent_tag == "footer":
                        target_list, semantic = footer, "footer"
                    elif parent_role == "navigation":
                        target_list, semantic = navigation, "nav"
                    elif parent_role == "contentinfo":
                        target_list, semantic = footer, "footer"
                    else:
                        target_list, semantic = main_links, None

                    _enrich_element(self.driver, link, link_data, "a", next_el_id())
                    if semantic:
                        link_data.setdefault("container", {})["semantic"] = semantic
                    target_list.append(link_data)
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
                    _enrich_element(self.driver, button, button_data, button.tag_name.lower(), next_el_id())
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
                        _enrich_element(
                            self.driver,
                            input_el,
                            data,
                            input_el.tag_name.lower(),
                            next_el_id(),
                        )
                        inputs.append(data)
                except Exception:
                    continue

            elements = buttons + inputs + main_links

            # Optional: extract elements inside iframes (with frame context for switch_to.frame)
            iframe_elements: List[Dict] = []
            try:
                iframes = self.driver.find_elements(By.TAG_NAME, "iframe")
                for idx, ifr in enumerate(iframes):
                    try:
                        frame_selector = None
                        if ifr.get_attribute("id"):
                            frame_selector = "#" + _escape_css_string(ifr.get_attribute("id").strip())
                        elif ifr.get_attribute("name"):
                            frame_selector = 'iframe[name="' + ifr.get_attribute("name").strip() + '"]'
                        else:
                            frame_selector = "iframe:nth-of-type(%d)" % (idx + 1)
                        self.driver.switch_to.frame(ifr)
                        # Links in iframe
                        for link in self.driver.find_elements(By.TAG_NAME, "a"):
                            try:
                                href = link.get_attribute("href")
                                if not href or href.startswith("javascript:") or href.startswith("mailto:") or href.startswith("#"):
                                    continue
                                link_data = {
                                    "tag": "a", "role": "link", "href": href,
                                    "text": link.text.strip() or None, "label": link.text.strip() or None,
                                }
                                link_data.update(_selector_info(link, "a"))
                                _enrich_element(self.driver, link, link_data, "a", next_el_id())
                                link_data["iframe"] = {"in_iframe": True, "frame_index": idx, "frame_selector": frame_selector}
                                iframe_elements.append(link_data)
                            except Exception:
                                continue
                        # Buttons in iframe
                        for button in self.driver.find_elements(By.XPATH, "//button | //input[@type='button'] | //input[@type='submit'] | //*[@role='button']"):
                            try:
                                btn_data = {"tag": button.tag_name.lower(), "role": "button", "text": button.text.strip() or None, "label": button.text.strip() or None}
                                btn_data.update(_selector_info(button, button.tag_name.lower()))
                                _enrich_element(self.driver, button, btn_data, button.tag_name.lower(), next_el_id())
                                btn_data["iframe"] = {"in_iframe": True, "frame_index": idx, "frame_selector": frame_selector}
                                iframe_elements.append(btn_data)
                            except Exception:
                                continue
                        # Inputs in iframe
                        for input_el in self.driver.find_elements(By.TAG_NAME, "input"):
                            try:
                                itype = input_el.get_attribute("type") or "text"
                                if itype in ("hidden", "submit", "button"):
                                    continue
                                data = self._extract_input_data(input_el)
                                if data:
                                    _enrich_element(self.driver, input_el, data, input_el.tag_name.lower(), next_el_id())
                                    data["iframe"] = {"in_iframe": True, "frame_index": idx, "frame_selector": frame_selector}
                                    iframe_elements.append(data)
                            except Exception:
                                continue
                    except Exception as e:
                        logger.debug("Error extracting from iframe %s: %s", idx, e)
                    finally:
                        self.driver.switch_to.default_content()
            except Exception as e:
                logger.debug("Iframe extraction failed: %s", e)

            return {
                "page_url": current_url,
                "title": title,
                "headings": headings,
                "forms": forms,
                "elements": elements,
                "navigation": navigation,
                "footer": footer,
                "iframe_elements": iframe_elements,
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
                "iframe_elements": [],
            }

    def scrape(self, url: str) -> Dict:
        """
        Load the given URL (no following links) and return extracted page data
        with selectors for test generation.
        """
        logger.info("Single-page scrape: %s", url)
        self._init_driver()
        try:
            self.driver.set_page_load_timeout(self.page_load_timeout)
            self.driver.get(url)
            page_data = self._extract_elements()
            total = (
                len(page_data.get("elements", []))
                + sum(len(f.get("elements", [])) for f in page_data.get("forms", []))
                + len(page_data.get("navigation", []))
                + len(page_data.get("footer", []))
                + len(page_data.get("iframe_elements", []))
            )
            logger.info("Extracted %s elements from %s", total, url)
            return {
                "page": page_data,
                "summary": {
                    "total_elements": total,
                    "forms": len(page_data.get("forms", [])),
                    "navigation_links": len(page_data.get("navigation", [])),
                    "footer_links": len(page_data.get("footer", [])),
                    "iframe_elements": len(page_data.get("iframe_elements", [])),
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

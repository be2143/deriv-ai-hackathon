"""
UI Model Builder - Structured UI Abstraction Layer

Converts raw Selenium DOM into structured UI representation
optimized for LLM-driven test generation.

Core approach: a single JavaScript execution extracts the entire
UI model from inside the browser in one shot. No element-by-element
Selenium round-trips, no broken deduplication.
"""

import json
import logging
import time
from typing import Dict, List, Optional

from selenium import webdriver
from selenium.webdriver.common.by import By

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# The entire extraction runs inside the browser as one JS blob.
# It returns a JSON-serialisable dict with the full page model.
# ---------------------------------------------------------------------------

EXTRACT_UI_JS = """
(function() {
    // ---- helpers ----

    function isVisible(el) {
        if (!el) return false;
        try {
            var style = window.getComputedStyle(el);
            if (style.display === 'none') return false;
            if (style.visibility === 'hidden') return false;
            if (parseFloat(style.opacity) === 0) return false;
            var rect = el.getBoundingClientRect();
            // More lenient: only filter out if truly zero-sized AND not in viewport
            if (rect.width === 0 && rect.height === 0 && rect.top === 0 && rect.left === 0) {
                // Might be hidden, but check parent
                var parent = el.parentElement;
                if (parent) {
                    var parentStyle = window.getComputedStyle(parent);
                    if (parentStyle.display === 'none' || parentStyle.visibility === 'hidden') return false;
                }
                return false;
            }
            return true;
        } catch(e) {
            // If we can't check, assume visible (better to include than exclude)
            return true;
        }
    }

    function isEnabled(el) {
        if (el.disabled) return false;
        if (el.getAttribute('aria-disabled') === 'true') return false;
        return true;
    }

    function normalizeRole(el) {
        var role = el.getAttribute('role');
        if (role) return role.toLowerCase();
        var tag = el.tagName.toLowerCase();
        if (tag === 'button') return 'button';
        if (tag === 'a') return 'link';
        if (tag === 'select') return 'dropdown';
        if (tag === 'textarea') return 'textarea';
        if (tag === 'input') {
            var t = (el.getAttribute('type') || 'text').toLowerCase();
            if (['text','email','tel','url','search','password','number','date','time','datetime-local','month','week','color','range'].includes(t)) return 'input';
            if (t === 'checkbox') return 'checkbox';
            if (t === 'radio') return 'radio';
            if (['button','submit','reset'].includes(t)) return 'button';
            if (t === 'file') return 'file';
            if (t === 'hidden') return 'hidden';
            return 'input';
        }
        if (el.getAttribute('onclick') || el.getAttribute('tabindex')) return 'button';
        return 'unknown';
    }

    function resolveLabel(el) {
        var id = el.id;
        // 1. <label for>
        if (id) {
            try {
                var lbl = document.querySelector('label[for="' + id.replace(/"/g, '\\"') + '"]');
                if (lbl) { var t = lbl.innerText.trim(); if (t) return t; }
            } catch(e) {}
        }
        // 2. ancestor <label>
        var parent = el.closest('label');
        if (parent) { var t = parent.innerText.trim(); if (t && t.length < 200) return t; }
        // 3. aria-labelledby
        var alb = el.getAttribute('aria-labelledby');
        if (alb) {
            var parts = alb.split(/\\s+/).map(function(rid) {
                var r = document.getElementById(rid);
                return r ? r.innerText.trim() : '';
            }).filter(Boolean);
            if (parts.length) return parts.join(' ');
        }
        // 4. aria-label
        var al = el.getAttribute('aria-label');
        if (al && al.trim()) return al.trim();
        // 5. title attribute
        var title = el.getAttribute('title');
        if (title && title.trim()) return title.trim();
        // 6. placeholder
        var ph = el.getAttribute('placeholder');
        if (ph && ph.trim().length > 1) return ph.trim();
        // 7. preceding sibling text
        var prev = el.previousElementSibling;
        if (prev && ['LABEL','SPAN','DIV','P','B','STRONG','EM'].includes(prev.tagName)) {
            var t = prev.innerText.trim();
            if (t && t.length > 0 && t.length < 120) return t;
        }
        // 8. nearest heading in same container
        var container = el.closest('form, fieldset, section, article, div');
        if (container) {
            var hdg = container.querySelector('h1,h2,h3,h4,h5,legend');
            if (hdg) { var t = hdg.innerText.trim(); if (t) return t; }
        }
        // fallbacks
        if (el.name && el.name.length > 1) return el.name.replace(/[_-]/g, ' ');
        if (id && id.length > 1) return id.replace(/[_-]/g, ' ');
        var dtid = el.getAttribute('data-testid');
        if (dtid) return dtid.replace(/[_-]/g, ' ');
        return null;
    }

    function getTextContent(el) {
        // For buttons/links return visible text; for inputs return value
        var tag = el.tagName.toLowerCase();
        if (tag === 'input') return el.value || null;
        if (tag === 'select') {
            var opt = el.options[el.selectedIndex];
            return opt ? opt.text : null;
        }
        var t = el.innerText || el.textContent || '';
        t = t.trim().replace(/\\s+/g, ' ');
        return t.length > 0 && t.length < 500 ? t : null;
    }

    function getSelectOptions(el) {
        if (el.tagName.toLowerCase() !== 'select') return null;
        return Array.from(el.options).map(function(o) {
            return { value: o.value, text: o.text.trim() };
        });
    }

    function isInRegion(el, regionSelector) {
        return !!el.closest(regionSelector);
    }

    function isInModal(el) {
        try {
            return !!(el.closest('[role="dialog"]') ||
                      el.closest('.modal') ||
                      el.closest('.overlay') ||
                      el.closest('.popup') ||
                      el.closest('[class*="cookie"]') ||
                      el.closest('[id*="cookie"]') ||
                      el.closest('[class*="consent"]'));
        } catch(e) {
            return false;
        }
    }

    function isInNav(el) {
        try {
            return !!(el.closest('nav') ||
                      el.closest('[role="navigation"]') ||
                      el.closest('header'));
        } catch(e) {
            return false;
        }
    }

    function isInFooter(el) {
        try {
            return !!(el.closest('footer') ||
                      el.closest('[role="contentinfo"]'));
        } catch(e) {
            return false;
        }
    }

    function extractElement(el) {
        try {
            var role = normalizeRole(el);
            if (role === 'hidden') return null;
            
            // More lenient visibility check - only exclude if clearly hidden
            var tag = el.tagName.toLowerCase();
            var isFormElement = ['input', 'select', 'textarea', 'button'].includes(tag);
            
            // For form elements, be more lenient - they might be in collapsed sections
            if (isFormElement) {
                // Check if element itself is explicitly hidden
                var style = window.getComputedStyle(el);
                if (style.display === 'none') return null;
            } else {
                // For other elements, use full visibility check
                if (!isVisible(el)) return null;
            }
            
            if (!isEnabled(el)) return null;

            var label = resolveLabel(el);
            var text = getTextContent(el);
            var href = el.getAttribute('href');

            var obj = {
                tag: tag,
                role: role,
                label: label || null,
                text: text || null,
                visible: true,
                enabled: true
            };

        // identifiers (only include non-empty)
        if (el.id) obj.id = el.id;
        if (el.name) obj.name = el.name;
        var dtid = el.getAttribute('data-testid');
        if (dtid) obj.data_testid = dtid;
        var dtest = el.getAttribute('data-test');
        if (dtest) obj.data_test = dtest;
        var dqa = el.getAttribute('data-qa');
        if (dqa) obj.data_qa = dqa;
        var al = el.getAttribute('aria-label');
        if (al) obj.aria_label = al;

        // type (for inputs)
        var type = el.getAttribute('type');
        if (type) obj.type = type.toLowerCase();

        // extras
        if (el.getAttribute('placeholder')) obj.placeholder = el.getAttribute('placeholder');
        if (href) obj.href = href;
        if (el.value && tag === 'input' && !['submit','button','reset'].includes(type)) obj.value = el.value;

        // select options
        var opts = getSelectOptions(el);
        if (opts) obj.options = opts;

        // required
        if (el.required || el.getAttribute('required') !== null) obj.required = true;
        if (el.getAttribute('pattern')) obj.pattern = el.getAttribute('pattern');
        if (el.getAttribute('min') !== null) obj.min = el.getAttribute('min');
        if (el.getAttribute('max') !== null) obj.max = el.getAttribute('max');
        if (el.getAttribute('maxlength') !== null) obj.maxlength = el.getAttribute('maxlength');

            return obj;
        } catch(e) {
            return null;
        }
    }

    // ---- selectors for interactive elements ----
    var selector = [
        'button', 'input', 'select', 'textarea',
        'a[href]',
        '[role="button"]', '[role="link"]', '[role="checkbox"]',
        '[role="radio"]', '[role="tab"]', '[role="switch"]',
        '[onclick]', '[tabindex]'
    ].join(',');

    var allEls = [];
    try {
        var nodeList = document.querySelectorAll(selector);
        allEls = Array.prototype.slice.call(nodeList); // Convert NodeList to Array (works everywhere)
    } catch(e) {
        // Fallback: try individual selectors
        try {
            allEls = Array.prototype.slice.call(document.querySelectorAll('button'))
                .concat(Array.prototype.slice.call(document.querySelectorAll('input')))
                .concat(Array.prototype.slice.call(document.querySelectorAll('select')))
                .concat(Array.prototype.slice.call(document.querySelectorAll('textarea')))
                .concat(Array.prototype.slice.call(document.querySelectorAll('a[href]')));
        } catch(e2) {
            console.error('Element selection failed:', e2);
        }
    }

    var navigation = [];
    var footer = [];
    var modals = [];
    var mainElements = [];

    var seen = new Set(); // deduplicate by DOM node reference

    var extractionErrors = 0;
    allEls.forEach(function(el) {
        try {
            if (seen.has(el)) return;
            seen.add(el);

            var data = extractElement(el);
            if (!data) {
                extractionErrors++;
                return;
            }

            if (isInModal(el)) { modals.push(data); return; }
            if (isInNav(el))   { navigation.push(data); return; }
            if (isInFooter(el)){ footer.push(data); return; }
            mainElements.push(data);
        } catch(e) {
            extractionErrors++;
            // Skip this element if extraction fails
        }
    });
    
    if (extractionErrors > 0) {
        console.warn('Extraction filtered out', extractionErrors, 'elements');
    }

    // ---- extract forms ----
    var forms = [];
    try {
        document.querySelectorAll('form').forEach(function(formEl) {
            try {
                if (!isVisible(formEl)) return;
                if (isInModal(formEl)) return;

                var formData = {
                    action: formEl.getAttribute('action') || null,
                    method: (formEl.getAttribute('method') || 'get').toLowerCase(),
                    elements: []
                };
                if (formEl.id) formData.id = formEl.id;
                // form heading
                try {
                    var hdg = formEl.querySelector('h1,h2,h3,h4,h5,legend');
                    if (hdg) {
                        var hdgText = hdg.innerText.trim();
                        if (hdgText) formData.label = hdgText;
                    }
                } catch(e) {}

                formEl.querySelectorAll('input,select,textarea,button').forEach(function(child) {
                    try {
                        if (seen.has(child)) return; // already processed
                        seen.add(child);
                        var d = extractElement(child);
                        if (d) formData.elements.push(d);
                    } catch(e) {}
                });

                if (formData.elements.length > 0) forms.push(formData);
            } catch(e) {}
        });
    } catch(e) {}

    // ---- page headings for context ----
    var headings = [];
    document.querySelectorAll('h1,h2,h3').forEach(function(h) {
        if (isVisible(h)) {
            headings.push({
                level: parseInt(h.tagName[1]),
                text: h.innerText.trim()
            });
        }
    });

    var result = {
        title: document.title || '',
        url: window.location.href || '',
        headings: headings || [],
        forms: forms || [],
        elements: mainElements || [],
        navigation: navigation || [],
        footer: footer || [],
        modals: modals || []
    };
    
    // Debug info
    console.log('Extraction complete:', {
        elements: mainElements.length,
        forms: forms.length,
        navigation: navigation.length,
        footer: footer.length,
        modals: modals.length
    });
    
    return result;
})();
"""


DISMISS_MODALS_JS = """
(function() {
    var dismissed = 0;

    // Common cookie/consent banner selectors
    var selectors = [
        '[class*="cookie"] button',
        '[class*="consent"] button',
        '[id*="cookie"] button',
        '[id*="consent"] button',
        '[role="dialog"] button',
        '.modal button.close',
        '[class*="banner"] button',
    ];

    var acceptWords = ['accept', 'allow', 'agree', 'ok', 'got it', 'dismiss', 'close', 'i understand'];

    selectors.forEach(function(sel) {
        document.querySelectorAll(sel).forEach(function(btn) {
            if (!btn.offsetParent) return;  // not visible
            var text = (btn.innerText || '').toLowerCase().trim();
            for (var i = 0; i < acceptWords.length; i++) {
                if (text.indexOf(acceptWords[i]) !== -1) {
                    try { btn.click(); dismissed++; } catch(e) {}
                    return;
                }
            }
        });
    });

    // Also try clicking any visible "Accept All" type button anywhere
    if (dismissed === 0) {
        document.querySelectorAll('button, a[role="button"], [role="button"]').forEach(function(btn) {
            if (!btn.offsetParent) return;
            var text = (btn.innerText || '').toLowerCase().trim();
            if (text === 'accept' || text === 'accept all' || text === 'allow all' ||
                text === 'accept cookies' || text === 'i agree') {
                try { btn.click(); dismissed++; } catch(e) {}
            }
        });
    }

    return dismissed;
})();
"""


PERFORMANCE_JS = """
(function() {
    var result = {};
    try {
        var nav = performance.getEntriesByType('navigation')[0];
        if (nav) {
            result.dom_content_loaded_ms = Math.round(nav.domContentLoadedEventEnd);
            result.load_event_ms = Math.round(nav.loadEventEnd);
        } else {
            var t = performance.timing;
            if (t && t.navigationStart) {
                result.dom_content_loaded_ms = t.domContentLoadedEventEnd - t.navigationStart;
                result.load_event_ms = t.loadEventEnd - t.navigationStart;
            }
        }
    } catch(e) {}
    try {
        result.total_resources = performance.getEntriesByType('resource').length;
    } catch(e) {}
    return result;
})();
"""


class UIModelBuilder:
    """
    Builds structured UI model from Selenium WebDriver.

    All DOM interrogation happens inside a single `execute_script`
    call so there are zero element-by-element Selenium round-trips.
    """

    def __init__(self, driver: webdriver.Chrome):
        self.driver = driver

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------

    def dismiss_modals(self) -> int:
        """Try to dismiss cookie banners / modals. Returns count dismissed."""
        try:
            dismissed = self.driver.execute_script(DISMISS_MODALS_JS)
            if dismissed:
                time.sleep(1.5)  # wait for animation
                logger.info(f"Dismissed {dismissed} modal(s)")
            return dismissed or 0
        except Exception as e:
            logger.debug(f"Modal dismissal error: {e}")
            return 0

    def build_ui_context(self, page_url: str) -> Dict:
        """
        Extract full structured UI model for the current page.

        Returns a plain dict (JSON-serialisable) – no dataclasses.
        """
        # 1. Dismiss overlays first
        self.dismiss_modals()

        # 2. Scroll to trigger lazy-loaded content
        try:
            self.driver.execute_script(
                "window.scrollTo(0, document.body.scrollHeight);"
            )
            time.sleep(0.8)
            self.driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(0.5)
        except Exception:
            pass

        # 3. Extract everything in one JS call
        try:
            # First, test if JS execution works at all
            test_result = self.driver.execute_script("return document.title;")
            logger.debug(f"JS test successful, page title: {test_result}")
            
            # Now run the full extraction
            raw = self.driver.execute_script(EXTRACT_UI_JS)
            
            if not raw or not isinstance(raw, dict):
                logger.error(f"JS extraction returned invalid result: {type(raw)}, value: {raw}")
                # Try to get at least basic info
                try:
                    title = self.driver.title
                    page_source_len = len(self.driver.page_source)
                    logger.error(f"Page has title '{title}' and {page_source_len} chars of HTML")
                except:
                    pass
                raw = {
                    "title": self.driver.title if self.driver else "",
                    "url": page_url,
                    "headings": [],
                    "forms": [],
                    "elements": [],
                    "navigation": [],
                    "footer": [],
                    "modals": [],
                }
            else:
                elem_count = len(raw.get('elements', []))
                form_count = len(raw.get('forms', []))
                nav_count = len(raw.get('navigation', []))
                logger.info(f"JS extraction succeeded: {elem_count} elements, {form_count} forms, {nav_count} nav links")
                
                # If we got nothing, log a warning
                if elem_count == 0 and form_count == 0:
                    logger.warning(f"No elements extracted! Page might be empty or extraction failed silently.")
                    # Try a simple fallback extraction
                    try:
                        simple_count = self.driver.execute_script(
                            "return document.querySelectorAll('button, input, select, textarea, a[href]').length;"
                        )
                        logger.warning(f"Simple selector found {simple_count} elements - extraction logic may be too strict")
                    except:
                        pass
        except Exception as e:
            logger.error(f"JS extraction failed: {e}", exc_info=True)
            # Try to get console errors
            try:
                logs = self.driver.get_log('browser')
                for log in logs[-5:]:  # Last 5 logs
                    logger.error(f"Browser log: {log}")
            except:
                pass
            raw = {
                "title": self.driver.title if self.driver else "",
                "url": page_url,
                "headings": [],
                "forms": [],
                "elements": [],
                "navigation": [],
                "footer": [],
                "modals": [],
            }

        # 4. Ensure url is correct (JS might give a different one after redirects)
        raw["page_url"] = raw.pop("url", page_url)

        return raw

    def extract_performance(self) -> Dict:
        """Lightweight performance metrics."""
        try:
            return self.driver.execute_script(PERFORMANCE_JS) or {}
        except Exception as e:
            logger.debug(f"Performance extraction error: {e}")
            return {}

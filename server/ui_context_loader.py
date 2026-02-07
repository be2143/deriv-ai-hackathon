"""
Load UI context from HTML or JSON (any website).
Used by run_langchain_ui_pipeline and execute_test_specs so both support .html and .json.
"""

from pathlib import Path
from typing import Any, Dict


def _css_selector_for_element(soup_element) -> str:
    """Build a stable, unique-ish CSS selector (id > name > href for links > tag+class > tag)."""
    tag = soup_element.name
    el_id = soup_element.get("id")
    if el_id and isinstance(el_id, str) and el_id.strip():
        return "#" + el_id.strip().replace(" ", "")
    name = soup_element.get("name")
    if name and tag in ("input", "select", "textarea", "button") and isinstance(name, str) and name.strip():
        return f"{tag}[name='{name.strip()}']"
    if tag == "a":
        href = soup_element.get("href")
        if href and isinstance(href, str) and href.strip():
            h = href.strip().replace("'", "\\'")
            return f"a[href='{h}']"
    classes = soup_element.get("class")
    if classes and isinstance(classes, list):
        cls = ".".join(c.strip() for c in classes if isinstance(c, str) and c.strip())
        if cls:
            return f"{tag}.{cls.replace(' ', '.')}"
    return tag


def load_ui_context_from_html(file_path: Path) -> Dict[str, Any]:
    """
    Parse an HTML file and build UI context (page_url, title, elements) for the test generator.
    Works with any website's saved DOM/HTML. Extracts links, buttons, inputs, forms, and headings.
    """
    from bs4 import BeautifulSoup

    html = file_path.read_text(encoding="utf-8", errors="replace")
    soup = BeautifulSoup(html, "html.parser")

    title_tag = soup.find("title")
    title = (title_tag.get_text(strip=True) or "").strip() if title_tag else ""

    elements = []
    seen_selectors = set()

    def add_el(tag: str, el, role: str = None) -> None:
        sel = _css_selector_for_element(el)
        if sel in seen_selectors:
            return
        seen_selectors.add(sel)
        text = (el.get_text(strip=True) or "").strip()[:200]
        entry = {
            "tag": tag,
            "role": role or tag,
            "css_selector": sel,
            "text": text or None,
        }
        if el.get("id"):
            entry["id"] = el["id"].strip() if isinstance(el["id"], str) else str(el["id"])
        if el.get("name") and tag in ("input", "select", "textarea", "button"):
            entry["name"] = el["name"].strip() if isinstance(el["name"], str) else str(el["name"])
        if el.get("type") and tag in ("input", "button"):
            entry["type"] = el["type"].strip() if isinstance(el["type"], str) else str(el["type"])
        if el.get("href") and tag == "a":
            entry["href"] = el["href"].strip() if isinstance(el["href"], str) else str(el["href"])
        if text:
            entry["label"] = text
        elements.append(entry)

    for a in soup.find_all("a", href=True):
        add_el("a", a, "link")
    for btn in soup.find_all("button"):
        add_el("button", btn)
    for inp in soup.find_all("input"):
        add_el("input", inp)
    for sel in soup.find_all("select"):
        add_el("select", sel)
    for ta in soup.find_all("textarea"):
        add_el("textarea", ta)
    for el in soup.find_all(attrs={"role": "button"}):
        if el.name not in ("button", "input"):
            add_el(el.name or "div", el, "button")
    for h in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
        sel = _css_selector_for_element(h)
        if sel in seen_selectors:
            continue
        seen_selectors.add(sel)
        text = (h.get_text(strip=True) or "").strip()[:200]
        elements.append({
            "tag": h.name,
            "role": "heading",
            "css_selector": sel,
            "text": text or None,
            "id": (h.get("id") or "").strip() or None,
            "label": text or None,
        })

    for i, el in enumerate(elements):
        if not el.get("id"):
            el["id"] = el.get("name") or el.get("label") or el.get("text") or f"element_{i}"

    page_url = ""
    stem = file_path.stem
    if stem.startswith("dom_"):
        base = stem[4:].split("____")[0].split("___")[0].rstrip("_")
        if base and ("." in base or base.startswith("www")):
            page_url = base if base.startswith("http") else "https://" + base.lstrip("./")

    return {
        "page_url": page_url,
        "title": title,
        "elements": elements,
    }

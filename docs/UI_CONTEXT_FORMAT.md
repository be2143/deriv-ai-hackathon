# UI Context JSON Format

The pipeline and executor are **format-agnostic**: they work with UI context JSON from **any website** and any crawl tool. They collect targets from common keys (`elements`, `headings`, `forms`, `links`, `buttons`) and from any top-level list of object that have `id`, `css_selector`, or `text`, so you are not tied to a single schema.

---

## Can we paste full JSON to the LLM?

**Yes.** The pipeline accepts full crawl JSON. The loader normalizes it into a single page with `page_url` and `elements` before sending to the LLM.

- **Small/medium files** – You can use the full JSON as-is.
- **Large files** (e.g. 1000+ elements, 100KB+) – Prefer compressing first:
  - **Cost** – More tokens = higher API cost.
  - **Limits** – Very large context can hit model context limits or get truncated.
  - **Quality** – Less noise helps the model focus on testable elements.

Use `ui_context_compressor.py` for large crawls; see [UI_CONTEXT_COMPRESSION.md](UI_CONTEXT_COMPRESSION.md).

---

## HTML vs JSON: which is better for the test generator?

You can provide either a **JSON** UI context or a **saved HTML** file (e.g. a DOM dump). Both are supported.

| | **JSON (crawl output)** | **HTML (saved DOM)** |
|---|-------------------------|----------------------|
| **When to use** | You have a crawler that outputs structured elements (ids, css_selectors, labels). | You only have a saved HTML file (e.g. from DevTools “Save as” or a DOM export). |
| **Quality** | Usually **better** for the generator: pre-computed selectors, less noise, only interactive elements. | HTML is parsed into the same structure automatically; selectors are derived from `id`, `name`, `href`, `class`. |
| **Token cost** | Typically smaller (only the elements you need). | Raw HTML is often larger and noisier (scripts, styles); we strip to elements so it’s still manageable. |
| **Accuracy** | Crawler may miss dynamic content or shadow DOM. | HTML is a snapshot; if the page changed after save, selectors may break. |

**Recommendation:** Prefer **JSON** from a proper crawl when you have it. Use **HTML** when that’s all you have (e.g. `dom_www.example.com____timestamp.html`). The pipeline converts HTML to the same UI context shape, so the rest of the flow is identical.

**Using HTML:** Pass an `.html` file to `--ui-context`; the loader parses it and extracts links, buttons, inputs, selects, textareas, and headings. Page URL can be inferred from filenames like `dom_www.example.com____20260206_203835.html`.

---

## Accepted formats

The loader in `run_langchain_ui_pipeline.py` (and the executor’s UI loader) accepts **HTML** (`.html`) or **JSON**. HTML is parsed into the same UI context shape (page_url, title, elements). JSON can use any of the shapes below.

### 1. Direct format (minimal)

Single page at root with URL and elements:

```json
{
  "page_url": "https://example.com/",
  "elements": [
    { "id": "submit-btn", "tag": "button", "css_selector": "#submit-btn" },
    { "id": "email", "name": "email", "tag": "input", "css_selector": "[name='email']" }
  ]
}
```

**Required:** `page_url` or `elements` at root.  
**Elements:** Each should have at least one of `id`, `name`, or `css_selector`; `tag` is recommended.

---

### 2. Single page under `"pages"` (object)

One page as an object:

```json
{
  "pages": {
    "page_url": "https://example.com/",
    "title": "Example",
    "headings": [...],
    "forms": [...],
    "elements": [
      { "tag": "button", "css_selector": "#btn", "container": { "id": "btn" } }
    ]
  }
}
```

**Required:** `pages` is an object with `page_url` (or `url`) and optionally `elements` (or elements come from `forms`).  
Elements are normalized: `id` can come from `container.id`; `css_selector` is preserved or derived from `id`/`name`.

---

### 3. Multiple pages under `"pages"` (array)

Array of pages; elements are aggregated from all pages:

```json
{
  "pages": [
    { "url": "https://example.com/", "forms": [{ "elements": [...] }] },
    { "url": "https://example.com/about", "elements": [...] }
  ]
}
```

**Required:** `pages` is a non-empty array. First page’s URL becomes `page_url`; elements from every page are merged into one list (with deduplication by id/name).

---

## How targets are collected (any website)

Validation and the executor discover targets from the UI context in a generic way:

- **Top-level lists:** `elements`, `headings`, `links`, `buttons`
- **Nested:** `forms[].elements`
- **Fallback:** Any other top-level key whose value is a list of objects with at least one of `id`, `css_selector`, or `text`
- **Page-level:** If the context has a string `title`, the target `title` is allowed (for document title assertions)
- **Per item:** For each object we use `id`, `name`, `data_testid`, `label`, `identifier`, `css_selector`, `text`, and `container.id` (as `#id`)

So any crawl output that exposes these fields (under any of these keys) will work without changing code.

---

## Element shape (after normalization)

What the pipeline and executor use for each entry in `elements`:

| Field           | Use |
|----------------|-----|
| `id`           | Logical identifier for the LLM and selectors (required after normalization). |
| `tag`          | e.g. `button`, `input`, `a`. |
| `css_selector` | Used by Selenium (required after normalization). |
| `name`         | Optional; used for id/selector if `id` missing. |
| `type`         | Optional; e.g. `submit`, `text`. |
| `role`         | Optional; e.g. `button`. |

Extra keys (e.g. `xpath`, `attributes`, `container`) are fine; the loader only normalizes `id` and `css_selector` when missing.

---

## Summary

- You **can** pass full JSON; the loader supports direct, single-page object, and multi-page array formats.
- For very large crawls, compress first and use the formats above so the LLM gets a single `page_url` + `elements` list.

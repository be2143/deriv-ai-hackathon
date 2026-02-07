import json
import os

def prune_options(options, limit=5):
    """Reduces long dropdown lists to a small representative sample."""
    if not isinstance(options, list) or len(options) <= limit:
        return options
    
    # Keep first 2, middle 1, and last 2
    head = options[:2]
    tail = options[-2:]
    middle = [options[len(options) // 2]]
    
    return head + [{"text": f"... truncated {len(options)-5} items ...", "value": "skip"}] + middle + tail

def clean_element(el):
    """Filters only the attributes needed for Selenium locators."""
    # We only care about interactive tags
    if el.get("tag") not in ["input", "select", "button", "textarea"]:
        return None
        
    cleaned = {k: v for k, v in el.items() if k in ["tag", "id", "name", "type", "value", "text"] and v}
    
    if "options" in el:
        cleaned["options"] = prune_options(el["options"])
    return cleaned

def optimize_ui_data(input_file, output_file):
    if not os.path.exists(input_file):
        print(f"Error: {input_file} not found.")
        return

    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    optimized = {"pages": []}

    for page in data.get("pages", []):
        new_page = {
            "url": page.get("page_url"),
            "title": page.get("title"),
            "forms": []
        }

        for form in page.get("forms", []):
            new_form = {
                "action": form.get("action"),
                "elements": [clean_element(e) for e in form.get("elements", []) if clean_element(e)]
            }
            new_page["forms"].append(new_form)
        
        optimized["pages"].append(new_page)

    # Save to a separate file
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(optimized, f, indent=2)

    # Calculate Savings
    original_size = os.path.getsize(input_file) / 1024
    new_size = os.path.getsize(output_file) / 1024
    print(f"✅ Optimization Complete!")
    print(f"   Original File: {input_file} ({original_size:.2f} KB)")
    print(f"   New File:      {output_file} ({new_size:.2f} KB)")
    print(f"   Reduction:     {((original_size - new_size) / original_size) * 100:.1f}%")

if __name__ == "__main__":
    # Specify your input and output filenames here
    optimize_ui_data('crawl_ui_results_20260206_172147.json', 'optimized_ui_context.json')
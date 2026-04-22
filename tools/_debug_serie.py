import re

def _normalize(text):
    text = text.lower().strip()
    text = re.sub(r"[''`\-]", " ", text)
    text = re.sub(r"[^a-z0-9\s.]", "", text)
    return re.sub(r"\s+", " ", text).strip()

# Simulate: CID is "Serie G", product is "Oliva Serie V Melanio Churchill"
cid_line_display = "Serie G"
cid_line_slug = "SERIEG"

product_title_raw = "Oliva Serie V Melanio Churchill Maduro Cigars Box of 10"

cid_line = _normalize(cid_line_display)
product_title = _normalize(product_title_raw)
cid_line_slug_norm = _normalize(cid_line_slug)

print(f"cid_line (display normalized): '{cid_line}'")
print(f"cid_line_slug (slug normalized): '{cid_line_slug_norm}'")
print(f"product_title: '{product_title}'")
print(f"cid_line in product_title: {cid_line in product_title}")
print(f"cid_line_slug in product_title: {cid_line_slug_norm in product_title}")

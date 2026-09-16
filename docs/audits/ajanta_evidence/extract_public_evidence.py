import datetime as dt
import html
import json
import re
from pathlib import Path
from urllib.parse import urlparse

import requests


OUT = Path(__file__).resolve().parent
TS = dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat()

HEADERS = {
    "User-Agent": "Mozilla/5.0 SANOCEA-read-only-public-audit/1.0",
    "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
}


def safe_name(url: str) -> str:
    parsed = urlparse(url)
    bits = [parsed.netloc.replace(".", "_")]
    path = parsed.path.strip("/").replace("/", "__")
    bits.append(path or "root")
    return "__".join(bits)


def fetch(url: str, timeout: int = 30) -> requests.Response:
    response = requests.get(url, headers=HEADERS, timeout=timeout)
    response.raise_for_status()
    return response


def write_json(name: str, data) -> None:
    (OUT / name).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def write_text(name: str, data: str) -> None:
    (OUT / name).write_text(data, encoding="utf-8")


official_store_url = "https://ajantasoya.com/wp-json/wc/store/products?per_page=100"
official_products = fetch(official_store_url).json()
write_json("official_wc_store_products_raw.json", {
    "observed_at_utc": TS,
    "url": official_store_url,
    "products": official_products,
})

official_summary = []
for product in official_products:
    row = {
        "id": product.get("id"),
        "name": product.get("name"),
        "type": product.get("type"),
        "sku": product.get("sku"),
        "permalink": product.get("permalink"),
        "is_purchasable": product.get("is_purchasable"),
        "is_in_stock": product.get("is_in_stock"),
        "add_to_cart": product.get("add_to_cart"),
        "prices": product.get("prices"),
        "attributes": product.get("attributes"),
        "variations": product.get("variations"),
        "categories": product.get("categories"),
        "images": [
            {
                "id": image.get("id"),
                "src": image.get("src"),
                "name": image.get("name"),
                "alt": image.get("alt"),
            }
            for image in product.get("images", [])
        ],
    }
    official_summary.append(row)

write_json("official_wc_store_products_summary.json", {
    "observed_at_utc": TS,
    "url": official_store_url,
    "product_count": len(official_summary),
    "products": official_summary,
})

official_pages = [
    "https://ajantasoya.com/",
    "https://ajantasoya.com/anchal-cooking-oil/",
    "https://ajantasoya.com/product/anchal-kachi-ghani-mustard-oil/",
    "https://ajantasoya.com/product/anchal-refined-soyabean-oil/",
    "https://ajantasoya.com/product/anchal-refined-sunflower-oil/",
    "https://ajantasoya.com/product/mustard-oil-offer/",
    "https://ajantasoya.com/product/soyaben-oil-offer/",
    "https://ajantasoya.com/product/buy-one-sunflower-oil-get-1l-free/",
]

page_summary = []
for url in official_pages:
    try:
        response = fetch(url)
        filename = f"html__{safe_name(url)}.html"
        write_text(filename, response.text)
        page_summary.append({
            "url": url,
            "status_code": response.status_code,
            "final_url": response.url,
            "file": filename,
            "title": re.search(r"<title[^>]*>(.*?)</title>", response.text, re.I | re.S).group(1).strip()
            if re.search(r"<title[^>]*>(.*?)</title>", response.text, re.I | re.S)
            else None,
            "contains_add_to_cart": "add-to-cart" in response.text.lower() or "add to cart" in response.text.lower(),
            "contains_free": "Free" in response.text,
        })
    except Exception as exc:
        page_summary.append({"url": url, "error": repr(exc)})

write_json("official_page_fetch_summary.json", {
    "observed_at_utc": TS,
    "pages": page_summary,
})

jio_urls = [
    "https://www.jiomart.com/product/anchal-refined-soyabean-oil-5-ltr-jar-with-1-ltr-bottle-combo-light-healthy-cooking-oil-for-everyday-meals-mj725u-50189181",
    "https://www.jiomart.com/product/anchal-refined-sunflower-oil-1-litre-bottle-pack-of-6-mki9yb-72247377",
    "https://www.jiomart.com/product/anchal-refined-sunflower-oil-1-litre-bottle-pack-of-5-mj725u-72819861",
    "https://www.jiomart.com/product/anchal-refined-soyabean-oil-5-ltr-jar-with-700-g-pouch-combo-light-healthy-cooking-oil-for-everyday-meals-mj725u-50189182",
    "https://www.jiomart.com/product/anchal-dil-se-fit-refined-soyabean-oil-750-gm-pouch-pack-of-5-light-healthy-cooking-oil-for-everyday-meals-mj725u-72489562",
]

jio_summary = []
for url in jio_urls:
    try:
        response = fetch(url)
        filename = f"html__{safe_name(url)}.html"
        write_text(filename, response.text)
        ld_json_blocks = []
        for match in re.findall(
            r"<script[^>]+type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>",
            response.text,
            flags=re.I | re.S,
        ):
            cleaned = html.unescape(match.strip())
            try:
                ld_json_blocks.append(json.loads(cleaned))
            except Exception:
                ld_json_blocks.append({"unparsed": cleaned[:2000]})
        next_data = None
        next_match = re.search(
            r"<script[^>]+id=[\"']__NEXT_DATA__[\"'][^>]*>(.*?)</script>",
            response.text,
            flags=re.I | re.S,
        )
        if next_match:
            try:
                next_data = json.loads(html.unescape(next_match.group(1)))
            except Exception:
                next_data = {"unparsed_prefix": next_match.group(1)[:2000]}
        write_json(f"extracted__{safe_name(url)}.json", {
            "observed_at_utc": TS,
            "url": url,
            "status_code": response.status_code,
            "final_url": response.url,
            "ld_json": ld_json_blocks,
            "next_data_present": next_data is not None,
            "next_data": next_data,
        })
        text = re.sub(r"\s+", " ", response.text)
        needles = ["Anchal", "700", "750", "MRP", "price", "availability", "Product"]
        snippets = {}
        for needle in needles:
            index = text.lower().find(needle.lower())
            snippets[needle] = text[max(0, index - 300): index + 500] if index >= 0 else None
        jio_summary.append({
            "url": url,
            "status_code": response.status_code,
            "final_url": response.url,
            "raw_file": filename,
            "extracted_file": f"extracted__{safe_name(url)}.json",
            "ld_json_blocks": len(ld_json_blocks),
            "next_data_present": next_data is not None,
            "snippets": snippets,
        })
    except Exception as exc:
        jio_summary.append({"url": url, "error": repr(exc)})

write_json("jiomart_fetch_summary.json", {
    "observed_at_utc": TS,
    "pages": jio_summary,
})

print(json.dumps({
    "observed_at_utc": TS,
    "official_products": len(official_summary),
    "official_pages": len(page_summary),
    "jiomart_pages": len(jio_summary),
    "out": str(OUT),
}, indent=2))

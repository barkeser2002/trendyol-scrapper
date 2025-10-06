import json
import os
import re
import time
import unicodedata
from typing import Any, Callable, Dict, List, Optional, Set
from urllib.parse import quote_plus

import pandas as pd
import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait

BASE_URL = "https://www.trendyol.com"
SEARCH_URL_TEMPLATE = "https://www.trendyol.com/sr?q={query}&qt={query}&st={query}&os=1"
SELLER_LINK_TEMPLATE = "https://www.trendyol.com/magaza/{slug}-m-{merchant_id}"
DETAIL_SCRIPT_PATTERN = r'window\["__envoy_flash-sales-banner__PROPS"\]=({.*?})</script>'
SELLER_PROPS_PATTERNS = [
    r'window\["__envoy_seller-storefront-web__PROPS"\]=({.*?})</script>',
    r'window\["__envoy_seller-storefront__PROPS"\]=({.*?})</script>',
]
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
    "Cache-Control": "no-cache",
}
DEFAULT_MAX_PAGES = int(os.getenv("TRENDYOL_MAX_PAGES", "7"))
SCROLL_PAUSE_SECONDS = 1.25
MAX_SCROLL_ROUNDS = 40
STAGNATION_LIMIT = 3
PAGE_READY_SELECTOR = (By.CSS_SELECTOR, "div.p-card-wrppr")


def create_driver(headless: bool = True) -> webdriver.Chrome:
    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument(f"--user-agent={HEADERS['User-Agent']}")
    service = Service()
    return webdriver.Chrome(service=service, options=options)


def slugify(value: str) -> str:
    if not value:
        return ""
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_value).strip("-")
    return slug.lower()


def build_seller_link(name: Optional[str], merchant_id: Optional[int]) -> str:
    if not name or not merchant_id:
        return "N/A"
    return SELLER_LINK_TEMPLATE.format(slug=slugify(name), merchant_id=merchant_id)


def ensure_absolute_url(url: Optional[str]) -> Optional[str]:
    if not url or url == "N/A":
        return None
    if url.startswith("http"):
        return url
    if url.startswith("/"):
        return f"{BASE_URL}{url}"
    return f"{BASE_URL}/{url.lstrip('/')}"


def extract_props_json(html: str, pattern: str) -> Optional[Dict[str, Any]]:
    if not html:
        return None
    match = re.search(pattern, html, re.DOTALL)
    if not match:
        return None
    payload = match.group(1).strip().rstrip(";")
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        return None


def collect_image_urls(image_payload: Any) -> List[str]:
    images: List[str] = []
    if isinstance(image_payload, list):
        for entry in image_payload:
            if isinstance(entry, str):
                images.append(entry)
            elif isinstance(entry, dict):
                for key in ("url", "imageUrl", "original", "thumbnail"):
                    candidate = entry.get(key)
                    if candidate:
                        images.append(candidate)
                        break
    return images


def format_price(price_info: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not price_info:
        return {"price_text": "N/A", "price_value": "N/A", "currency": "N/A"}
    discounted = price_info.get("discountedPrice", {}) if isinstance(price_info, dict) else {}
    return {
        "price_text": discounted.get("text")
        or price_info.get("text")
        or str(discounted.get("value", "N/A")),
        "price_value": discounted.get("value") or price_info.get("value", "N/A"),
        "currency": price_info.get("currency", discounted.get("currency", "N/A")),
    }


def format_merchant_record(
    merchant_id: Optional[int],
    name: Optional[str],
    price: Optional[Dict[str, Any]],
    merchant_type: str,
    official_name: Optional[str] = None,
    city: Optional[str] = None,
    email: Optional[str] = None,
    tax: Optional[str] = None,
    seller_link: Optional[str] = None,
    listing_id: Optional[str] = None,
    quantity: Optional[Any] = None,
    fulfilment: Optional[str] = None,
    is_ty_plus: Optional[bool] = None,
) -> Optional[Dict[str, Any]]:
    if not merchant_id or not name:
        return None
    price_info = format_price(price)
    seller_url = ensure_absolute_url(seller_link)
    if not seller_url:
        fallback_link = build_seller_link(name, merchant_id)
        seller_url = ensure_absolute_url(fallback_link) or fallback_link
    return {
        "Merchant Type": merchant_type,
        "Merchant ID": merchant_id,
        "Merchant Name": name,
        "officialName": official_name or "N/A",
        "cityName": city or "N/A",
        "registeredEmailAddress": email or "N/A",
        "taxNumber": tax or "N/A",
        "sellerLink": seller_url or "N/A",
        "Price Text": price_info["price_text"] or "N/A",
        "Price Value": price_info["price_value"] or "N/A",
        "Currency": price_info["currency"] or "N/A",
        "Listing ID": listing_id or "N/A",
        "Stock": quantity if quantity is not None else "N/A",
        "Fulfilment Type": fulfilment or "N/A",
        "isTyPlusEligible": is_ty_plus if is_ty_plus is not None else "N/A",
    }


def build_primary_merchant(merchant_listing: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    merchant = merchant_listing.get("merchant") or {}
    winner = merchant_listing.get("winnerVariant") or {}
    variants = merchant_listing.get("variants") or []
    fallback_variant = variants[0] if variants else {}
    listing_id = winner.get("listingId") or fallback_variant.get("listingId")
    quantity = winner.get("quantity") if winner else fallback_variant.get("quantity")
    fulfilment = winner.get("fulfilmentType") or fallback_variant.get("fulfilmentType")
    is_ty_plus = winner.get("isTyPlusEligible") if winner else fallback_variant.get("isTyPlusEligible")
    price_info = (
        (winner.get("price") if winner else None)
        or fallback_variant.get("price")
        or merchant_listing.get("price")
    )
    return format_merchant_record(
        merchant_id=merchant.get("id"),
        name=merchant.get("name"),
        price=price_info,
        merchant_type="Primary",
        official_name=merchant.get("officialName"),
        city=merchant.get("cityName"),
        email=merchant.get("registeredEmailAddress"),
        tax=merchant.get("taxNumber"),
        seller_link=build_seller_link(merchant.get("name"), merchant.get("id")),
        listing_id=listing_id,
        quantity=quantity,
        fulfilment=fulfilment,
        is_ty_plus=is_ty_plus,
    )


def build_other_merchant(other: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    variants = other.get("variants") or []
    variant = variants[0] if variants else {}
    price = other.get("price") or variant.get("price")
    listing_id = variant.get("listingId")
    quantity = variant.get("quantity")
    fulfilment = variant.get("fulfilmentType")
    return format_merchant_record(
        merchant_id=other.get("id"),
        name=other.get("name"),
        price=price,
        merchant_type="Other",
        official_name=other.get("officialName"),
        city=other.get("cityName"),
        email=other.get("registeredEmailAddress"),
        tax=other.get("taxNumber"),
        seller_link=ensure_absolute_url(other.get("url")),
        listing_id=listing_id,
        quantity=quantity,
        fulfilment=fulfilment,
        is_ty_plus=variant.get("isTyPlusEligible"),
    )


def parse_product_detail(html: str) -> Dict[str, Any]:
    data = extract_props_json(html, DETAIL_SCRIPT_PATTERN)
    if not data:
        return {}

    product = data.get("product", {})
    category = product.get("category") or {}
    general = {
        "product_code": product.get("productCode") or "N/A",
        "category_name": category.get("name") or "N/A",
        "category_hierarchy": category.get("hierarchy") or "N/A",
        "brand": (product.get("brand") or {}).get("name", "N/A"),
        "images": collect_image_urls(product.get("images") or []),
    }

    merchants: List[Dict[str, Any]] = []
    merchant_listing = product.get("merchantListing") or {}
    primary_record = build_primary_merchant(merchant_listing)
    if primary_record:
        merchants.append(primary_record)
    for other in merchant_listing.get("otherMerchants", []):
        other_record = build_other_merchant(other)
        if other_record:
            merchants.append(other_record)

    return {"general": general, "merchants": merchants}


class ProductDetailFetcher:
    def __init__(self, session: requests.Session, headless: bool = True) -> None:
        self.session = session
        self._driver: Optional[webdriver.Chrome] = None
        self._headless = headless
        self._seller_cache: Dict[int, Dict[str, Any]] = {}

    def _get_driver(self) -> webdriver.Chrome:
        if self._driver is None:
            self._driver = create_driver(headless=self._headless)
        return self._driver

    def fetch_page(self, url: str) -> Optional[str]:
        if not url:
            return None
        try:
            response = self.session.get(url, timeout=20)
            if response.ok and "__envoy_flash-sales-banner__PROPS" in response.text:
                return response.text
        except requests.RequestException:
            pass

        try:
            driver = self._get_driver()
            driver.get(url)
            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
            time.sleep(1.0)
            return driver.page_source
        except Exception:
            return None

    def fetch_seller_details(
        self,
        merchant_id: Optional[int],
        merchant_name: Optional[str],
        merchant_link: Optional[str] = None,
    ) -> Dict[str, Any]:
        if merchant_id is None:
            return {}
        if merchant_id in self._seller_cache:
            return self._seller_cache[merchant_id]
        link = ensure_absolute_url(merchant_link)
        if not link:
            fallback_link = build_seller_link(merchant_name, merchant_id)
            link = ensure_absolute_url(fallback_link) or fallback_link
        if not link or link == "N/A":
            self._seller_cache[merchant_id] = {}
            return {}
        html = None
        try:
            response = self.session.get(link, timeout=12)
            if response.ok:
                html = response.text
        except requests.RequestException:
            pass
        if html is None:
            try:
                driver = self._get_driver()
                driver.get(link)
                WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
                time.sleep(1.0)
                html = driver.page_source
            except Exception:
                self._seller_cache[merchant_id] = {}
                return {}
        for pattern in SELLER_PROPS_PATTERNS:
            props = extract_props_json(html, pattern)
            if props:
                seller = props.get("seller") or props.get("merchant") or {}
                corporate = seller.get("corporateInfo") or {}
                details = {
                    "officialName": corporate.get("officialName") or seller.get("corporateTitle"),
                    "cityName": corporate.get("cityName") or seller.get("city"),
                    "registeredEmailAddress": corporate.get("registeredEmail"),
                    "taxNumber": corporate.get("taxNumber") or seller.get("taxNumber"),
                }
                self._seller_cache[merchant_id] = details
                return details
        self._seller_cache[merchant_id] = {}
        return {}

    def close(self) -> None:
        if self._driver:
            self._driver.quit()
            self._driver = None


def load_all_results(driver: webdriver.Chrome) -> None:
    stagnation = 0
    last_count = 0
    for _ in range(MAX_SCROLL_ROUNDS):
        try:
            WebDriverWait(driver, 10).until(EC.presence_of_element_located(PAGE_READY_SELECTOR))
        except Exception:
            time.sleep(SCROLL_PAUSE_SECONDS)
        cards = driver.find_elements(By.CSS_SELECTOR, "div.p-card-wrppr")
        count = len(cards)
        if count == 0:
            time.sleep(SCROLL_PAUSE_SECONDS)
            continue
        if count == last_count:
            stagnation += 1
        else:
            stagnation = 0
            last_count = count
        if stagnation >= STAGNATION_LIMIT:
            break
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(SCROLL_PAUSE_SECONDS)
        try:
            load_more = driver.find_element(By.CSS_SELECTOR, "div.infinite-scroll button")
            if load_more.is_displayed():
                driver.execute_script("arguments[0].click();", load_more)
                time.sleep(1.0)
        except Exception:
            pass


def collect_products_from_cards(
    soup: BeautifulSoup, seen_ids: Optional[Set[str]] = None
) -> List[Dict[str, Any]]:
    products: List[Dict[str, Any]] = []
    if seen_ids is None:
        seen_ids = set()
    for card in soup.select("div.p-card-wrppr"):
        link_elem = card.find("a", href=True)
        if not link_elem:
            continue
        url_path = link_elem["href"]
        url_full = url_path if url_path.startswith("http") else f"{BASE_URL}{url_path}"
        product_id_match = re.search(r"p-(\d+)", url_full)
        product_id = product_id_match.group(1) if product_id_match else None
        if not product_id or product_id in seen_ids:
            continue
        seen_ids.add(product_id)
        name_elem = card.find("span", class_=re.compile(r"prdct-desc-cntnr-name"))
        product_name = name_elem.get_text(strip=True) if name_elem else link_elem.get_text(strip=True)
        image_elem = card.find("img")
        image_url = image_elem.get("data-src") or image_elem.get("src") if image_elem else None
        boutique_match = re.search(r"boutiqueId=(\d+)", url_full)
        category_id = boutique_match.group(1) if boutique_match else "N/A"
        products.append(
            {
                "product_id": product_id,
                "product_name": product_name,
                "product_url": url_full,
                "category_id": category_id,
                "image_url": image_url,
            }
        )
    return products


def enrich_merchant_with_seller(fetcher: ProductDetailFetcher, merchant: Dict[str, Any]) -> Dict[str, Any]:
    fields_to_check = ("officialName", "cityName", "registeredEmailAddress", "taxNumber")
    needs_enrichment = any(merchant.get(field) in (None, "N/A") for field in fields_to_check)
    if merchant.get("Merchant Type") == "Other":
        needs_enrichment = True
    if not needs_enrichment:
        return merchant
    existing_link = merchant.get("sellerLink")
    additional = fetcher.fetch_seller_details(
        merchant.get("Merchant ID"),
        merchant.get("Merchant Name"),
        existing_link if isinstance(existing_link, str) else None,
    )
    if not additional:
        return merchant
    normalized_link = ensure_absolute_url(existing_link)
    if not normalized_link:
        fallback_link = build_seller_link(merchant.get("Merchant Name"), merchant.get("Merchant ID"))
        normalized_link = ensure_absolute_url(fallback_link)
    if normalized_link:
        merchant["sellerLink"] = normalized_link
    for source_key, column in {
        "officialName": "officialName",
        "cityName": "cityName",
        "registeredEmailAddress": "registeredEmailAddress",
        "taxNumber": "taxNumber",
    }.items():
        value = additional.get(source_key)
        if value:
            merchant[column] = value
    return merchant


def search_trendyol(
    query: str,
    headless: bool = True,
    progress_callback: Optional[Callable[[int, int, str, str], None]] = None,
    max_pages: Optional[int] = None,
) -> List[Dict[str, Any]]:
    def notify(current: int, total: int, stage: str, message: str) -> None:
        if progress_callback:
            try:
                progress_callback(current, total, stage, message)
            except Exception:
                pass

    notify(0, 0, "initializing", "Arama hazırlanıyor")
    encoded_query = quote_plus(query)
    base_search_url = SEARCH_URL_TEMPLATE.format(query=encoded_query)
    page_limit = max_pages if isinstance(max_pages, int) and max_pages > 0 else DEFAULT_MAX_PAGES

    driver = create_driver(headless=headless)
    session = requests.Session()
    session.headers.update(HEADERS)

    products: List[Dict[str, Any]] = []
    seen_ids: set[str] = set()
    try:
        notify(0, 0, "loading", "Arama sonuçları yükleniyor")
        for page in range(1, page_limit + 1):
            page_url = f"{base_search_url}&pi={page}"
            notify(len(products), 0, "loading", f"{page}. sayfa yükleniyor")
            driver.get(page_url)
            WebDriverWait(driver, 10).until(EC.presence_of_element_located(PAGE_READY_SELECTOR))
            load_all_results(driver)
            time.sleep(1.0)
            soup = BeautifulSoup(driver.page_source, "html.parser")
            before_count = len(products)
            page_products = collect_products_from_cards(soup, seen_ids)
            if not page_products:
                break
            products.extend(page_products)
            if page == 1:
                for cookie in driver.get_cookies():
                    session.cookies.set(cookie["name"], cookie["value"])
            if len(page_products) < 24:
                break
    finally:
        driver.quit()

    fetcher = ProductDetailFetcher(session, headless=headless)
    rows: List[Dict[str, Any]] = []
    total_products = len(products)
    if total_products == 0:
        notify(0, 0, "completed", "Hiç ürün bulunamadı")
        return rows
    notify(0, total_products, "processing", f"{total_products} ürün bulundu. Ayrıntılar getiriliyor")
    try:
        for index, product in enumerate(products, start=1):
            detail_html = fetcher.fetch_page(product["product_url"])
            parsed = parse_product_detail(detail_html or "")
            general = parsed.get("general", {})
            merchants = parsed.get("merchants", [])
            if not merchants:
                row = {
                    "Product ID": product["product_id"],
                    "Product Name": product["product_name"],
                    "Product Code": general.get("product_code", "N/A"),
                    "Category Name": general.get("category_name", "N/A"),
                    "Category Hierarchy": general.get("category_hierarchy", "N/A"),
                    "Category ID": product.get("category_id", "N/A"),
                    "Brand": general.get("brand", "N/A"),
                    "Product URL": product["product_url"],
                    "Image URLs": general.get("images") or [product.get("image_url") or "N/A"],
                    "Merchant Type": "N/A",
                    "Merchant ID": "N/A",
                    "Merchant Name": "N/A",
                    "officialName": "N/A",
                    "cityName": "N/A",
                    "registeredEmailAddress": "N/A",
                    "taxNumber": "N/A",
                    "sellerLink": "N/A",
                    "Price Text": "N/A",
                    "Price Value": "N/A",
                    "Currency": "N/A",
                    "Listing ID": "N/A",
                    "Stock": "N/A",
                    "Fulfilment Type": "N/A",
                    "isTyPlusEligible": "N/A",
                }
                if isinstance(row["Image URLs"], list):
                    row["Image URLs"] = " | ".join([img for img in row["Image URLs"] if img]) or "N/A"
                rows.append(row)
                notify(index, total_products, "processing", f"{index}/{total_products} ürün işlendi")
                continue

            for merchant in merchants:
                enriched = enrich_merchant_with_seller(fetcher, merchant)
                row = {
                    "Product ID": product["product_id"],
                    "Product Name": product["product_name"],
                    "Product Code": general.get("product_code", "N/A"),
                    "Category Name": general.get("category_name", "N/A"),
                    "Category Hierarchy": general.get("category_hierarchy", "N/A"),
                    "Category ID": product.get("category_id", "N/A"),
                    "Brand": general.get("brand", "N/A"),
                    "Product URL": product["product_url"],
                    "Image URLs": general.get("images") or [product.get("image_url") or "N/A"],
                }
                row.update(enriched)
                image_data = row["Image URLs"]
                if isinstance(image_data, list):
                    row["Image URLs"] = " | ".join([img for img in image_data if img]) or "N/A"
                rows.append(row)
            notify(index, total_products, "processing", f"{index}/{total_products} ürün işlendi")
    finally:
        fetcher.close()

    notify(total_products, total_products, "completed", "Arama tamamlandı")
    return rows


def export_to_excel(rows: List[Dict[str, Any]], output_path: str = "trendyol_products.xlsx") -> None:
    if not rows:
        return
    df = pd.DataFrame(rows)
    if os.path.exists(output_path):
        os.remove(output_path)
    df.to_excel(output_path, index=False)


def main() -> None:
    query = input("Arama terimini girin: ")
    if not query.strip():
        print("Arama terimi boş olamaz.")
        return
    last_percent: Optional[int] = None

    def cli_progress(current: int, total: int, stage: str, message: str) -> None:
        nonlocal last_percent
        if total:
            percent = int((current / total) * 100)
            if percent != last_percent:
                print(f"[{percent:3d}%] {message}", end="\r", flush=True)
                last_percent = percent
        else:
            print(f"[{stage}] {message}")

    rows = search_trendyol(query, progress_callback=cli_progress)
    if last_percent is not None:
        print()
    if rows:
        export_to_excel(rows)
        print(f"{len(rows)} satır Excel'e kaydedildi.")
    else:
        print("Ürün bulunamadı veya veri alınamadı.")


if __name__ == "__main__":
    main()
"""
BaseExtractor - Standardized base class for all cigar retailer extractors.

All AI-generated extractors inherit from this class. Existing extractors
can be migrated incrementally but are not required to use it.

Provides:
- Session management with standard headers
- Rate limiting between requests
- Retry logic with exponential backoff
- Price parsing utilities
- Stock detection helpers
- Box quantity extraction helpers
- Standardized return format compatible with all update scripts
"""

import requests
from bs4 import BeautifulSoup
import re
import time
import logging
from typing import Dict, Optional, Tuple, List
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class BaseExtractor(ABC):
    """
    Base class for retailer-specific price extractors.

    Subclasses must implement:
        - RETAILER_NAME: Display name (e.g., "Fox Cigar")
        - RETAILER_KEY: CSV filename stem (e.g., "foxcigar")
        - extract_product_data(url): Core extraction logic

    Subclasses may override:
        - RATE_LIMIT_SECONDS: Delay between requests (default 1.5)
        - REQUEST_TIMEOUT: HTTP timeout in seconds (default 15)
        - MAX_RETRIES: Number of retry attempts (default 2)
        - USER_AGENT: Browser user agent string
        - VALID_PRICE_RANGE: (min, max) tuple for price sanity checks
        - VALID_BOX_QTY_RANGE: (min, max) tuple for box quantity checks
    """

    RETAILER_NAME: str = ""
    RETAILER_KEY: str = ""
    BASE_URL: str = ""

    RATE_LIMIT_SECONDS: float = 1.5
    REQUEST_TIMEOUT: int = 15
    MAX_RETRIES: int = 2

    USER_AGENT: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )

    VALID_PRICE_RANGE: Tuple[float, float] = (20.0, 5000.0)
    VALID_BOX_QTY_RANGE: Tuple[int, int] = (5, 100)

    PRICE_REGEX = re.compile(r'\$(\d{1,4}(?:,\d{3})*(?:\.\d{2})?)')

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': self.USER_AGENT,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
        })
        self._last_request_time = 0.0

    # ── Core interface ──────────────────────────────────────────────

    @abstractmethod
    def extract_product_data(self, url: str) -> Dict:
        """
        Extract product data from a single product page URL.

        Must return a dict with at least:
            price (float | None): Box price in dollars
            box_quantity (int | None): Number of cigars in box
            in_stock (bool): Whether the product is available
            error (str | None): Error message if extraction failed

        May also include:
            discount_percent (float | None): Percentage discount from MSRP
            msrp (float | None): Manufacturer's suggested retail price
            title (str | None): Product title as shown on page
        """
        raise NotImplementedError

    def extract(self, url: str) -> Dict:
        """
        Public entry point. Calls extract_product_data with rate limiting,
        retries, and output normalization.

        Returns the standardized format expected by all update scripts:
            {success, price, box_quantity, in_stock, discount_percent, error}
        """
        self._rate_limit()

        last_error = None
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                raw = self.extract_product_data(url)
                return self._normalize_output(raw)
            except requests.exceptions.Timeout:
                last_error = f"Request timed out (attempt {attempt}/{self.MAX_RETRIES})"
                logger.warning(f"[{self.RETAILER_NAME}] {last_error}: {url}")
                if attempt < self.MAX_RETRIES:
                    time.sleep(2 ** attempt)
            except requests.exceptions.HTTPError as e:
                status = e.response.status_code if e.response is not None else "unknown"
                last_error = f"HTTP {status} (attempt {attempt}/{self.MAX_RETRIES})"
                logger.warning(f"[{self.RETAILER_NAME}] {last_error}: {url}")
                if status in (429, 503) and attempt < self.MAX_RETRIES:
                    time.sleep(2 ** attempt)
                else:
                    break
            except Exception as e:
                last_error = str(e)
                logger.error(f"[{self.RETAILER_NAME}] Extraction error: {last_error}: {url}")
                break

        return {
            'success': False,
            'price': None,
            'box_quantity': None,
            'in_stock': False,
            'discount_percent': None,
            'error': last_error,
        }

    # ── HTTP helpers ────────────────────────────────────────────────

    def fetch_page(self, url: str) -> BeautifulSoup:
        """
        Fetch a URL and return parsed BeautifulSoup.
        Raises on HTTP errors so the retry loop in extract() can handle them.
        """
        response = self.session.get(url, timeout=self.REQUEST_TIMEOUT)
        response.raise_for_status()
        return BeautifulSoup(response.content, 'html.parser')

    def fetch_html(self, url: str) -> str:
        """Fetch a URL and return raw HTML string."""
        response = self.session.get(url, timeout=self.REQUEST_TIMEOUT)
        response.raise_for_status()
        return response.text

    def _rate_limit(self):
        """Enforce minimum delay between requests."""
        now = time.time()
        elapsed = now - self._last_request_time
        if elapsed < self.RATE_LIMIT_SECONDS:
            time.sleep(self.RATE_LIMIT_SECONDS - elapsed)
        self._last_request_time = time.time()

    # ── Price parsing utilities ─────────────────────────────────────

    def parse_price(self, text: str) -> Optional[float]:
        """Extract a single dollar price from text. Returns None if not found."""
        match = self.PRICE_REGEX.search(text)
        if match:
            try:
                return float(match.group(1).replace(',', ''))
            except ValueError:
                return None
        return None

    def parse_all_prices(self, text: str) -> List[float]:
        """Extract all dollar prices from text, filtered to valid range."""
        matches = self.PRICE_REGEX.findall(text)
        prices = []
        for price_str in matches:
            try:
                val = float(price_str.replace(',', ''))
                if self.VALID_PRICE_RANGE[0] <= val <= self.VALID_PRICE_RANGE[1]:
                    prices.append(val)
            except ValueError:
                continue
        return prices

    def is_valid_price(self, price: Optional[float]) -> bool:
        """Check if a price falls within the expected range."""
        if price is None:
            return False
        return self.VALID_PRICE_RANGE[0] <= price <= self.VALID_PRICE_RANGE[1]

    # ── Stock detection utilities ───────────────────────────────────

    OUT_OF_STOCK_PATTERNS = [
        re.compile(r'out\s+of\s+stock', re.I),
        re.compile(r'sold\s+out', re.I),
        re.compile(r'currently\s+unavailable', re.I),
        re.compile(r'notify\s+me\s+when', re.I),
        re.compile(r'notify\s+when\s+available', re.I),
        re.compile(r'back\s+in\s+stock', re.I),
    ]

    IN_STOCK_PATTERNS = [
        re.compile(r'add\s+to\s+cart', re.I),
        re.compile(r'buy\s+now', re.I),
        re.compile(r'in\s+stock', re.I),
    ]

    def detect_stock_from_text(self, page_text: str) -> Optional[bool]:
        """
        Detect stock status from page text.
        Returns True (in stock), False (out of stock), or None (indeterminate).
        """
        for pattern in self.OUT_OF_STOCK_PATTERNS:
            if pattern.search(page_text):
                return False
        for pattern in self.IN_STOCK_PATTERNS:
            if pattern.search(page_text):
                return True
        return None

    def detect_stock_from_soup(self, soup: BeautifulSoup) -> Optional[bool]:
        """
        Detect stock status from parsed HTML using buttons and meta tags.
        Returns True, False, or None (indeterminate).
        """
        notify_btn = soup.find(
            ['button', 'input'],
            string=re.compile(r'notify\s+me', re.I),
        )
        if notify_btn:
            return False

        add_cart_btn = soup.find(
            ['button', 'input'],
            string=re.compile(r'add\s+to\s+cart', re.I),
        )
        if add_cart_btn and not add_cart_btn.get('disabled'):
            return True

        og_avail = soup.find('meta', property='og:availability')
        if og_avail:
            content = (og_avail.get('content') or '').lower()
            if 'instock' in content or 'in stock' in content:
                return True
            if 'outofstock' in content or 'out of stock' in content:
                return False

        return None

    # ── Box quantity utilities ──────────────────────────────────────

    BOX_QTY_PATTERNS = [
        re.compile(r'box\s+of\s+(\d+)', re.I),
        re.compile(r'box\s*(\d+)', re.I),
        re.compile(r'(\d+)\s*(?:ct|count)\s*box', re.I),
        re.compile(r'(\d+)\s+count', re.I),
        re.compile(r'(\d+)\s*cigars?\s*(?:per\s+)?box', re.I),
    ]

    def extract_box_quantity(self, text: str) -> Optional[int]:
        """
        Extract box quantity from text using common patterns.
        Returns None if no valid quantity found.
        """
        for pattern in self.BOX_QTY_PATTERNS:
            match = pattern.search(text)
            if match:
                try:
                    qty = int(match.group(1))
                    if self.VALID_BOX_QTY_RANGE[0] <= qty <= self.VALID_BOX_QTY_RANGE[1]:
                        return qty
                except ValueError:
                    continue
        return None

    def is_valid_box_quantity(self, qty: Optional[int]) -> bool:
        """Check if a box quantity falls within the expected range."""
        if qty is None:
            return False
        return self.VALID_BOX_QTY_RANGE[0] <= qty <= self.VALID_BOX_QTY_RANGE[1]

    # ── Output normalization ────────────────────────────────────────

    def _normalize_output(self, raw: Dict) -> Dict:
        """
        Convert the raw dict from extract_product_data into the standardized
        format that all update scripts expect.

        Handles both naming conventions:
            box_price/price -> price
            box_qty/box_quantity -> box_quantity
        """
        price = raw.get('price') or raw.get('box_price')
        box_qty = raw.get('box_quantity') or raw.get('box_qty')
        in_stock = raw.get('in_stock', False)
        error = raw.get('error')
        discount = raw.get('discount_percent')

        if box_qty is not None:
            try:
                box_qty = int(box_qty)
            except (ValueError, TypeError):
                box_qty = None

        return {
            'success': error is None and price is not None,
            'price': price,
            'box_quantity': box_qty,
            'in_stock': bool(in_stock),
            'discount_percent': discount,
            'error': error,
        }

    # ── Validation ──────────────────────────────────────────────────

    def validate_extraction(self, result: Dict) -> List[str]:
        """
        Run sanity checks on an extraction result.
        Returns a list of warning messages (empty = all good).
        """
        warnings = []

        price = result.get('price') or result.get('box_price')
        if price is not None and not self.is_valid_price(price):
            warnings.append(
                f"Price ${price} outside expected range "
                f"${self.VALID_PRICE_RANGE[0]}-${self.VALID_PRICE_RANGE[1]}"
            )

        qty = result.get('box_quantity') or result.get('box_qty')
        if qty is not None and not self.is_valid_box_quantity(qty):
            warnings.append(
                f"Box quantity {qty} outside expected range "
                f"{self.VALID_BOX_QTY_RANGE[0]}-{self.VALID_BOX_QTY_RANGE[1]}"
            )

        if price is not None and result.get('in_stock') is False:
            warnings.append("Product has a price but is marked out of stock")

        return warnings


def create_extract_function(extractor_class):
    """
    Factory that creates a module-level extract function from an extractor class.

    Usage in a retailer extractor module:
        class MyRetailerExtractor(BaseExtractor):
            ...

        extract_my_retailer_data = create_extract_function(MyRetailerExtractor)

    The returned function has the signature:
        extract_my_retailer_data(url: str, **kwargs) -> Dict
    and returns the standardized {success, price, box_quantity, in_stock, ...} format.
    """
    _instance = None

    def extract_fn(url: str, **kwargs) -> Dict:
        nonlocal _instance
        if _instance is None:
            _instance = extractor_class()
        return _instance.extract(url)

    extract_fn.__doc__ = f"Extract product data from {extractor_class.RETAILER_NAME}"
    extract_fn.__name__ = f"extract_{extractor_class.RETAILER_KEY}_data"
    return extract_fn

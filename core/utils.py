"""
core/utils.py — Centralized utilities for APRS V5.

Eliminates duplicate helper functions scattered across web/app.py,
core/orchestrator.py, and core/excel_manager.py.
Provides a single authoritative region normalizer that uses exact-match
enum lookup — NOT substring matching — to prevent Finland/Indonesia/Argentina
misclassification bugs.
"""
from urllib.parse import quote_plus

# ── Canonical region names (the only valid values in the system) ───────────
REGION_ENUM = {"India", "USA", "UK", "Europe", "GCC_MiddleEast", "Germany", "France"}

# ── Alias map: common variations → canonical name ─────────────────────────
_REGION_ALIASES = {
    "india":          "India",
    "in":             "India",
    "amazon.in":      "India",
    "usa":            "USA",
    "us":             "USA",
    "united states":  "USA",
    "amazon.com":     "USA",
    "uk":             "UK",
    "united kingdom": "UK",
    "amazon.co.uk":   "UK",
    "europe":         "Europe",
    "eu":             "Europe",
    "germany":        "Germany",
    "de":             "Germany",
    "amazon.de":      "Germany",
    "france":         "France",
    "fr":             "France",
    "amazon.fr":      "France",
    "gcc":            "GCC_MiddleEast",
    "gcc_middleeast": "GCC_MiddleEast",
    "middleeast":     "GCC_MiddleEast",
    "uae":            "GCC_MiddleEast",
    "dubai":          "GCC_MiddleEast",
    "saudi":          "GCC_MiddleEast",
    "amazon.ae":      "GCC_MiddleEast",
}

# ── Currency map per canonical region ─────────────────────────────────────
_REGION_CURRENCY = {
    "India":         ("₹",    "INR"),
    "USA":           ("$",    "USD"),
    "UK":            ("£",    "GBP"),
    "Europe":        ("€",    "EUR"),
    "Germany":       ("€",    "EUR"),
    "France":        ("€",    "EUR"),
    "GCC_MiddleEast": ("AED ", "AED"),
}


def normalize_region(region: str) -> str:
    """
    Exact-match alias lookup for region strings.
    Returns a canonical region name from REGION_ENUM.
    Falls back to "USA" if not recognized.

    Examples:
        normalize_region("india")         -> "India"
        normalize_region("India")         -> "India"
        normalize_region("IN")            -> "India"
        normalize_region("Finland")       -> "USA"   (safe default, not India!)
        normalize_region("Indonesia")     -> "USA"   (safe default, not India!)
        normalize_region("GCC_MiddleEast") -> "GCC_MiddleEast"
    """
    if not region:
        return "USA"
    # Direct canonical match first
    if region in REGION_ENUM:
        return region
    # Alias lookup (case-insensitive, strip whitespace)
    normalized = region.strip().lower().replace(" ", "").replace("_", "")
    # Try the alias map
    for alias, canonical in _REGION_ALIASES.items():
        if alias.replace("_", "") == normalized:
            return canonical
    # Final fallback
    return "USA"


def get_region_currency(region: str):
    """
    Returns (currency_symbol, currency_code) for a region string.
    Uses normalize_region() — no substring matching.
    """
    canonical = normalize_region(region)
    return _REGION_CURRENCY.get(canonical, ("$", "USD"))


def format_currency(amount, region: str) -> str:
    """Format a numeric amount as a currency string for the given region."""
    sym, code = get_region_currency(region)
    if amount is None:
        return f"{sym}0.00"
    try:
        val = float(amount)
    except (TypeError, ValueError):
        return f"{sym}0.00"
    if code == "INR":
        return f"₹{val:,.2f}"
    elif code == "EUR":
        return f"€{val:,.2f}"
    elif code == "GBP":
        return f"£{val:,.2f}"
    elif code == "AED":
        return f"AED {val:,.2f}"
    return f"${val:,.2f}"


def get_product_live_url(product_obj: dict) -> str:
    """
    Returns a live marketplace URL for a product.
    Uses the stored marketplace_url if it looks valid.
    Falls back to an Amazon search URL using the product name — NO hardcoded ASINs.
    """
    url = product_obj.get("marketplace_url", "")
    if url and url.startswith("http"):
        return url
    # Safe fallback: Amazon search by product name
    name = product_obj.get("name", "")
    region = normalize_region(product_obj.get("region", "USA"))
    if region == "India":
        domain = "www.amazon.in"
    elif region == "UK":
        domain = "www.amazon.co.uk"
    elif region == "GCC_MiddleEast":
        domain = "www.amazon.ae"
    elif region in ("Germany",):
        domain = "www.amazon.de"
    elif region in ("France",):
        domain = "www.amazon.fr"
    else:
        domain = "www.amazon.com"
    if name:
        return f"https://{domain}/s?k={quote_plus(name)}"
    return f"https://{domain}"

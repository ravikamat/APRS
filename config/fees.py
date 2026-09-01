"""
Marketplace Fee Schedules (India)
Updated: 2026-09-01
DO NOT use LLM to generate these. Manual verification required.
"""
import math

AMAZON_IN_REFERRAL = {
    "electronics": 0.05,
    "electronics_over_500": 0.07,
    "electronics_over_1000": 0.10,
    "fashion": 0.15,
    "home_kitchen": 0.11,
    "beauty": 0.09,
    "toys": 0.09,
    "sports": 0.09,
    "default": 0.15,
}

AMAZON_IN_CLOSING = {
    "under_300": 6.0,
    "300_500": 12.0,
    "500_1000": 24.0,
    "over_1000": 49.0,
}

FLIPKART_COMMISSION = {
    "electronics": 0.05,
    "fashion": 0.20,
    "home": 0.12,
    "beauty": 0.10,
    "default": 0.15,
}

FLIPKART_FIXED_FEE = {
    "under_300": 5.0,
    "300_500": 10.0,
    "500_1000": 20.0,
    "over_1000": 40.0,
}


def get_amazon_referral_pct(category: str, price: float) -> float:
    """Get Amazon India referral fee percentage as decimal fraction (e.g. 0.05 for 5%)."""
    cat = category.lower()
    if cat == "electronics":
        if price <= 500:
            return AMAZON_IN_REFERRAL["electronics"]
        elif price <= 1000:
            return AMAZON_IN_REFERRAL["electronics_over_500"]
        else:
            return AMAZON_IN_REFERRAL["electronics_over_1000"]
    return AMAZON_IN_REFERRAL.get(cat, AMAZON_IN_REFERRAL["default"])


def get_amazon_closing_fee(price: float) -> float:
    """Get Amazon India closing fee based on price."""
    if price < 300:
        return AMAZON_IN_CLOSING["under_300"]
    elif price <= 500:
        return AMAZON_IN_CLOSING["300_500"]
    elif price <= 1000:
        return AMAZON_IN_CLOSING["500_1000"]
    else:
        return AMAZON_IN_CLOSING["over_1000"]


def get_amazon_fba_fee(weight_kg: float) -> float:
    """Get Amazon India FBA pick/pack fee based on weight (Rs 25 base + Rs 20/kg)."""
    return 25.0 + (20.0 * weight_kg)


def get_flipkart_commission(category: str) -> float:
    """Get Flipkart commission rate as decimal fraction (e.g. 0.05 for 5%)."""
    cat = category.lower()
    return FLIPKART_COMMISSION.get(cat, FLIPKART_COMMISSION["default"])


def get_flipkart_fixed_fee(price: float) -> float:
    """Get Flipkart fixed fee based on price."""
    if price < 300:
        return FLIPKART_FIXED_FEE["under_300"]
    elif price <= 500:
        return FLIPKART_FIXED_FEE["300_500"]
    elif price <= 1000:
        return FLIPKART_FIXED_FEE["500_1000"]
    else:
        return FLIPKART_FIXED_FEE["over_1000"]


def get_meesho_shipping(weight_kg: float) -> float:
    """Get Meesho shipping fee (Rs 45 per 500g)."""
    if weight_kg <= 0:
        return 0.0
    units = math.ceil(weight_kg / 0.5)
    return 45.0 * units

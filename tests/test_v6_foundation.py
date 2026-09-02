"""
tests/test_v6_foundation.py — Unit tests for APRS V6 Pro Foundation modules.
Tests:
- config/fees.py (Marketplace fee calculations)
- core/validation.py (Pydantic RawProduct/CanonicalProduct + ValidationPipeline)
- core/scoring_engine.py (Deterministic scoring rubric)
- core/rule_engine.py (Rule accumulator and safe evaluation)
- tools/review_miner.py (Review parsing and prompt formatting)
"""
import pytest
import sqlite3
from config.fees import (
    get_amazon_referral_pct,
    get_amazon_closing_fee,
    get_amazon_fba_fee,
    get_flipkart_commission,
    get_flipkart_fixed_fee,
    get_meesho_shipping,
)
from core.validation import RawProduct, CanonicalProduct, ProductMatcher, ValidationPipeline
from core.scoring_engine import ScoringEngine, ScoreBreakdown
from core.rule_engine import RuleEngine
from tools.review_miner import ReviewMiner


def test_fees_amazon_calculations():
    # Referral fee
    assert get_amazon_referral_pct("electronics", 400.0) == 0.05
    assert get_amazon_referral_pct("electronics", 800.0) == 0.07
    assert get_amazon_referral_pct("electronics", 1500.0) == 0.10
    assert get_amazon_referral_pct("home_kitchen", 999.0) == 0.11
    assert get_amazon_referral_pct("fashion", 999.0) == 0.15

    # Closing fee
    assert get_amazon_closing_fee(250.0) == 6.0
    assert get_amazon_closing_fee(450.0) == 12.0
    assert get_amazon_closing_fee(850.0) == 24.0
    assert get_amazon_closing_fee(1500.0) == 49.0

    # FBA fee
    assert get_amazon_fba_fee(0.5) == 35.0  # 25 + 0.5*20


def test_fees_flipkart_and_meesho():
    assert get_flipkart_commission("electronics") == 0.05
    assert get_flipkart_commission("fashion") == 0.20
    assert get_flipkart_commission("home") == 0.12
    assert get_flipkart_fixed_fee(250.0) == 5.0
    assert get_flipkart_fixed_fee(1200.0) == 40.0
    assert get_meesho_shipping(0.5) == 45.0
    assert get_meesho_shipping(1.0) == 90.0


def test_validation_raw_product_valid():
    raw = RawProduct(
        marketplace="amazon",
        product_id="B09XYZ1234",
        title="Premium Stainless Steel Garlic Press Rocker",
        price=499.0,
        rating=4.3,
        review_count=120,
        url="https://www.amazon.in/dp/B09XYZ1234",
    )
    assert raw.marketplace == "amazon"
    assert raw.price == 499.0


def test_validation_raw_product_invalid_price():
    with pytest.raises(Exception):
        RawProduct(
            marketplace="amazon",
            product_id="B09XYZ1234",
            title="Stainless Steel Garlic Press Rocker",
            price=-10.0,
            rating=4.3,
            review_count=120,
            url="https://www.amazon.in/dp/B09XYZ1234",
        )


def test_validation_raw_product_placeholder_title():
    with pytest.raises(Exception):
        RawProduct(
            marketplace="amazon",
            product_id="B09XYZ1234",
            title="click here item",
            price=499.0,
            rating=4.3,
            review_count=120,
            url="https://www.amazon.in/dp/B09XYZ1234",
        )


def test_validation_pipeline_deduplication():
    pipeline = ValidationPipeline()
    raw_list = [
        {
            "marketplace": "amazon",
            "product_id": "B01",
            "title": "Kitchen Bamboo Spice Rack Organizer 3 Tier",
            "price": 899.0,
            "rating": 4.5,
            "review_count": 200,
            "url": "https://www.amazon.in/dp/B01",
        },
        {
            "marketplace": "flipkart",
            "product_id": "FK01",
            "title": "Kitchen Bamboo Spice Rack Organizer 3 Tier",
            "price": 849.0,
            "rating": 4.2,
            "review_count": 180,
            "url": "https://www.flipkart.com/p/FK01",
        },
    ]
    valid, errors = pipeline.validate_batch(raw_list)
    assert len(valid) == 2
    assert len(errors) == 0

    canonicals = pipeline.deduplicate(valid)
    assert len(canonicals) == 1
    # Average price is used for canonical products (correct behavior)
    assert canonicals[0].retail_price_inr == 874.0


def test_scoring_engine():
    scorer = ScoringEngine()
    score_pass = scorer.score(
        bsr=5000,
        rating=4.4,
        review_count=150,
        net_margin_pct=32.0,
        has_defects=True,
        competitor_count=4,
    )
    assert score_pass.verdict == "PROCEED"
    assert score_pass.total >= 75.0
    assert score_pass.margin_safety == 40.0

    score_fail = scorer.score(
        bsr=80000,
        rating=3.2,
        review_count=10,
        net_margin_pct=12.0,
        has_defects=False,
        competitor_count=15,
    )
    assert score_fail.verdict == "REJECT"
    assert score_fail.total < 60.0


def test_rule_engine_safe_evaluation():
    re = RuleEngine()

    # Test low review count penalty rule
    product_low_rev = {
        "canonical_title": "Bamboo Rack",
        "category": "home_kitchen",
        "review_count": 15,
        "retail_price_inr": 899.0,
    }
    triggered = re.evaluator.evaluate(product_low_rev)
    assert any(r["rule_id"] == "low_review_count_penalty" for r in triggered)
    penalty_rule = next(r for r in triggered if r["rule_id"] == "low_review_count_penalty")
    assert penalty_rule["action"] == "PENALTY"
    assert penalty_rule["params"]["penalty_points"] == 10

def test_rule_engine_safe_evaluation():
    re = RuleEngine()

    # Test low review count penalty rule
    product_low_rev = {
        "canonical_title": "Bamboo Rack",
        "category": "home_kitchen",
        "review_count": 15,
        "retail_price_inr": 899.0,
    }
    triggered = re.evaluator.evaluate(product_low_rev)
    assert any(r["rule_id"] == "low_review_count_penalty" for r in triggered)
    penalty_rule = next(r for r in triggered if r["rule_id"] == "low_review_count_penalty")
    assert penalty_rule["action"] == "PENALTY"
    assert penalty_rule["params"]["penalty_points"] == 10

    # Test defect fixability bonus rule
    product_silicone = {
        "canonical_title": "Silicone Beauty Blender Sponge",
        "category": "beauty",
        "review_count": 100,
        "retail_price_inr": 299.0,
        "has_defects": True,
        "actionable_defects": 2,
    }
    triggered_silicone = re.evaluator.evaluate(product_silicone)
    assert any(r["rule_id"] == "defect_fixability_bonus" for r in triggered_silicone)
    bonus_rule = next(r for r in triggered_silicone if r["rule_id"] == "defect_fixability_bonus")
    assert bonus_rule["action"] == "BOOST"
    assert bonus_rule["params"]["bonus_points"] == 10
    miner = ReviewMiner()
    sample_json = '{"defects":[{"defect":"Handle breaks under load","frequency":"common","severity":"critical","suggested_fix":"Reinforce joint"}],"v2_spec":{"improvement_1":"Thicker handle"}}'
    result = miner._parse_json_response(sample_json)
    assert len(result["defects"]) == 1
    assert result["defects"][0]["defect"] == "Handle breaks under load"
    assert result["v2_spec"]["improvement_1"] == "Thicker handle"

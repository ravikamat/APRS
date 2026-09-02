"""
tests/test_economics_engine.py — Unit tests for 15-Factor Economics Engine.
Tests scenario calculations, Gate 3 passes_gate(), and full evaluation.
"""
import pytest
from core.economics_engine import Comprehensive15FactorEconomics
from core.scoring_engine import ScoringEngine, ScoreBreakdown
from core.models import ScenarioEconomics, EconomicsAssessment


class TestComprehensive15FactorEconomics:
    """Tests for the 15-Factor Economics Engine."""
    
    def test_calculate_scenario_expected(self):
        """Test Expected scenario calculation."""
        scenario = Comprehensive15FactorEconomics.calculate_scenario(
            scenario_name="Expected",
            fob_price=350.0,
            planned_msrp=1299.0,
            region="India",
            category="Kitchen",
            marketplace="amazon",
        )
        
        assert isinstance(scenario, ScenarioEconomics)
        assert scenario.scenario_name == "Expected"
        assert scenario.planned_msrp == 1299.0
        assert scenario.fob_price == 350.0
        assert scenario.landed_cogs > 0
        assert scenario.gross_margin_pct > 0
        assert scenario.net_profit_pct > 0
        assert scenario.status in ("PASS", "FAIL")
    
    def test_calculate_scenario_conservative(self):
        """Test Conservative scenario applies penalties."""
        conservative = Comprehensive15FactorEconomics.calculate_scenario(
            scenario_name="Conservative",
            fob_price=350.0,
            planned_msrp=1299.0,
            region="India",
            category="Kitchen",
            marketplace="amazon",
        )
        
        expected = Comprehensive15FactorEconomics.calculate_scenario(
            scenario_name="Expected",
            fob_price=350.0,
            planned_msrp=1299.0,
            region="India",
            category="Kitchen",
            marketplace="amazon",
        )
        
        # Conservative should have higher FOB and lower MSRP
        assert conservative.fob_price > expected.fob_price
        assert conservative.planned_msrp < expected.planned_msrp
        # Conservative should have lower or equal net margin
        assert conservative.net_profit_pct <= expected.net_profit_pct
    
    def test_calculate_scenario_upside(self):
        """Test Upside scenario applies benefits."""
        upside = Comprehensive15FactorEconomics.calculate_scenario(
            scenario_name="Upside",
            fob_price=350.0,
            planned_msrp=1299.0,
            region="India",
            category="Kitchen",
            marketplace="amazon",
        )
        
        expected = Comprehensive15FactorEconomics.calculate_scenario(
            scenario_name="Expected",
            fob_price=350.0,
            planned_msrp=1299.0,
            region="India",
            category="Kitchen",
            marketplace="amazon",
        )
        
        # Upside should have lower FOB and higher MSRP
        assert upside.fob_price < expected.fob_price
        assert upside.planned_msrp > expected.planned_msrp
        # Upside should have higher or equal net margin
        assert upside.net_profit_pct >= expected.net_profit_pct
    
    def test_passes_gate_success(self):
        """Test Gate 3 pass for viable product."""
        passes, details = Comprehensive15FactorEconomics.passes_gate(
            fob_price=350.0,
            planned_msrp=1299.0,
            region="India",
            category="Kitchen",
            marketplace="amazon",
            min_margin_pct=15.0,  # Updated to match actual fee structure (11% referral)
        )
        
        assert passes is True
        assert details["gate_passed"] is True
        assert details["expected"]["net_margin_pct"] >= 15.0
        assert details["expected"]["gross_margin_pct"] >= 50.0
    
    def test_passes_gate_failure_high_fob(self):
        """Test Gate 3 fail for high FOB (low margin)."""
        passes, details = Comprehensive15FactorEconomics.passes_gate(
            fob_price=600.0,
            planned_msrp=1299.0,
            region="India",
            category="Kitchen",
            marketplace="amazon",
            min_margin_pct=20.0,
        )
        
        assert passes is False
        assert details["gate_passed"] is False
        assert details["expected"]["net_margin_pct"] < 20.0
    
    def test_passes_gate_failure_low_msrp(self):
        """Test Gate 3 fail for low MSRP."""
        passes, details = Comprehensive15FactorEconomics.passes_gate(
            fob_price=350.0,
            planned_msrp=800.0,
            region="India",
            category="Kitchen",
            marketplace="amazon",
            min_margin_pct=20.0,
        )
        
        assert passes is False
    
    def test_evaluate_15_factor_economics(self):
        """Test full 3-scenario evaluation."""
        result = Comprehensive15FactorEconomics.evaluate_15_factor_economics(
            product_id="TEST001",
            fob_price=350.0,
            planned_msrp=1299.0,
            region="India",
            category="Kitchen",
            marketplace="amazon",
        )
        
        assert isinstance(result, EconomicsAssessment)
        assert result.product_id == "TEST001"
        assert result.region == "India"
        assert result.currency == "INR"
        assert hasattr(result, "conservative")
        assert hasattr(result, "expected")
        assert hasattr(result, "upside")
        assert result.recommendation in ("PASS", "FAIL")
        assert 0 <= result.composite_score <= 100
        assert 0 <= result.lead_time_risk_factor <= 1.0
    
    def test_evaluate_lead_time_fail(self):
        """Test lead time failure (lead time > 70% of trend half-life)."""
        result = Comprehensive15FactorEconomics.evaluate_15_factor_economics(
            product_id="TEST002",
            fob_price=350.0,
            planned_msrp=1299.0,
            region="India",
            category="Kitchen",
            marketplace="amazon",
            lead_time_days=80,
            trend_half_life_days=90,  # 80 > 90 * 0.7 = 63
        )
        
        assert result.lead_time_risk_factor > 0.7
        assert result.is_financially_viable is False
        assert result.recommendation == "FAIL"
    
    def test_different_marketplaces(self):
        """Test economics with different marketplaces."""
        # Use categories with different fee structures
        amazon_result = Comprehensive15FactorEconomics.calculate_scenario(
            scenario_name="Expected",
            fob_price=350.0,
            planned_msrp=1299.0,
            region="India",
            category="electronics",  # Amazon: 10% (over 1000), Flipkart: 5%
            marketplace="amazon",
        )
        
        flipkart_result = Comprehensive15FactorEconomics.calculate_scenario(
            scenario_name="Expected",
            fob_price=350.0,
            planned_msrp=1299.0,
            region="India",
            category="electronics",
            marketplace="flipkart",
        )
        
        # Different marketplaces should have different fee structures
        assert amazon_result.marketplace_commission != flipkart_result.marketplace_commission
        assert amazon_result.fulfillment_fee != flipkart_result.fulfillment_fee
        # Amazon electronics > 1000: 10%, Flipkart electronics: 5%
        assert amazon_result.marketplace_commission > flipkart_result.marketplace_commission
    
    def test_different_regions(self):
        """Test economics for different regions."""
        india_result = Comprehensive15FactorEconomics.evaluate_15_factor_economics(
            product_id="TEST_IN",
            fob_price=350.0,
            planned_msrp=1299.0,
            region="India",
            category="Kitchen",
        )
        
        usa_result = Comprehensive15FactorEconomics.evaluate_15_factor_economics(
            product_id="TEST_US",
            fob_price=4.20,  # USD
            planned_msrp=15.99,  # USD
            region="USA",
            category="Kitchen",
        )
        
        assert india_result.currency == "INR"
        assert usa_result.currency == "USD"
        # India has COD fees, USA doesn't
        assert india_result.expected.payment_or_cod_fee > usa_result.expected.payment_or_cod_fee
    
    def test_volumetric_weight(self):
        """Test volumetric weight calculation."""
        # Large but light product
        scenario = Comprehensive15FactorEconomics.calculate_scenario(
            scenario_name="Expected",
            fob_price=350.0,
            planned_msrp=1299.0,
            region="India",
            category="Kitchen",
            length_cm=50.0,
            width_cm=40.0,
            height_cm=30.0,
            actual_weight_kg=0.5,  # Light but bulky
        )
        
        # Volumetric weight = 50*40*30/5000 = 12kg > 0.5kg actual
        # So chargeable weight should be 12kg
        assert scenario.volumetric_freight_cost > 0
    
    def test_mold_amortization(self):
        """Test mold tooling cost amortization."""
        scenario = Comprehensive15FactorEconomics.calculate_scenario(
            scenario_name="Expected",
            fob_price=350.0,
            planned_msrp=1299.0,
            region="India",
            category="Kitchen",
            mold_tooling_cost=50000.0,  # 50k INR mold
            moq_units=300,
        )
        
        # Amortized over max(1000, 300*3) = 1000 units
        # 50000 / 1000 = 50 per unit
        assert scenario.landed_cogs > 350  # FOB + mold_per_unit + other costs


class TestScoringEngine:
    """Tests for deterministic scoring engine (already tested in validation schemas)."""
    
    def test_score_components(self):
        """Test individual score components."""
        engine = ScoringEngine()
        result = engine.score(
            bsr=10000,
            rating=4.5,
            review_count=200,
            net_margin_pct=30.0,
            has_defects=True,
            competitor_count=3,
        )
        
        assert result.market_signal == 20.0  # 25 - (10000/2000) = 20
        assert result.review_quality == 20.0  # rating >= 4.2 & reviews >= 100
        assert result.margin_safety == 40.0  # >= 30%
        assert result.defect_fixability == 10.0  # has defects
        assert result.competition_density == 5.0  # <= 5
        assert result.total == 95.0
        assert result.verdict == "PROCEED"
    
    def test_score_thresholds(self):
        """Test score thresholds match rubric."""
        engine = ScoringEngine()
        
        # PROCEED: >= 75
        result = engine.score(bsr=5000, rating=4.5, review_count=200, net_margin_pct=30, has_defects=True, competitor_count=3)
        assert result.verdict == "PROCEED"
        assert result.total >= 75
        
        # MARGINAL: >= 60, < 75
        result = engine.score(bsr=25000, rating=4.0, review_count=80, net_margin_pct=22, has_defects=True, competitor_count=8)
        assert result.verdict == "MARGINAL"
        assert 60 <= result.total < 75
        
        # REJECT: < 60
        result = engine.score(bsr=50000, rating=3.5, review_count=30, net_margin_pct=15, has_defects=False, competitor_count=15)
        assert result.verdict == "REJECT"
        assert result.total < 60
    
    def test_missing_bsr(self):
        """Test missing BSR gets default market signal."""
        engine = ScoringEngine()
        result = engine.score(bsr=None, rating=4.5, review_count=200, net_margin_pct=30, has_defects=True, competitor_count=3)
        assert result.market_signal == 20.0


class TestFeeIntegration:
    """Tests that config/fees.py is properly integrated."""
    
    def test_amazon_referral_fee(self):
        from config.fees import get_amazon_referral_pct
        # Electronics < 500: 5% (0.05)
        assert get_amazon_referral_pct("electronics", 400) == 0.05
        # Electronics 500-1000: 7% (0.07)
        assert get_amazon_referral_pct("electronics", 750) == 0.07
        # Electronics > 1000: 10% (0.10)
        assert get_amazon_referral_pct("electronics", 1500) == 0.10
        # Fashion: 15% (0.15)
        assert get_amazon_referral_pct("fashion", 1000) == 0.15
    
    def test_amazon_closing_fee(self):
        from config.fees import get_amazon_closing_fee
        assert get_amazon_closing_fee(200) == 6.0
        assert get_amazon_closing_fee(400) == 12.0
        assert get_amazon_closing_fee(750) == 24.0
        assert get_amazon_closing_fee(1500) == 49.0
    
    def test_amazon_fba_fee(self):
        from config.fees import get_amazon_fba_fee
        # Base 25 + 20 * weight
        assert get_amazon_fba_fee(0.5) == 35.0  # 25 + 20*0.5
        assert get_amazon_fba_fee(1.0) == 45.0
        assert get_amazon_fba_fee(2.0) == 65.0
    
    def test_flipkart_commission(self):
        from config.fees import get_flipkart_commission
        assert get_flipkart_commission("electronics") == 0.05
        assert get_flipkart_commission("fashion") == 0.20
        assert get_flipkart_commission("home") == 0.12
        assert get_flipkart_commission("beauty") == 0.10
    
    def test_flipkart_fixed_fee(self):
        from config.fees import get_flipkart_fixed_fee
        assert get_flipkart_fixed_fee(200) == 5.0
        assert get_flipkart_fixed_fee(400) == 10.0
        assert get_flipkart_fixed_fee(750) == 20.0
        assert get_flipkart_fixed_fee(1500) == 40.0
    
    def test_meesho_shipping(self):
        from config.fees import get_meesho_shipping
        # Rs 45 per 500g
        assert get_meesho_shipping(0.25) == 45.0  # 1 unit
        assert get_meesho_shipping(0.5) == 45.0   # 1 unit
        assert get_meesho_shipping(0.75) == 90.0  # 2 units
        assert get_meesho_shipping(1.0) == 90.0   # 2 units


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
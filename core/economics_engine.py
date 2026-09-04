"""
core/economics_engine.py — Advanced 15-Factor 3-Scenario Unit Economics Engine for APRS V6 Pro.

Calculates:
- Conservative, Expected, and Upside scenarios simultaneously.
- Volumetric freight calculation: max(Actual Weight, L x W x H / 5000) * Freight Rate.
- Lead-time vs. Trend decay velocity penalty.
- Realistic Indian & Global marketplace schedules (Amazon, Flipkart, Meesho, D2C).
- COD fees, RTO reserves, return fraud/wardrobing buffers, and net contribution margins.

Gate 3 Integration: passes_gate(min_margin_pct=20.0) -> bool
"""
from typing import Dict, Any, Optional, Tuple
import math
from config.settings import REGIONAL_PROFILES, settings
from config.fees import (
    get_amazon_referral_pct, get_amazon_closing_fee, get_amazon_fba_fee,
    get_flipkart_commission, get_flipkart_fixed_fee, get_meesho_shipping,
)
from core.models import ScenarioEconomics, EconomicsAssessment


class Comprehensive15FactorEconomics:
    """
    15-Factor 3-Scenario Unit Economics Engine.
    Evaluates Conservative, Expected, and Upside contribution margins.
    """
    
    # Category RTO and return fraud benchmarks (India / Global)
    CATEGORY_RTO_RATES = {
        "Apparel": 0.28,
        "Beauty": 0.18,
        "Kitchen": 0.14,
        "Home": 0.15,
        "Electronics": 0.12,
        "Fitness": 0.15,
        "General": 0.16
    }
    
    # Packaging costs by currency
    PACKAGING_COST = {"INR": 25.0, "USD": 0.40, "EUR": 0.35, "GBP": 0.30}
    
    # Freight rates per kg by currency
    FREIGHT_RATE_PER_KG = {"INR": 75.0, "USD": 4.50, "EUR": 4.20, "GBP": 3.80}
    
    # FBA/3PL fulfillment fee base + per kg
    FULFILLMENT_FEE = {
        "INR": {"base": 55.0, "per_kg": 20.0},
        "USD": {"base": 3.50, "per_kg": 1.20},
        "EUR": {"base": 3.20, "per_kg": 1.10},
        "GBP": {"base": 2.80, "per_kg": 1.00},
    }
    
    # Payment gateway fees
    PAYMENT_FEE = {
        "India": {"prepaid_pct": 0.02, "cod_fixed": 38.0, "cod_pct": 0.02, "cod_split": 0.60},
        "USA": {"prepaid_pct": 0.029, "fixed_usd": 0.30},
        "Europe": {"prepaid_pct": 0.025, "fixed_eur": 0.25},
        "UK": {"prepaid_pct": 0.025, "fixed_gbp": 0.20},
        "GCC_MiddleEast": {"prepaid_pct": 0.029, "fixed_usd": 0.30},
    }
    
    # Return fraud buffer by category
    FRAUD_BUFFER_PCT = {"Apparel": 0.08, "General": 0.04}
    
    # Damage & defect reserve
    DAMAGE_RESERVE_PCT = 0.03
    
    # ITC credit ratio for GST
    ITC_CREDIT_RATIO = 0.85
    
    # Lead time pass threshold (must arrive within 70% of trend half-life)
    LEAD_TIME_THRESHOLD_PCT = 0.70

    # Live USD/INR rate from OpenBB (updated via set_live_rate)
    _live_usd_inr_rate: float = 83.0  # default fallback

    @classmethod
    def set_live_rate(cls, rate: float) -> None:
        """Update live USD/INR rate from OpenBB MCP.
        
        Called by OpenBB client when fetching fresh rates.
        """
        cls._live_usd_inr_rate = max(1.0, rate)  # prevent invalid rates
        # Also update REGIONAL_PROFILES for India
        try:
            from config.settings import REGIONAL_PROFILES
            if "India" in REGIONAL_PROFILES:
                REGIONAL_PROFILES["India"]["usd_inr_rate"] = cls._live_usd_inr_rate
        except Exception:
            pass  # settings may not be loaded yet
    
    @classmethod
    def get_live_rate(cls) -> float:
        """Get current live USD/INR rate."""
        return cls._live_usd_inr_rate

    @classmethod
    def _get_marketplace_commission(cls, category: str, msrp: float, marketplace: str = "amazon") -> float:
        """Get marketplace commission using config/fees.py."""
        if marketplace == "amazon":
            return msrp * get_amazon_referral_pct(category, msrp)
        elif marketplace == "flipkart":
            return msrp * get_flipkart_commission(category)
        elif marketplace == "meesho":
            # Meesho uses shipping-based model, commission ~5-10%
            return msrp * 0.08
        return msrp * 0.13  # Default
    
    @classmethod
    def _get_fulfillment_fee(cls, chargeable_weight_kg: float, currency: str, marketplace: str = "amazon") -> float:
        """Get fulfillment fee using config/fees.py for Amazon."""
        if marketplace == "amazon" and currency == "INR":
            return get_amazon_fba_fee(chargeable_weight_kg)
        fee_config = cls.FULFILLMENT_FEE.get(currency, cls.FULFILLMENT_FEE["INR"])
        return fee_config["base"] + (chargeable_weight_kg * fee_config["per_kg"])
    
    @classmethod
    def _get_payment_fee(cls, msrp: float, region: str, currency: str, is_cod: bool = True) -> float:
        """Get payment gateway / COD fee."""
        fee_config = cls.PAYMENT_FEE.get(region, cls.PAYMENT_FEE["India"])
        
        if region == "India" and is_cod:
            cod_split = fee_config.get("cod_split", 0.60)
            prepaid_pct = fee_config.get("prepaid_pct", 0.02)
            cod_fixed = fee_config.get("cod_fixed", 38.0)
            cod_pct = fee_config.get("cod_pct", 0.02)
            return (cod_split * (cod_fixed + msrp * cod_pct)) + ((1 - cod_split) * msrp * prepaid_pct)
        else:
            prepaid_pct = fee_config.get("prepaid_pct", 0.029)
            fixed = fee_config.get("fixed_usd", 0.30) if currency == "USD" else fee_config.get("fixed_eur", 0.25)
            return msrp * prepaid_pct + fixed
    
    @classmethod
    def _get_rto_rate(cls, category: str, scenario_name: str) -> float:
        """Get RTO rate for category and scenario."""
        base_rto = cls.CATEGORY_RTO_RATES.get(category, 0.16)
        if scenario_name == "Conservative":
            return base_rto * 1.25
        elif scenario_name == "Upside":
            return base_rto * 0.85
        return base_rto
    
    @classmethod
    def calculate_scenario(
        cls,
        scenario_name: str,
        fob_price: float,
        planned_msrp: float,
        region: str = "India",
        category: str = "General",
        marketplace: str = "amazon",
        length_cm: float = 20.0,
        width_cm: float = 15.0,
        height_cm: float = 10.0,
        actual_weight_kg: float = 0.5,
        moq_units: int = 300,
        mold_tooling_cost: float = 0.0,
        est_ad_tacos_pct: float = 0.18,
        lead_time_days: int = 30,
        trend_half_life_days: int = 90
    ) -> ScenarioEconomics:
        """Calculates a single scenario economics breakdown."""
        reg_cfg = REGIONAL_PROFILES.get(region, REGIONAL_PROFILES.get("India", {}))
        currency = reg_cfg.get("currency", "INR")
        gst_rate = reg_cfg.get("gst_vat_rate", 0.18)
        
        # Scenario Multipliers
        if scenario_name == "Conservative":
            msrp = planned_msrp * 0.92
            fob = fob_price * 1.10
            tacos = min(0.35, est_ad_tacos_pct * 1.30)
            rto_rate_mult = 1.25
        elif scenario_name == "Upside":
            msrp = planned_msrp * 1.08
            fob = fob_price * 0.90
            tacos = max(0.10, est_ad_tacos_pct * 0.80)
            rto_rate_mult = 0.85
        else:  # Expected
            msrp = planned_msrp
            fob = fob_price
            tacos = est_ad_tacos_pct
            rto_rate_mult = 1.0
        
        # Factor 1: FOB (already adjusted above)
        # Factor 2: Mold/Tooling amortization
        amortized_units = max(1000, moq_units * 3)
        mold_per_unit = mold_tooling_cost / amortized_units if mold_tooling_cost > 0 else 0.0
        
        # Factor 3: Packaging & Inserts
        packaging_cost = cls.PACKAGING_COST.get(currency, 25.0)
        
        # Factor 4: Volumetric Freight Calculation
        volumetric_weight_kg = (length_cm * width_cm * height_cm) / 5000.0
        chargeable_weight_kg = max(actual_weight_kg, volumetric_weight_kg)
        freight_rate = cls.FREIGHT_RATE_PER_KG.get(currency, 75.0)
        volumetric_freight = chargeable_weight_kg * freight_rate
        
        # Factor 5: Inbound Customs / Regional Tariff
        tariff_rate = 0.0 if region == "India" else 0.075
        customs_duty = fob * tariff_rate
        
        # Landed COGS
        landed_cogs = fob + packaging_cost + volumetric_freight + customs_duty + mold_per_unit
        gross_profit = max(0.0, msrp - landed_cogs)
        gross_margin_pct = (gross_profit / msrp * 100.0) if msrp > 0 else 0.0
        
        # Factor 6: Marketplace Commission (from config/fees.py)
        marketplace_commission = cls._get_marketplace_commission(category, msrp, marketplace)
        
        # Factor 7: FBA / 3PL Fulfillment Fee (from config/fees.py for Amazon)
        fulfillment_fee = cls._get_fulfillment_fee(chargeable_weight_kg, currency, marketplace)
        
        # Factor 8: Payment Gateway / COD Fee
        payment_or_cod_fee = cls._get_payment_fee(msrp, region, currency, is_cod=True)
        
        # Factor 9: RTO Reserve
        base_rto_pct = cls._get_rto_rate(category, scenario_name)
        reverse_shipping_cost = fulfillment_fee * 1.15
        rto_reserve = base_rto_pct * reverse_shipping_cost if region == "India" else base_rto_pct * (fulfillment_fee * 0.5)
        
        # Factor 10: Return Fraud & Customer Wardrobing Reserve
        fraud_buffer = cls.FRAUD_BUFFER_PCT.get(category, 0.04)
        return_fraud_reserve = msrp * fraud_buffer
        
        # Factor 11: Ad Spend (TACoS)
        ad_tacos_reserve = msrp * tacos
        
        # Factor 12: Damage & Defect Reserve
        damage_reserve = landed_cogs * cls.DAMAGE_RESERVE_PCT
        
        # Factor 13: Net GST / Tax Burden
        output_tax = msrp * (gst_rate / (1.0 + gst_rate))
        itc_credit = (landed_cogs + fulfillment_fee + marketplace_commission + ad_tacos_reserve) * (gst_rate / (1.0 + gst_rate)) * cls.ITC_CREDIT_RATIO
        net_tax_burden = max(0.0, output_tax - itc_credit)
        
        # Factor 14: Closing Fee (Amazon specific)
        closing_fee = get_amazon_closing_fee(msrp) if marketplace == "amazon" and currency == "INR" else 0.0
        
        # Factor 15: Fixed Fee (Flipkart specific)
        fixed_fee = get_flipkart_fixed_fee(msrp) if marketplace == "flipkart" and currency == "INR" else 0.0
        
        # Total Variable Costs
        total_variable_cost = (
            landed_cogs + marketplace_commission + fulfillment_fee +
            payment_or_cod_fee + rto_reserve + return_fraud_reserve +
            ad_tacos_reserve + damage_reserve + net_tax_burden +
            closing_fee + fixed_fee
        )
        
        net_profit = msrp - total_variable_cost
        net_profit_pct = (net_profit / msrp * 100.0) if msrp > 0 else 0.0
        contribution_margin = net_profit
        
        # Capital required for first batch
        first_batch_capital = (moq_units * landed_cogs) + (moq_units * ad_tacos_reserve * 0.5)
        
        # Gate 3 Pass Criteria: Net Margin >= threshold AND Gross Margin >= 50%
        # Threshold comes from settings (default 20% for Gate 3)
        pass_threshold = getattr(settings, 'gate3_min_margin_pct', 20.0)
        if scenario_name == "Conservative":
            pass_threshold = max(pass_threshold, 15.0)  # Stricter for conservative
        elif scenario_name == "Upside":
            pass_threshold = max(pass_threshold, 25.0)
        
        status = "PASS" if (net_profit_pct >= pass_threshold and gross_margin_pct >= 50.0) else "FAIL"
        
        return ScenarioEconomics(
            scenario_name=scenario_name,
            planned_msrp=round(msrp, 2),
            fob_price=round(fob, 2),
            landed_cogs=round(landed_cogs, 2),
            gross_profit=round(gross_profit, 2),
            gross_margin_pct=round(gross_margin_pct, 2),
            volumetric_freight_cost=round(volumetric_freight, 2),
            marketplace_commission=round(marketplace_commission, 2),
            fulfillment_fee=round(fulfillment_fee, 2),
            payment_or_cod_fee=round(payment_or_cod_fee, 2),
            rto_reserve=round(rto_reserve, 2),
            return_fraud_reserve=round(return_fraud_reserve, 2),
            ad_tacos_reserve=round(ad_tacos_reserve, 2),
            net_tax_burden=round(net_tax_burden, 2),
            total_variable_cost=round(total_variable_cost, 2),
            net_profit=round(net_profit, 2),
            net_profit_pct=round(net_profit_pct, 2),
            contribution_margin=round(contribution_margin, 2),
            first_batch_capital=round(first_batch_capital, 2),
            status=status
        )

    @classmethod
    def passes_gate(
        cls,
        fob_price: float,
        planned_msrp: float,
        region: str = "India",
        category: str = "General",
        marketplace: str = "amazon",
        min_margin_pct: float = 20.0,
        **kwargs
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Gate 3 Check: Does this product pass the economics gate?
        
        Args:
            fob_price: Factory FOB price
            planned_msrp: Planned retail price
            region: Target region
            category: Product category
            marketplace: Target marketplace
            min_margin_pct: Minimum net margin percentage to pass (default 20%)
            **kwargs: Additional parameters passed to calculate_scenario
        
        Returns:
            Tuple of (passes: bool, details: dict with scenario results)
        """
        # Run Expected scenario (primary gate check)
        expected = cls.calculate_scenario(
            scenario_name="Expected",
            fob_price=fob_price,
            planned_msrp=planned_msrp,
            region=region,
            category=category,
            marketplace=marketplace,
            **kwargs
        )
        
        # Also check Conservative for safety
        conservative = cls.calculate_scenario(
            scenario_name="Conservative",
            fob_price=fob_price,
            planned_msrp=planned_msrp,
            region=region,
            category=category,
            marketplace=marketplace,
            **kwargs
        )
        
        passes = (
            (expected.net_profit_pct >= min_margin_pct and expected.gross_margin_pct >= 50.0) or
            (conservative.net_profit_pct >= min_margin_pct * 0.75 and conservative.gross_margin_pct >= 45.0)
        )
        
        return passes, {
            "expected": {
                "net_margin_pct": expected.net_profit_pct,
                "gross_margin_pct": expected.gross_margin_pct,
                "status": expected.status,
                "landed_cogs": expected.landed_cogs,
                "total_variable_cost": expected.total_variable_cost,
            },
            "conservative": {
                "net_margin_pct": conservative.net_profit_pct,
                "gross_margin_pct": conservative.gross_margin_pct,
                "status": conservative.status,
            },
            "gate_passed": passes,
            "min_margin_required": min_margin_pct,
        }

    @classmethod
    def evaluate_15_factor_economics(
        cls,
        product_id: str,
        fob_price: float,
        planned_msrp: float,
        region: str = "India",
        category: str = "General",
        marketplace: str = "amazon",
        length_cm: float = 20.0,
        width_cm: float = 15.0,
        height_cm: float = 10.0,
        actual_weight_kg: float = 0.5,
        moq_units: int = 300,
        mold_tooling_cost: float = 0.0,
        est_ad_tacos_pct: float = 0.18,
        lead_time_days: int = 30,
        trend_half_life_days: int = 90
    ) -> EconomicsAssessment:
        """
        Generates complete 15-factor 3-scenario economics assessment.
        Factor 15: Rejects products if Lead Time > Trend Half Life * threshold.
        """
        reg_cfg = REGIONAL_PROFILES.get(region, REGIONAL_PROFILES.get("India", {}))
        currency = reg_cfg.get("currency", "INR")
        
        common_kwargs = {
            "region": region,
            "category": category,
            "marketplace": marketplace,
            "length_cm": length_cm,
            "width_cm": width_cm,
            "height_cm": height_cm,
            "actual_weight_kg": actual_weight_kg,
            "moq_units": moq_units,
            "mold_tooling_cost": mold_tooling_cost,
            "est_ad_tacos_pct": est_ad_tacos_pct,
            "lead_time_days": lead_time_days,
            "trend_half_life_days": trend_half_life_days,
        }
        
        cons = cls.calculate_scenario(scenario_name="Conservative", fob_price=fob_price, planned_msrp=planned_msrp, **common_kwargs)
        exp = cls.calculate_scenario(scenario_name="Expected", fob_price=fob_price, planned_msrp=planned_msrp, **common_kwargs)
        ups = cls.calculate_scenario(scenario_name="Upside", fob_price=fob_price, planned_msrp=planned_msrp, **common_kwargs)
        
        # Factor 15: Lead Time Risk Check
        lead_time_risk_factor = min(1.0, lead_time_days / float(max(1, trend_half_life_days)))
        lead_time_pass = lead_time_days <= (trend_half_life_days * cls.LEAD_TIME_THRESHOLD_PCT)
        
        # Gate 3 viability: Expected or Conservative must pass, AND lead time must pass
        min_margin = getattr(settings, 'gate3_min_margin_pct', 20.0)
        is_financially_viable = (
            (exp.net_profit_pct >= min_margin and exp.gross_margin_pct >= 50.0) or
            (cons.net_profit_pct >= min_margin * 0.75 and cons.gross_margin_pct >= 45.0)
        ) and lead_time_pass
        
        # Composite score
        score_base = (exp.net_profit_pct * 2.5) + (exp.gross_margin_pct * 0.5)
        if not lead_time_pass:
            score_base -= 25.0
        composite_score = max(0.0, min(100.0, score_base))
        
        recommendation = "PASS" if is_financially_viable else "FAIL"
        
        return EconomicsAssessment(
            product_id=product_id,
            region=region,
            currency=currency,
            conservative=cons,
            expected=exp,
            upside=ups,
            lead_time_days=lead_time_days,
            trend_half_life_days=trend_half_life_days,
            lead_time_risk_factor=round(lead_time_risk_factor, 2),
            is_financially_viable=is_financially_viable,
            composite_score=round(composite_score, 1),
            recommendation=recommendation
        )


if __name__ == "__main__":
    # Quick test
    result = Comprehensive15FactorEconomics.evaluate_15_factor_economics(
        product_id="TEST001",
        fob_price=350.0,
        planned_msrp=1299.0,
        region="India",
        category="Kitchen",
        marketplace="amazon",
    )
    print(f"Recommendation: {result.recommendation}")
    print(f"Composite Score: {result.composite_score}")
    print(f"Expected Net Margin: {result.expected.net_profit_pct}%")
    print(f"Conservative Net Margin: {result.conservative.net_profit_pct}%")
    print(f"Lead Time Pass: {result.lead_time_risk_factor < 0.7}")
    
    # Test passes_gate
    passes, details = Comprehensive15FactorEconomics.passes_gate(
        fob_price=350.0,
        planned_msrp=1299.0,
        region="India",
        category="Kitchen",
        marketplace="amazon",
        min_margin_pct=20.0,
    )
    print(f"\nGate 3 Pass: {passes}")
    print(f"Details: {details}")
"""
core/economics_engine.py — Advanced 15-Factor 3-Scenario Unit Economics Engine for APRS V6 Pro.

Calculates:
- Conservative, Expected, and Upside scenarios simultaneously.
- Volumetric freight calculation: max(Actual Weight, L x W x H / 5000) * Freight Rate.
- Lead-time vs. Trend decay velocity penalty.
- Realistic Indian & Global marketplace schedules (Amazon, Flipkart, Meesho, D2C).
- COD fees, RTO reserves, return fraud/wardrobing buffers, and net contribution margins.
"""
from typing import Dict, Any, Optional
import math
from config.settings import REGIONAL_PROFILES
from core.models import ScenarioEconomics, EconomicsAssessment


class Comprehensive15FactorEconomics:
    """
    15-Factor 3-Scenario Unit Economics Engine.
    Evaluates Conservative, Expected, and Upside contribution margins.
    """

    # Category commission benchmarks
    COMMISSION_RATES = {
        "Kitchen": 0.12,
        "Home": 0.135,
        "Beauty": 0.10,
        "Electronics": 0.08,
        "Fitness": 0.12,
        "Apparel": 0.17,
        "General": 0.13
    }

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

    @classmethod
    def calculate_scenario(
        cls,
        scenario_name: str,
        fob_price: float,
        planned_msrp: float,
        region: str = "India",
        category: str = "General",
        length_cm: float = 20.0,
        width_cm: float = 15.0,
        height_cm: float = 10.0,
        actual_weight_kg: float = 0.5,
        moq_units: int = 300,
        mold_tooling_cost: float = 0.0,
        est_ad_tacos_pct: float = 0.18,
        is_cod: bool = True,
        lead_time_days: int = 30,
        trend_half_life_days: int = 90
    ) -> ScenarioEconomics:
        """Calculates a single scenario economics breakdown."""
        reg_cfg = REGIONAL_PROFILES.get(region, REGIONAL_PROFILES.get("India", {}))
        currency = reg_cfg.get("currency", "INR")
        gst_rate = reg_cfg.get("gst_vat_rate", 0.18)

        # Scenario Multipliers
        if scenario_name == "Conservative":
            msrp = planned_msrp * 0.92  # 8% price depression from competitors
            fob = fob_price * 1.10      # 10% higher raw material/BOM cost
            tacos = min(0.35, est_ad_tacos_pct * 1.30)
            rto_rate_mult = 1.25
        elif scenario_name == "Upside":
            msrp = planned_msrp * 1.08  # Premium packaging / brand power
            fob = fob_price * 0.90      # Volume discounts at scale
            tacos = max(0.10, est_ad_tacos_pct * 0.80)
            rto_rate_mult = 0.85
        else:  # Expected
            msrp = planned_msrp
            fob = fob_price
            tacos = est_ad_tacos_pct
            rto_rate_mult = 1.0

        # Factor 3: Packaging & Inserts
        packaging_cost = 25.0 if currency == "INR" else 0.40

        # Factor 4: Volumetric Freight Calculation
        volumetric_weight_kg = (length_cm * width_cm * height_cm) / 5000.0
        chargeable_weight_kg = max(actual_weight_kg, volumetric_weight_kg)
        freight_rate_per_kg = 75.0 if currency == "INR" else 4.50  # Domestic / Sea Freight
        volumetric_freight = chargeable_weight_kg * freight_rate_per_kg

        # Factor 5: Inbound Customs / Regional Tariff
        tariff_rate = 0.0 if region == "India" else 0.075  # 7.5% for international ocean freight
        customs_duty = fob * tariff_rate

        # Factor 13: Mold / Tooling Amortization per unit
        amortized_units = max(1000, moq_units * 3)
        mold_per_unit = mold_tooling_cost / amortized_units if mold_tooling_cost > 0 else 0.0

        # Landed COGS
        landed_cogs = fob + packaging_cost + volumetric_freight + customs_duty + mold_per_unit
        gross_profit = max(0.0, msrp - landed_cogs)
        gross_margin_pct = (gross_profit / msrp * 100.0) if msrp > 0 else 0.0

        # Factor 6: Marketplace Commission
        comm_pct = cls.COMMISSION_RATES.get(category, 0.13)
        marketplace_commission = msrp * comm_pct

        # Factor 7: FBA / 3PL Fulfillment Fee
        if currency == "INR":
            fulfillment_fee = 55.0 + (chargeable_weight_kg * 20.0)
        else:
            fulfillment_fee = 3.50 + (chargeable_weight_kg * 1.20)

        # Factor 8: Payment Gateway / COD Fee
        if region == "India":
            # 60% COD, 40% Prepaid
            payment_or_cod_fee = (0.40 * (msrp * 0.02)) + (0.60 * (38.0 + (msrp * 0.02)))
        else:
            payment_or_cod_fee = msrp * 0.029 + (0.30 if currency == "USD" else 20.0)

        # Factor 9: RTO Reserve (Reverse logistics cost on non-delivered orders)
        base_rto_pct = cls.CATEGORY_RTO_RATES.get(category, 0.16) * rto_rate_mult
        reverse_shipping_cost = fulfillment_fee * 1.15
        rto_reserve = base_rto_pct * reverse_shipping_cost if region == "India" else base_rto_pct * (fulfillment_fee * 0.5)

        # Factor 10: Return Fraud & Customer Wardrobing Reserve
        fraud_buffer_pct = 0.04 if category != "Apparel" else 0.08
        return_fraud_reserve = msrp * fraud_buffer_pct

        # Factor 11: Ad Spend (TACoS)
        ad_tacos_reserve = msrp * tacos

        # Factor 12: Damage & Defect Reserve
        damage_reserve = landed_cogs * 0.03

        # Factor 14: Net GST / Tax Burden
        # Output GST on MSRP minus Input Tax Credit (ITC on COGS, Ads, Logistics)
        output_tax = msrp * (gst_rate / (1.0 + gst_rate))
        itc_credit = (landed_cogs + fulfillment_fee + marketplace_commission + ad_tacos_reserve) * (gst_rate / (1.0 + gst_rate)) * 0.85
        net_tax_burden = max(0.0, output_tax - itc_credit)

        # Total Variable Costs & Contribution Margin
        total_variable_cost = (
            landed_cogs + marketplace_commission + fulfillment_fee +
            payment_or_cod_fee + rto_reserve + return_fraud_reserve +
            ad_tacos_reserve + damage_reserve + net_tax_burden
        )

        net_profit = msrp - total_variable_cost
        net_profit_pct = (net_profit / msrp * 100.0) if msrp > 0 else 0.0
        contribution_margin = msrp - total_variable_cost

        # Capital required for first batch (MOQ units * Landed COGS + 30 days initial Ad buffer)
        first_batch_capital = (moq_units * landed_cogs) + (moq_units * ad_tacos_reserve * 0.5)

        # Status: Conservative requires Net Margin >= 12% and Gross Margin >= 55%
        pass_threshold = 12.0 if scenario_name != "Upside" else 15.0
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
    def evaluate_15_factor_economics(
        cls,
        product_id: str,
        fob_price: float,
        planned_msrp: float,
        region: str = "India",
        category: str = "General",
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
        Factor 15: Rejects products if Lead Time > Trend Half Life.
        """
        reg_cfg = REGIONAL_PROFILES.get(region, REGIONAL_PROFILES.get("India", {}))
        currency = reg_cfg.get("currency", "INR")

        cons = cls.calculate_scenario(
            scenario_name="Conservative", fob_price=fob_price, planned_msrp=planned_msrp,
            region=region, category=category, length_cm=length_cm, width_cm=width_cm,
            height_cm=height_cm, actual_weight_kg=actual_weight_kg, moq_units=moq_units,
            mold_tooling_cost=mold_tooling_cost, est_ad_tacos_pct=est_ad_tacos_pct,
            lead_time_days=lead_time_days, trend_half_life_days=trend_half_life_days
        )
        exp = cls.calculate_scenario(
            scenario_name="Expected", fob_price=fob_price, planned_msrp=planned_msrp,
            region=region, category=category, length_cm=length_cm, width_cm=width_cm,
            height_cm=height_cm, actual_weight_kg=actual_weight_kg, moq_units=moq_units,
            mold_tooling_cost=mold_tooling_cost, est_ad_tacos_pct=est_ad_tacos_pct,
            lead_time_days=lead_time_days, trend_half_life_days=trend_half_life_days
        )
        ups = cls.calculate_scenario(
            scenario_name="Upside", fob_price=fob_price, planned_msrp=planned_msrp,
            region=region, category=category, length_cm=length_cm, width_cm=width_cm,
            height_cm=height_cm, actual_weight_kg=actual_weight_kg, moq_units=moq_units,
            mold_tooling_cost=mold_tooling_cost, est_ad_tacos_pct=est_ad_tacos_pct,
            lead_time_days=lead_time_days, trend_half_life_days=trend_half_life_days
        )

        # Factor 15: Lead Time Risk Check
        lead_time_risk_factor = min(1.0, lead_time_days / float(max(1, trend_half_life_days)))
        lead_time_pass = lead_time_days <= (trend_half_life_days * 0.70)  # Must arrive within 70% of trend life

        is_financially_viable = (cons.status == "PASS" or exp.status == "PASS") and lead_time_pass

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

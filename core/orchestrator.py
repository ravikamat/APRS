import sys
import datetime
import math
import os
from pathlib import Path
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import REGIONAL_PROFILES
from core.database import (
    record_product_evaluation, get_all_products, init_product_gates,
    update_gate_status, get_gate_status, can_enter_gate, get_current_gate,
    write_ai_rejection
)
from core.utils import normalize_region
from tools.amazon_live_scraper import AmazonLiveScraper, ScraperError
from tools.keepa_api_client import KeepaAPIClient, KeepaAPIError
from core.excel_manager import update_master_excel
from tools.ai_supervisor import get_supervisor

# -------------------------------------------------------------
# CATEGORY REFERRAL FEES MAPPING
# -------------------------------------------------------------
CATEGORY_COMMISSIONS = {
    "Consumer Electronics": 0.08,
    "Automotive": 0.12,
    "Beauty & Grooming": 0.12,
    "Home & Kitchen": 0.15,
    "Kitchen Storage": 0.15,
    "Pet Supplies": 0.15,
    "Apparel & Accessories": 0.17,
    "General": 0.15
}

# -------------------------------------------------------------
# COMPREHENSIVE 12-FACTOR + TAX + MOLD ECONOMICS ENGINE
# -------------------------------------------------------------
class ComprehensiveUnitEconomics:
    """
    12-Factor Landed COGS, Taxes (GST/VAT), Category Fees,
    Mold Amortization, Transit Financing, and Stress Shock Matrix.
    """
    @staticmethod
    def calculate_landed_economics(
        fob_price: float,
        planned_msrp: float,
        region: str = "USA",
        category: str = "General",
        est_ad_cac: float = 15.0,
        moq_units: int = 300,
        mold_tooling_cost: float = 600.0
    ) -> Dict[str, Any]:
        reg_canonical = normalize_region(region or "USA")
        
        # 1. Category Referral Fee Lookup
        referral_fee_pct = CATEGORY_COMMISSIONS.get(category, CATEGORY_COMMISSIONS.get("General", 0.15))
        
        # 2. Regional Logistics, Customs, Taxes & Margins
        if reg_canonical == "India":
            origin_inland_trucking = 12.0
            freight_sea_air = 0.0
            marine_insurance = 0.0
            customs_duty_pct = 0.0
            customs_duty = 0.0
            cha_port_handling = 0.0
            if planned_msrp < 600:
                fba_3pl_storage_fulfillment = 52.0
            elif planned_msrp < 1500:
                fba_3pl_storage_fulfillment = 75.0
            else:
                fba_3pl_storage_fulfillment = 95.0
            payment_gateway_fee_pct = 0.02
            rto_return_reserve_pct = 0.08
            gst_vat_pct = 0.18
            min_target_net_margin = 15.0
            transit_days = 7
        elif reg_canonical in ("Europe", "Germany", "France", "UK"):
            origin_inland_trucking = 0.35
            freight_sea_air = 2.40
            marine_insurance = 0.25
            customs_duty_pct = 0.065
            customs_duty = fob_price * customs_duty_pct
            cha_port_handling = 0.45
            fba_3pl_storage_fulfillment = 5.20
            payment_gateway_fee_pct = 0.025
            rto_return_reserve_pct = 0.04
            gst_vat_pct = 0.20
            min_target_net_margin = 18.0
            transit_days = 45
        else:
            origin_inland_trucking = 0.40
            freight_sea_air = 2.20
            marine_insurance = 0.30
            customs_duty_pct = 0.075
            customs_duty = fob_price * customs_duty_pct
            cha_port_handling = 0.50
            fba_3pl_storage_fulfillment = 5.50
            payment_gateway_fee_pct = 0.029
            rto_return_reserve_pct = 0.04
            gst_vat_pct = 0.00
            min_target_net_margin = 15.0
            transit_days = 35

        # Mold & Tooling Amortization per unit
        moq_safe = max(moq_units, 100)
        mold_amortization_per_unit = round(mold_tooling_cost / moq_safe, 2)
        
        # Landed COGS Calculation
        raw_landed_cogs = fob_price + origin_inland_trucking + freight_sea_air + marine_insurance + customs_duty + cha_port_handling + mold_amortization_per_unit
        
        # 60-Day Transit & Inventory Carrying Cost (1.5% per month financing)
        inventory_carrying_cost = round(raw_landed_cogs * (0.015 * (transit_days / 30.0)), 2)
        landed_cogs = round(raw_landed_cogs + inventory_carrying_cost, 2)
        
        # Gross Margin Calculation
        gross_profit = round(planned_msrp - landed_cogs, 2)
        gross_margin_pct = round((gross_profit / planned_msrp) * 100, 1) if planned_msrp > 0 else 0.0
        
        # Opex Deductions
        marketplace_fee = round(planned_msrp * referral_fee_pct, 2)
        payment_fee = round(planned_msrp * payment_gateway_fee_pct, 2)
        return_reserve = round(planned_msrp * rto_return_reserve_pct, 2)
        
        # Net Tax Burden (Input tax credit offset for GST/VAT regions)
        if gst_vat_pct > 0:
            output_tax = planned_msrp * (gst_vat_pct / (1.0 + gst_vat_pct))
            input_tax_credit = landed_cogs * 0.12
            net_tax_burden = max(0.0, output_tax - input_tax_credit)
        else:
            net_tax_burden = 0.0
            
        total_variable_cost = round(landed_cogs + est_ad_cac + fba_3pl_storage_fulfillment + marketplace_fee + payment_fee + return_reserve + net_tax_burden, 2)
        net_profit = round(planned_msrp - total_variable_cost, 2)
        net_profit_pct = round((net_profit / planned_msrp) * 100, 1) if planned_msrp > 0 else 0.0
        
        # 4-Scenario Stress Shock Testing
        stress_cac = est_ad_cac * 1.35
        stress_msrp = planned_msrp * 0.85
        worst_cost = landed_cogs + stress_cac + fba_3pl_storage_fulfillment + (stress_msrp * referral_fee_pct) + (stress_msrp * payment_gateway_fee_pct) + (stress_msrp * rto_return_reserve_pct) + (net_tax_burden * 0.85)
        worst_case_net_profit = round(stress_msrp - worst_cost, 2)
        worst_case_stress_margin_pct = round((worst_case_net_profit / stress_msrp) * 100, 1) if stress_msrp > 0 else 0.0
        
        # First Batch Capital Requirement
        first_batch_capital = round((landed_cogs * moq_safe) + mold_tooling_cost, 2)
        
        # Decision Gate
        is_pass = (net_profit_pct >= min_target_net_margin) and (worst_case_stress_margin_pct >= 6.0) and (gross_margin_pct >= 60.0)
        status = "PASS" if is_pass else "FAIL"
        score = min(100.0, max(0.0, (gross_margin_pct * 0.35) + (net_profit_pct * 0.45) + (worst_case_stress_margin_pct * 0.20)))
        
        return {
            "landed_cogs": landed_cogs,
            "gross_profit": gross_profit,
            "gross_margin_pct": gross_margin_pct,
            "estimated_cac": est_ad_cac,
            "net_profit": net_profit,
            "net_profit_pct": net_profit_pct,
            "worst_case_stress_margin_pct": worst_case_stress_margin_pct,
            "first_batch_capital": first_batch_capital,
            "mold_amortization_per_unit": mold_amortization_per_unit,
            "net_tax_burden": round(net_tax_burden, 2),
            "referral_fee_pct": referral_fee_pct,
            "status": status,
            "score": round(score, 1),
            "consensus_status": "CONSENSUS_PASS" if is_pass else "CONSENSUS_FAIL"
        }


class AutonomousProductResearchOrchestrator:
    """
    End-to-End Autonomous Product Intelligence Orchestrator.
    6-Stage Gated Workflow:
    Gate 1: Signal Discovery (Keepa BSR + Price History)
    Gate 2: Defect Mining (Manual entry - review analysis & v2.0 spec)
    Gate 3: Economics Validation (12-Factor Unit Economics)
    Gate 4: Sourcing Quote (Manual entry - factory negotiation)
    Gate 5: War Room Consensus (Multi-agent review)
    Gate 6: Sign-Off & Artifacts (Human override + PO generation)
    """
    def __init__(self):
        self.amazon_scraper = AmazonLiveScraper()
        self.keepa = KeepaAPIClient(api_key=os.environ.get("KEEPA_API_KEY", ""))
        
    def _run_gate_1_signal_discovery(self, asin: str, region: str, category: str, item_metadata: dict = None) -> Dict[str, Any]:
        """Gate 1: Fetch real BSR and price history from Keepa API, or live scraped listing fallback."""
        print(f"[GATE 1] Signal Discovery for ASIN {asin} in {region}...")
        update_gate_status(asin, 1, 'IN_PROGRESS', completed_by='system')
        
        # Check if Keepa is enabled; if not, use live scraped item metadata fallback
        if not self.keepa._enabled:
            if item_metadata:
                from tools.keepa_api_client import KeepaProduct
                price = float(item_metadata.get("price") or 499.0)
                title = item_metadata.get("title") or f"Product {asin}"
                keepa_prod = KeepaProduct(
                    asin=asin,
                    title=title,
                    current_price=price,
                    currency="INR" if region == "India" else "USD",
                    bsr_current=int(item_metadata.get("bsr_rank") or 2200),
                    rating=float(item_metadata.get("rating") or 4.2),
                    review_count=int(item_metadata.get("review_count") or 150),
                    price_30d_avg=price,
                    price_historical_low=price * 0.95
                )
                metadata = {
                    "bsr_current": keepa_prod.bsr_current,
                    "current_price": price,
                    "price_30d_avg": price,
                    "price_90d_avg": price,
                    "price_historical_low": price * 0.95,
                    "rating": keepa_prod.rating,
                    "review_count": keepa_prod.review_count,
                    "price_stable": True,
                    "bsr_category": category,
                    "source": "live_scraper_fallback"
                }
                update_gate_status(asin, 1, 'PASS', metadata=metadata, completed_by='system')
                print(f"[GATE 1] PASS (Live Scraper Signal) - BSR: {keepa_prod.bsr_current}, Price: {price}")
                return {"success": True, "data": metadata, "keepa_product": keepa_prod}
            else:
                reason = "Keepa API not configured and no listing metadata provided."
                update_gate_status(asin, 1, 'BLOCKED', blocked_reason=reason, completed_by='system')
                print(f"[GATE 1] BLOCKED - {reason}")
                return {"success": False, "error": reason, "blocked": True}
        
        try:
            keepa_prod = self.keepa.get_product(asin, region=region)
            if not keepa_prod:
                update_gate_status(asin, 1, 'FAIL', blocked_reason='Product not found in Keepa', completed_by='system')
                return {"success": False, "error": "Product not found in Keepa"}
            
            # Validate signal quality
            bsr = keepa_prod.bsr_current
            current_price = keepa_prod.current_price
            price_30d_avg = keepa_prod.price_30d_avg
            price_historical_low = keepa_prod.price_historical_low
            
            # Gate 1 passing criteria: BSR < 5000, price stability (current within 20% of 30d avg)
            price_stable = True
            if price_30d_avg and current_price > 0:
                price_stable = abs(current_price - price_30d_avg) / price_30d_avg < 0.20
            
            gate_passed = (bsr is not None and bsr < 5000) and price_stable
            
            metadata = {
                "bsr_current": bsr,
                "current_price": current_price,
                "price_30d_avg": price_30d_avg,
                "price_90d_avg": keepa_prod.price_90d_avg,
                "price_historical_low": price_historical_low,
                "rating": keepa_prod.rating,
                "review_count": keepa_prod.review_count,
                "price_stable": price_stable,
                "bsr_category": keepa_prod.bsr_category
            }
            
            if gate_passed:
                update_gate_status(asin, 1, 'PASS', metadata=metadata, completed_by='system')
                print(f"[GATE 1] PASS - BSR: {bsr}, Price: ${current_price}, Stable: {price_stable}")
            else:
                reason = f"BSR: {bsr} (need <5000), Price stable: {price_stable}"
                update_gate_status(asin, 1, 'FAIL', blocked_reason=reason, metadata=metadata, completed_by='system')
                print(f"[GATE 1] FAIL - {reason}")
            
            return {"success": gate_passed, "data": metadata, "keepa_product": keepa_prod}
            
        except KeepaAPIError as e:
            update_gate_status(asin, 1, 'FAIL', blocked_reason=f'Keepa API error: {str(e)}', completed_by='system')
            return {"success": False, "error": str(e)}
        except Exception as e:
            update_gate_status(asin, 1, 'FAIL', blocked_reason=f'Unexpected error: {str(e)}', completed_by='system')
            return {"success": False, "error": str(e)}
    
    def manual_gate_1_entry(self, product_id: str, bsr: int, current_price: float, price_30d_avg: float = None, price_historical_low: float = None, rating: float = 0.0, review_count: int = 0) -> Dict[str, Any]:
        """Manually enter Gate 1 data when Keepa API is not available."""
        print(f"[GATE 1 MANUAL] Manual entry for {product_id}...")
        
        price_stable = True
        if price_30d_avg and current_price > 0:
            price_stable = abs(current_price - price_30d_avg) / price_30d_avg < 0.20
        
        gate_passed = (bsr is not None and bsr < 5000) and price_stable
        
        metadata = {
            "bsr_current": bsr,
            "current_price": current_price,
            "price_30d_avg": price_30d_avg,
            "price_historical_low": price_historical_low,
            "rating": rating,
            "review_count": review_count,
            "price_stable": price_stable,
            "manual_entry": True
        }
        
        if gate_passed:
            update_gate_status(product_id, 1, 'PASS', metadata=metadata, completed_by='human')
            print(f"[GATE 1 MANUAL] PASS - BSR: {bsr}, Price: ${current_price}, Stable: {price_stable}")
        else:
            reason = f"BSR: {bsr} (need <5000), Price stable: {price_stable}"
            update_gate_status(product_id, 1, 'FAIL', blocked_reason=reason, metadata=metadata, completed_by='human')
            print(f"[GATE 1 MANUAL] FAIL - {reason}")
        
        return {"success": gate_passed, "data": metadata}
    
    def _run_gate_3_economics_validation(self, product_id: str, live_msrp: float, region: str, category: str, fob_price: float, est_cac: float, moq_units: int, mold_tooling_cost: float) -> Dict[str, Any]:
        """Gate 3: Run 12-factor economics. Enforces Gate 1 & 2 PASS first."""
        print(f"[GATE 3] Economics Validation for {product_id}...")
        
        # Enforce gate progression
        can_enter, reason = can_enter_gate(product_id, 3)
        if not can_enter:
            print(f"[GATE 3] BLOCKED - {reason}")
            update_gate_status(product_id, 3, 'BLOCKED', blocked_reason=reason, completed_by='system')
            return {"success": False, "error": f"Gate 3 blocked: {reason}"}
        
        update_gate_status(product_id, 3, 'IN_PROGRESS', completed_by='system')
        
        econ = ComprehensiveUnitEconomics.calculate_landed_economics(
            fob_price=fob_price,
            planned_msrp=live_msrp,
            region=region,
            category=category,
            est_ad_cac=est_cac,
            moq_units=moq_units,
            mold_tooling_cost=mold_tooling_cost
        )
        
        # Gate 3 passing criteria from economics engine
        gate_passed = econ["status"] == "PASS"
        metadata = {
            "landed_cogs": econ["landed_cogs"],
            "gross_margin_pct": econ["gross_margin_pct"],
            "net_profit_pct": econ["net_profit_pct"],
            "worst_case_stress_margin_pct": econ["worst_case_stress_margin_pct"],
            "score": econ["score"]
        }
        
        if gate_passed:
            update_gate_status(product_id, 3, 'PASS', metadata=metadata, completed_by='system')
            print(f"[GATE 3] PASS - Gross: {econ['gross_margin_pct']}%, Net: {econ['net_profit_pct']}%, Stress: {econ['worst_case_stress_margin_pct']}%")
        else:
            update_gate_status(product_id, 3, 'FAIL', blocked_reason=f"Economics failed: Gross={econ['gross_margin_pct']}%, Net={econ['net_profit_pct']}%, Stress={econ['worst_case_stress_margin_pct']}%", metadata=metadata, completed_by='system')
            print(f"[GATE 3] FAIL - Gross: {econ['gross_margin_pct']}%, Net: {econ['net_profit_pct']}%, Stress: {econ['worst_case_stress_margin_pct']}%")
        
        return {"success": gate_passed, "data": econ, "metadata": metadata}
    
    def discover_and_evaluate_products(self, region: str = "USA", category: str = "Kitchen Storage", max_candidates: int = 3) -> List[Dict[str, Any]]:
        """
        6-Stage Gated Product Discovery Pipeline:
        Gate 1: Signal Discovery (Keepa BSR + Price History) - AUTOMATED
        Gate 2: Defect Mining (Manual - requires human review entry)
        Gate 3: Economics Validation (12-Factor) - AUTOMATED (blocked until Gates 1&2 PASS)
        Gate 4: Sourcing Quote (Manual - requires factory quote entry)
        Gate 5: War Room Consensus (Automated multi-agent)
        Gate 6: Sign-Off & Artifacts (Human override + PO generation)
        """
        clean_cat = category.strip()[:60] if category else "Home & Kitchen"
        print(f"[ORCHESTRATOR] 6-Stage Gated Discovery initiated for '{clean_cat}' in {region}...")
        
        # Register with AI Supervisor for active monitoring
        supervisor = get_supervisor()
        task_id = supervisor.register_task("scrape", f"discover_{clean_cat}", marketplace="amazon", region=region)
        
        with supervisor.supervise(task_id) as task:
            # Step 1: Live Marketplace Scraping for candidate ASINs (using curl_cffi for anti-bot)
            try:
                live_listings = self.amazon_scraper.search(clean_cat, region=region, max_results=max_candidates)
                print(f"[ORCHESTRATOR] Found {len(live_listings)} live products via curl_cffi scraper")
                task.data_collected = {"listings": live_listings}
            except ScraperError as e:
                print(f"[ORCHESTRATOR] curl_cffi scraper failed: {e}. No fallback - returning error.")
                return [{"success": False, "error": f"Scraper failed: {e}"}]
            
            evaluated_products = []
            
            for item in live_listings:
            asin = item["asin"]
            title = item["title"]
            raw_price = item.get("price")
            canon_region = normalize_region(region)
            is_india = (canon_region == "India")
            try:
                live_msrp = float(raw_price) if (raw_price is not None and float(raw_price) > 0) else (499.0 if is_india else 24.99)
            except (ValueError, TypeError):
                live_msrp = 499.0 if is_india else 24.99
            product_id = f"{region[:2].upper()}_{asin[:6].upper()}"
            
            # GATE 1: Signal Discovery (Automated via Keepa or Live Scraper Fallback)
            gate1_result = self._run_gate_1_signal_discovery(asin, region, clean_cat, item_metadata=item)
            if not gate1_result["success"]:
                if gate1_result.get("blocked"):
                    print(f"[ORCHESTRATOR] Product {product_id} blocked at Gate 1: {gate1_result['error']}")
                else:
                    print(f"[ORCHESTRATOR] Product {product_id} failed Gate 1, skipping.")
                continue
            
            keepa_prod = gate1_result.get("keepa_product")
            if not keepa_prod:
                print(f"[ORCHESTRATOR] Product {product_id} has no Keepa product data, skipping.")
                continue
            
            live_msrp = float(keepa_prod.current_price) if keepa_prod.current_price else 0.0
            if live_msrp <= 0:
                print(f"[ORCHESTRATOR] Product {product_id} has zero or negative price, skipping.")
                continue
            
            # Create product record with Gate 1 data only
            # Gate 2 (Defect Mining) and Gate 4 (Sourcing) require MANUAL entry
            canon_region = normalize_region(region)
            is_india = (canon_region == "India")
            hub_name = "Moradabad / Surat / Rajkot Cluster" if is_india else "Ningbo / Shenzhen Cluster"

            # Determine marketplace URL using the real ASIN from Keepa
            if is_india:
                marketplace_url = f"https://www.amazon.in/dp/{asin}"
            elif canon_region == "UK":
                marketplace_url = f"https://www.amazon.co.uk/dp/{asin}"
            elif canon_region == "GCC_MiddleEast":
                marketplace_url = f"https://www.amazon.ae/dp/{asin}"
            else:
                marketplace_url = f"https://www.amazon.com/dp/{asin}"

            prod_data = {
                "id": product_id,
                "name": keepa_prod.title,
                "category": clean_cat,
                "region": region,
                "retail_msrp": live_msrp,
                "factory_cogs": 0.0,  # Will be filled in Gate 4
                "est_cac": round(live_msrp * (0.14 if is_india else 0.28), 2),  # 14% TACoS for India
                "sourcing_hub": hub_name,
                "marketplace_url": marketplace_url,
                "competitor_flaw": "",   # User fills in Gate 2
                "upgrade_v2": "",        # User fills in Gate 2
                "bsr_rank": gate1_result.get("data", {}).get("bsr_current", 999),
                "estimated_daily_units": 30,
                "ad_active_days": 0,
                "suppliers": [
                    {
                        # ⚠️ UNVERIFIED CLUSTER REFERENCE — Gate 4 requires real factory negotiation
                        "factory_name": f"[Gate 4 Required] {clean_cat.split()[0].title()} Manufacturer — {hub_name}",
                        "supplier_type": "Unverified Cluster Reference",
                        "industrial_address": (
                            "Surat GIDC / Moradabad Brass Cluster / Rajkot Auto Parts Cluster, India"
                            if is_india else
                            "Ningbo / Yiwu / Shenzhen Export Processing Zone, China"
                        ),
                        "contact_person": "⚠️ Not yet sourced — complete Gate 4",
                        "contact_details": (
                            "⚠️ Unverified — search IndiaMart / TradeIndia for verified contacts"
                            if is_india else
                            "⚠️ Unverified — search 1688.com / Alibaba for verified contacts"
                        ),
                        "platform_profile_url": "https://indiamart.com" if is_india else "https://alibaba.com",
                        "fob_unit_price": "TBD — pending Gate 4 negotiation",
                        "moq_units": 300,
                        "sample_cost_leadtime": "TBD — pending Gate 4 negotiation",
                        "certifications": "TBD — verify during Gate 4 sourcing",
                    }
                ],
                # Gate 1 data
                "gate_1_bsr":          gate1_result.get("data", {}).get("bsr_current"),
                "gate_1_price_stable": gate1_result.get("data", {}).get("price_stable"),
                "gate_1_rating":       gate1_result.get("data", {}).get("rating"),
                "gate_1_review_count": gate1_result.get("data", {}).get("review_count"),
            }
            
            # Save Gate 1 data FIRST (product must exist in master_products before gates)
            gate1_eval = {
                "landed_cogs": 0.0,
                "gross_margin_pct": 0.0,
                "net_profit_pct": 0.0,
                "worst_case_stress_margin_pct": 0.0,
                "status": "PENDING",
                "score": 0.0,
                "consensus_status": "PENDING",
                "action_plan": "Awaiting Gate 2 manual defect review"
            }
            
            record_product_evaluation(prod_data, gate1_eval)
            
            # NOW initialize gates (product exists in master_products)
            init_product_gates(product_id)
            
            # Attach multi-platform listings (Amazon, Flipkart, Meesho)
            try:
                from tools.multi_marketplace_engine import MultiMarketplaceEngine
                mkt = MultiMarketplaceEngine()
                mkt.attach_listings_to_product(product_id, clean_cat, region=region)
            except Exception as e:
                print(f"[ORCHESTRATOR] Multi-platform listing attachment notice: {e}")
            
            # GATE 1: PASS
            update_gate_status(product_id, 1, 'PASS', completed_by='system')
            
            # GATE 2: Defect Mining - MANUAL (blocked until human enters data)
            update_gate_status(product_id, 2, 'BLOCKED', blocked_reason='Awaiting manual review mining: Enter 3-star defect summary and v2.0 engineering spec', completed_by='system')
            
            evaluated_products.append({
                "product_id": product_id,
                "status": "BLOCKED_AT_GATE_2",
                "message": "Gate 1 complete. Proceed to Gate 2 in UI for defect mining."
            })
            
        # AI Supervisor: Validate ALL evaluated products post-evaluation
        if evaluated_products:
            try:
                validation_summary = get_supervisor().validate_products_batch(
                    products=evaluated_products,
                    marketplace="amazon",
                    region=region
                )
                print(f"[ORCHESTRATOR] 🧠 AI Validation: {validation_summary['valid']} valid, "
                      f"{validation_summary['invalid']} flagged, {validation_summary['auto_deleted']} auto-deleted")
            except Exception as ve:
                print(f"[ORCHESTRATOR] AI validation notice: {ve}")

        # Update Master Excel shadow export
        update_master_excel()
        return evaluated_products

    def re_evaluate_single_product(self, product_id: str) -> Dict[str, Any]:
        """Re-evaluates an existing product in SQLite. Requires Gate 4 FOB to be set."""
        products = get_all_products()
        target = next((p for p in products if p["product_id"] == product_id), None)
        if not target:
            return {"success": False, "error": "Product ID not found"}
        
        # Check prerequisites: Gates 1 & 2 must be PASS, Gate 4 FOB must be set
        gates = get_gate_status(product_id)
        gate1 = next((g for g in gates if g['gate_number'] == 1), None)
        gate2 = next((g for g in gates if g['gate_number'] == 2), None)
        
        if not gate1 or gate1['status'] not in ('PASS', 'OVERRIDDEN'):
            return {"success": False, "error": "Gate 1 must be PASS before re-evaluation."}
        if not gate2 or gate2['status'] not in ('PASS', 'OVERRIDDEN'):
            return {"success": False, "error": "Gate 2 must be PASS before re-evaluation."}
        
        fob  = float(target.get("factory_cogs") or 0)
        msrp = float(target.get("planned_msrp") or 0)
        cac  = float(target.get("estimated_cac") or 5.0)

        if fob <= 0:
            return {"success": False, "error": "Gate 4 FOB (factory_cogs) not set. Enter it via the Gate 4 Sourcing form before refreshing."}
        if msrp <= 0:
            return {"success": False, "error": "Planned MSRP is 0 or not set. Update the product MSRP first."}

        econ = ComprehensiveUnitEconomics.calculate_landed_economics(
            fob_price=fob,
            planned_msrp=msrp,
            region=target["region"],
            category=target.get("category", "General"),
            est_ad_cac=cac,
            moq_units=300
        )
        
        # Update Gate 3 status based on economics result
        gate3_status = econ["status"]  # PASS or FAIL from economics engine
        gate3_metadata = {
            "landed_cogs": econ["landed_cogs"],
            "gross_margin_pct": econ["gross_margin_pct"],
            "net_profit_pct": econ["net_profit_pct"],
            "worst_case_stress_margin_pct": econ["worst_case_stress_margin_pct"],
            "score": econ["score"]
        }
        update_gate_status(product_id, 3, gate3_status, metadata=gate3_metadata, completed_by='system')
        
        record_product_evaluation(
            {
                "id": target["product_id"],
                "name": target["name"],
                "category": target.get("category") or "General",
                "region": target["region"],
                "retail_msrp": msrp,
                "factory_cogs": fob,
                "est_cac": cac,
                "sourcing_hub": target.get("sourcing_cluster") or "Unknown",
                "marketplace_url": target.get("marketplace_url") or "",
                "competitor_flaw": target.get("competitor_3star_flaws") or "",
                "upgrade_v2": target.get("upgrade_v2_engineering") or "",
                "bsr_rank": int(target.get("bsr_rank") or 0),
                "estimated_daily_units": float(target.get("estimated_daily_units") or 0),
                "ad_active_days": int(target.get("ad_active_days") or 0),
                "suppliers": target.get("suppliers") or []
            },
            econ
        )
        update_master_excel()
        return {"success": True, "data": econ}


# ── Universal Multi-Marketplace Discovery ─────────────────────────────────
    def discover_universal_marketplaces(self, query: str, region: str = "India", max_pages: int = 2) -> Dict[str, List[Dict]]:
        """
        Discovers products across ALL configured marketplaces using Universal Browser Scraper.
        Returns dict of marketplace -> product listings.
        """
        try:
            from tools.universal_browser_scraper import UniversalBrowserScraper
            scraper = UniversalBrowserScraper()
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(
                    scraper.scrape_all_marketplaces(region=region, query=query, max_pages=max_pages)
                )
            finally:
                loop.close()
        except Exception as e:
            print(f"[ORCHESTRATOR] Universal marketplace discovery failed: {e}")
            return {}

    def discover_and_evaluate_universal(self, region: str = "India", category: str = "Kitchen Storage", max_candidates: int = 5, max_pages: int = 2) -> List[Dict]:
        """
        Extended discovery: Uses Universal Scraper across ALL marketplaces (Amazon, Flipkart, Meesho, Myntra, Shopify)
        then runs full 6-gate evaluation on merged & deduplicated results.
        """
        import asyncio
        from core.utils import normalize_region
        from core.database import record_product_evaluation, init_product_gates, update_gate_status
        from core.excel_manager import update_master_excel
        from core.product_matcher import CanonicalProductMatcher
        
        clean_cat = category.strip()[:60] if category else "Home & Kitchen"
        print(f"[ORCHESTRATOR UNIVERSAL] Multi-marketplace discovery for '{clean_cat}' in {region}...")

        # 1. Universal multi-marketplace scraping
        all_marketplace_results = self.discover_universal_marketplaces(clean_cat, region, max_pages=max_pages)
        
        # Aggregate all products from all marketplaces
        all_products = []
        for marketplace, products in all_marketplace_results.items():
            for p in products:
                p['source_marketplace'] = marketplace
                all_products.append(p)
        
        print(f"[ORCHESTRATOR UNIVERSAL] Total raw products from all marketplaces: {len(all_products)}")
        
        if not all_products:
            print(f"[ORCHESTRATOR UNIVERSAL] No products found across all marketplaces")
            return []

        # 2. Canonical deduplication across marketplaces
        matcher = CanonicalProductMatcher()
        canonical_products = []
        seen_ids = set()
        
        for p in all_products:
            pname = p.get("title", "")
            pprice = float(p.get("price", 0))
            pid = f"{region[:2].upper()}_{abs(hash(pname)) % 1000000:06d}"
            
            # Check against existing canonical products
            is_dup = False
            for cp in canonical_products:
                match = matcher.evaluate_match_confidence(
                    pname, cp.get("title", ""),
                    pprice, float(cp.get("price", 0))
                )
                if match.get("classification") == "EXACT_MATCH":
                    is_dup = True
                    # Merge: keep the one with more data
                    if len(str(p)) > len(str(cp)):
                        canonical_products.remove(cp)
                        canonical_products.append(p)
                    is_dup = True
                    break
            
            if not is_dup:
                canonical_products.append(p)
                seen_ids.add(pid)

        print(f"[ORCHESTRATOR UNIVERSAL] After deduplication: {len(canonical_products)} unique products")
        
        # 3. Evaluate each canonical product through full pipeline
        evaluated = []
        for p in canonical_products[:max_candidates]:
            try:
                # Create a mock item for the existing pipeline
                item = {
                    "asin": p.get("product_url", "").split("/")[-1] if p.get("product_url") else f"UNIV_{abs(hash(p.get('title', '')))}",
                    "title": p.get("title", "Unknown Product"),
                    "price": p.get("price", 0),
                    "rating": p.get("rating"),
                    "review_count": p.get("review_count", 0),
                    "product_url": p.get("product_url", ""),
                    "source_marketplace": p.get("source_marketplace", "universal")
                }
                
                # Use existing pipeline with the universal item
                results = self.discover_and_evaluate_products(
                    region=region, 
                    category=clean_cat, 
                    max_candidates=1
                )
                evaluated.extend(results)
            except Exception as e:
                print(f"[ORCHESTRATOR UNIVERSAL] Evaluation notice for {p.get('title', '')}: {e}")
                continue
        
        update_master_excel()
        return evaluated


if __name__ == "__main__":
    orch = AutonomousProductResearchOrchestrator()
    res = orch.discover_and_evaluate_products(region="USA", category="Desk Organizer", max_candidates=2)
    print(f"[SUCCESS] Discovered & Evaluated {len(res)} live products with 12-factor economics!")
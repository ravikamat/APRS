"""
tests/test_aprs_v6_advanced.py — Comprehensive Test Suite for APRS V6 Pro Advanced Components.

Covers:
1. Canonical Data Models (core/models.py).
2. 15-Factor 3-Scenario Unit Economics Engine (core/economics_engine.py).
3. Universal Source Adapter Telemetry (tools/adapters/base_adapter.py).
4. Canonical Product Graph Matcher & Demand Proxy Scoring (core/product_matcher.py).
5. Formal Negative-Finding Backtracking and Sourcing Launchpad DB workflows (core/database.py).
"""
import os
import sys
import tempfile
import gc
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


class TestAPRSV6Advanced(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db_path = Path(self.temp_dir.name) / "test_adv_v6.db"
        os.environ["APRS_DB_PATH"] = str(self.db_path)

        from core.database import init_db
        init_db()

    def tearDown(self):
        if "APRS_DB_PATH" in os.environ:
            del os.environ["APRS_DB_PATH"]
        gc.collect()
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_canonical_models_validation(self):
        """Tests Pydantic domain models instantiate and enforce constraints."""
        from core.models import (
            TrendSignal, MarketplaceListing, DefectCluster,
            ScenarioEconomics, EconomicsAssessment, NegativeFinding, LaunchpadItem
        )

        ts = TrendSignal(
            platform="tiktok",
            keyword="Mini USB Desk Fan",
            trend_category="Home",
            region="India",
            velocity_score=88.5,
            longevity_days=21
        )
        self.assertEqual(ts.platform, "tiktok")
        self.assertEqual(ts.longevity_type, "EVERGREEN_PROBLEM_SOLVER")

        ml = MarketplaceListing(
            product_id="TEST_001",
            platform="amazon",
            title="Mini USB Desk Fan 3 Speed",
            price=499.0,
            listing_url="https://amazon.in/dp/B001"
        )
        self.assertEqual(ml.currency, "INR")

        nf = NegativeFinding(
            product_id="TEST_001",
            origin_stage="economics_auditor",
            target_stage="marketplace_harvester",
            reason_code="MARGIN_FAIL",
            human_readable_reason="Conservative net margin is 4.2% (below 12% threshold)"
        )
        self.assertEqual(nf.reason_code, "MARGIN_FAIL")

    def test_15_factor_3_scenario_economics(self):
        """Tests 15-factor economics calculation across Conservative, Expected, and Upside."""
        from core.economics_engine import Comprehensive15FactorEconomics

        assessment = Comprehensive15FactorEconomics.evaluate_15_factor_economics(
            product_id="IN_FAN_001",
            fob_price=120.0,
            planned_msrp=599.0,
            region="India",
            category="Home",
            length_cm=18.0,
            width_cm=12.0,
            height_cm=8.0,
            actual_weight_kg=0.35,
            moq_units=300,
            mold_tooling_cost=0.0,
            est_ad_tacos_pct=0.15,
            lead_time_days=25,
            trend_half_life_days=90
        )

        self.assertIsNotNone(assessment.conservative)
        self.assertIsNotNone(assessment.expected)
        self.assertIsNotNone(assessment.upside)
        self.assertTrue(assessment.is_financially_viable)
        self.assertEqual(assessment.recommendation, "PASS")
        self.assertGreater(assessment.expected.net_profit_pct, 12.0)
        self.assertGreater(assessment.conservative.volumetric_freight_cost, 0.0)

        # Test Lead Time decay failure condition
        decay_assessment = Comprehensive15FactorEconomics.evaluate_15_factor_economics(
            product_id="IN_SLOW_001",
            fob_price=120.0,
            planned_msrp=599.0,
            region="India",
            category="Home",
            lead_time_days=80,      # > 70% of 90 days trend life
            trend_half_life_days=90
        )
        self.assertFalse(decay_assessment.is_financially_viable)
        self.assertEqual(decay_assessment.recommendation, "FAIL")

    def test_source_adapter_telemetry(self):
        """Tests adapter base class telemetry and health reporting."""
        from tools.adapters.base_adapter import BaseSourceAdapter

        adapter = BaseSourceAdapter("test_google_trends")
        adapter.record_success(count=12, latency_ms=145.0)
        health = adapter.health_check()
        self.assertTrue(health.is_healthy)
        self.assertEqual(health.records_collected_total, 12)
        self.assertEqual(health.status_message, "ONLINE")

        for _ in range(6):
            adapter.record_error()
        degraded_health = adapter.health_check()
        self.assertFalse(degraded_health.is_healthy)
        self.assertIn("DEGRADED", degraded_health.status_message)

    def test_canonical_product_matcher_and_demand_proxy(self):
        """Tests canonical title normalization, match confidence, and demand proxy scoring."""
        from core.product_matcher import CanonicalProductMatcher, DemandProxyScorer

        # Test Matcher
        title_a = "2 Tier Sliding Under Sink Cabinet Storage Organizer Rack for Kitchen"
        title_b = "2-Tier Under Sink Organizers and Storage, Multi-Purpose Sliding Drawer Rack"
        match_type, conf = CanonicalProductMatcher.evaluate_match_confidence(
            canonical_title=title_a,
            target_listing_title=title_b,
            canonical_price=1299.0,
            target_price=1199.0,
            target_category="Kitchen"
        )
        self.assertIn(match_type, ["EXACT_MATCH", "PROBABLE_VARIANT"])
        self.assertGreaterEqual(conf, 0.35)

        # Test Demand Proxy Scoring
        dp = DemandProxyScorer.calculate_demand_proxy(
            bsr_rank=850,
            review_count=350,
            rating=4.1,
            ad_active_days=45,
            price_stability_pct=90.0
        )
        self.assertGreaterEqual(dp["demand_proxy_score"], 70.0)
        self.assertEqual(dp["signal_tier"], "HIGH_VELOCITY_OPPORTUNITY")

    def test_negative_findings_and_launchpad_database_workflows(self):
        """Tests negative finding recording and Sourcing Launchpad milestone progression."""
        from core.database import (
            record_product_evaluation,
            record_negative_finding, get_negative_findings,
            add_to_launchpad, get_launchpad_items, update_launchpad_status
        )

        # Create master product first to satisfy Foreign Key
        dummy_prod = {
            "id": "WIN_MUG_002",
            "name": "SUS304 Magnetic Stirring Mug v2.0",
            "category": "Kitchen",
            "region": "India",
            "retail_msrp": 899.0,
            "factory_cogs": 220.0,
            "est_cac": 90.0,
            "sourcing_hub": "Moradabad Cluster",
            "marketplace_url": "https://www.amazon.in/dp/B0WIN0002",
            "competitor_flaw": "Leaky lid",
            "upgrade_v2": "Silicone pressure seal",
            "bsr_rank": 950,
            "estimated_daily_units": 45,
            "ad_active_days": 25,
            "suppliers": []
        }
        dummy_econ = {"status": "PASS", "score": 90.0}
        record_product_evaluation(dummy_prod, dummy_econ)

        # 1. Negative Finding Event
        fid = record_negative_finding(
            product_id="WIN_MUG_002",
            origin_stage="defect_analyst",
            target_stage="trend_scout",
            reason_code="FATAL_FLAW",
            human_readable_reason="Thermal shock crack in plastic casing",
            evidence_summary="15 out of 40 reviews report crack on boiling water",
            severity="CRITICAL",
            recommended_action="Reject SKU and branch to ceramic/SUS304 variants"
        )
        self.assertGreater(fid, 0)
        findings = get_negative_findings(product_id="WIN_MUG_002")
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["reason_code"], "FATAL_FLAW")

        # 2. Launchpad Item Creation & Milestone Tracking
        lid = add_to_launchpad(
            product_id="WIN_MUG_002",
            product_name="SUS304 Magnetic Stirring Mug v2.0",
            target_moq=500,
            target_fob=220.0,
            target_launch_date="2026-10-15",
            confirmed_factory_name="Moradabad Metal Crafts"
        )
        self.assertGreater(lid, 0)

        items = get_launchpad_items()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["confirmed_factory_name"], "Moradabad Metal Crafts")

        # Progress milestones
        update_launchpad_status(
            item_id=lid,
            launch_status="SAMPLING",
            sample_ordered=True,
            sample_approved=False,
            qc_passed=False,
            po_generated=False
        )

        updated_items = get_launchpad_items()
        self.assertEqual(updated_items[0]["launch_status"], "SAMPLING")
        self.assertEqual(updated_items[0]["sample_ordered"], 1)


if __name__ == "__main__":
    unittest.main()

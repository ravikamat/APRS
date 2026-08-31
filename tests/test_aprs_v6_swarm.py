"""
tests/test_aprs_v6_swarm.py — Test Suite for APRS V6 Swarm & Intelligence Capabilities.

Verifies:
1. Database V6 migrations, soft-delete with mandatory audit reason, restore, shortlist toggle.
2. Open-Web Trend Scout aggregation & signal persistence.
3. Multi-Marketplace crawler listing attachment.
4. NVIDIA NIM Nemotron Swarm Orchestrator with false-positive backtracking alarms.
5. Unified SSOT Database Explorer multi-table queries.
"""
import os
import sys
import tempfile
import unittest
import asyncio
from pathlib import Path
from unittest.mock import patch, MagicMock

# Project root import
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


class TestAPRSV6Swarm(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_research_engine_v6.db"
        os.environ["APRS_DB_PATH"] = str(self.db_path)

        from core.database import init_db
        init_db()

    def tearDown(self):
        self.temp_dir.cleanup()
        if "APRS_DB_PATH" in os.environ:
            del os.environ["APRS_DB_PATH"]

    def test_database_soft_delete_and_shortlist(self):
        """Tests that products can be soft-deleted with mandatory reason, restored, and shortlisted."""
        from core.database import (
            record_product_evaluation, get_all_products,
            soft_delete_product, restore_product, toggle_shortlist, get_shortlisted_products
        )

        dummy_prod = {
            "id": "IN_TEST_001",
            "name": "Magnetic Stainless Steel Mug",
            "category": "Kitchen",
            "region": "India",
            "retail_msrp": 999.0,
            "factory_cogs": 250.0,
            "est_cac": 120.0,
            "sourcing_hub": "Moradabad Cluster",
            "marketplace_url": "https://www.amazon.in/dp/B0TEST0001",
            "competitor_flaw": "Weak magnet",
            "upgrade_v2": "Neodymium N52 magnet",
            "bsr_rank": 1500,
            "estimated_daily_units": 40,
            "ad_active_days": 10,
            "suppliers": []
        }
        dummy_econ = {
            "landed_cogs": 310.0,
            "gross_margin_pct": 68.9,
            "net_profit_pct": 22.5,
            "worst_case_stress_margin_pct": 9.8,
            "status": "PASS",
            "score": 88.0,
            "consensus_status": "CONSENSUS_PASS"
        }

        ok = record_product_evaluation(dummy_prod, dummy_econ)
        self.assertTrue(ok)

        # Verify active fetch
        active_prods = get_all_products(include_deleted=False)
        self.assertEqual(len(active_prods), 1)

        # Test Shortlist Toggle
        toggle_shortlist("IN_TEST_001", True)
        shortlisted = get_shortlisted_products()
        self.assertEqual(len(shortlisted), 1)
        self.assertEqual(shortlisted[0]["product_id"], "IN_TEST_001")

        # Test Soft Delete (Mandatory reason)
        with self.assertRaises(ValueError):
            soft_delete_product("IN_TEST_001", "")

        del_ok = soft_delete_product("IN_TEST_001", "Negative unit economics under revised freight", deleted_by="test_agent")
        self.assertTrue(del_ok)

        # Active list should now be 0
        active_after_del = get_all_products(include_deleted=False)
        self.assertEqual(len(active_after_del), 0)

        # Deleted list should have 1
        all_with_del = get_all_products(include_deleted=True)
        self.assertEqual(len(all_with_del), 1)
        self.assertEqual(all_with_del[0]["is_deleted"], 1)
        self.assertEqual(all_with_del[0]["deletion_reason"], "Negative unit economics under revised freight")

        # Test Restore
        restore_ok = restore_product("IN_TEST_001")
        self.assertTrue(restore_ok)
        active_restored = get_all_products(include_deleted=False)
        self.assertEqual(len(active_restored), 1)

    def test_open_web_trend_scout_recording(self):
        """Tests trend signal harvesting and persistence."""
        from tools.trend_scout.trend_aggregator import OpenWebTrendScout
        from core.database import get_active_trend_signals

        scout = OpenWebTrendScout()
        signals = scout.scout_google_breakout_queries("oil spray bottle", region="India")
        self.assertIsInstance(signals, list)

        # Record manual signal
        from core.database import record_trend_signal
        sig_id = record_trend_signal(
            platform="instagram",
            keyword="Smart Flame Diffuser",
            category="Home",
            region="USA",
            velocity_score=92.5,
            longevity_days=28,
            raw_json={"hashtag": "#flamediffuser", "views": 1500000}
        )
        self.assertGreater(sig_id, 0)

        active_signals = get_active_trend_signals(region="USA")
        self.assertEqual(len(active_signals), 1)
        self.assertEqual(active_signals[0]["keyword"], "Smart Flame Diffuser")

    def test_multi_platform_listing_attachment(self):
        """Tests multi-marketplace listing attachment and querying."""
        from core.database import record_multi_platform_listing, get_all_products, record_product_evaluation

        dummy_prod = {
            "id": "IN_MKT_001",
            "name": "Silicone Toilet Wand Quick Dry",
            "category": "Cleaning",
            "region": "India",
            "retail_msrp": 499.0,
            "factory_cogs": 90.0,
            "est_cac": 50.0,
            "sourcing_hub": "Surat Cluster",
            "marketplace_url": "https://www.amazon.in/dp/B0WAND0001",
            "competitor_flaw": "Handle snaps",
            "upgrade_v2": "Reinforced stainless steel core",
            "bsr_rank": 3200,
            "estimated_daily_units": 25,
            "ad_active_days": 5,
            "suppliers": []
        }
        dummy_econ = {"status": "PASS", "score": 82.0}
        record_product_evaluation(dummy_prod, dummy_econ)

        # Attach Flipkart & Meesho comp listings
        record_multi_platform_listing(
            product_id="IN_MKT_001",
            platform="flipkart",
            title="Silicone Toilet Cleaner Brush Wall Mounted",
            price=449.0,
            listing_url="https://flipkart.com/p/123",
            rating=4.2,
            review_count=180
        )
        record_multi_platform_listing(
            product_id="IN_MKT_001",
            platform="meesho",
            title="Flexible Silicone Toilet Cleaner Brush",
            price=299.0,
            listing_url="https://meesho.com/p/456",
            rating=3.9,
            review_count=90
        )

        prods = get_all_products(include_deleted=False)
        self.assertEqual(len(prods), 1)
        self.assertEqual(len(prods[0]["multi_platform_listings"]), 2)

    def test_nim_swarm_orchestrator_backtracking(self):
        """Tests sequential multi-agent swarm evaluation and negative-feedback backtracking."""
        import asyncio
        from unittest.mock import AsyncMock, patch
        from models.nim_swarm_orchestrator import NIMSwarmOrchestrator
        from models.llm_router import LLMRouter, LLMResponse, LLMTaskType, LLMProvider
        from core.database import get_swarm_audit_logs

        # 1. Test Passing Candidate with mocked LLM
        async def test_passing():
            with patch.object(LLMRouter, 'query', new_callable=AsyncMock) as mock_query:
                call_count = {"count": 0}
                
                async def mock_query_side_effect(prompt, task_type, **kwargs):
                    call_count["count"] += 1
                    stage = call_count["count"]
                    
                    if stage == 1:  # Trend Scout
                        return LLMResponse(
                            content='{"passed": true, "confidence_score": 85.0, "longevity_type": "EVERGREEN_PROBLEM_SOLVER", "target_audience": "Home cooks", "summary": "Strong trend"}',
                            provider=LLMProvider.NIM, model="nemotron_scout", latency_ms=100
                        )
                    elif stage == 2:  # Marketplace
                        return LLMResponse(
                            content='{"passed": true, "confidence_score": 80.0, "market_saturation": "MEDIUM", "dominant_brand_risk": false, "optimal_msrp_range": {"min": 799, "max": 1499}, "competitor_count": 25, "avg_competitor_rating": 3.8, "summary": "Good market"}',
                            provider=LLMProvider.NIM, model="ultra_reasoning", latency_ms=100
                        )
                    elif stage == 3:  # Defect
                        return LLMResponse(
                            content='{"passed": true, "confidence_score": 85.0, "fatal_hazard_detected": false, "feasibility_score": 85.0, "estimated_bom_delta": 0.50, "summary": "Feasible fix"}',
                            provider=LLMProvider.NIM, model="deep_reasoning", latency_ms=100
                        )
                    elif stage == 4:  # Economics
                        return LLMResponse(
                            content='{"passed": true, "confidence_score": 85.0, "primary_risk": "Low", "margin_assessment": "HEALTHY", "summary": "Economics viable"}',
                            provider=LLMProvider.NIM, model="long_context_synthesis", latency_ms=100
                        )
                    elif stage == 5:  # Arbiter
                        return LLMResponse(
                            content='{"final_verdict": "CONSENSUS_PASS", "confidence_score": 85.0, "dissenting_concerns": [], "risk_mitigation_notes": "None", "summary": "Approved"}',
                            provider=LLMProvider.NIM, model="nemotron_arbiter", latency_ms=100
                        )
                    return LLMResponse(content='{"passed": true}', provider=LLMProvider.NIM, model="default", latency_ms=100)
                
                mock_query.side_effect = mock_query_side_effect
                
                swarm = NIMSwarmOrchestrator()

                pass_prod = {
                    "id": "PASS_001",
                    "name": "Double Wall Vacuum Insulated Flask",
                    "region": "India",
                    "competitor_flaw": "Paint chips after dishwasher",
                    "upgrade_v2": "Powder coated matte exterior"
                }
                pass_econ = {
                    "gross_margin_pct": 65.0,
                    "net_profit_pct": 20.0,
                    "worst_case_stress_margin_pct": 8.0
                }
                res_pass = await swarm.run_full_swarm_audit(pass_prod, pass_econ)
                self.assertEqual(res_pass["consensus_status"], "CONSENSUS_PASS")
                self.assertIsNone(res_pass["backtracked_at"])

        # 2. Test Failing Candidate (Economics Below Threshold -> Triggers Backtrack)
        async def test_failing():
            with patch.object(LLMRouter, 'query', new_callable=AsyncMock) as mock_query:
                call_count = {"count": 0}
                
                async def mock_fail_side_effect(prompt, task_type, **kwargs):
                    call_count["count"] += 1
                    stage = call_count["count"]
                    
                    if stage == 1:  # Trend Scout
                        return LLMResponse(
                            content='{"passed": true, "confidence_score": 85.0, "longevity_type": "EVERGREEN_PROBLEM_SOLVER", "target_audience": "Tech users", "summary": "Trend OK"}',
                            provider=LLMProvider.NIM, model="nemotron_scout", latency_ms=100
                        )
                    elif stage == 2:  # Marketplace
                        return LLMResponse(
                            content='{"passed": true, "confidence_score": 80.0, "market_saturation": "MEDIUM", "dominant_brand_risk": false, "optimal_msrp_range": {"min": 799, "max": 1499}, "competitor_count": 25, "avg_competitor_rating": 3.8, "summary": "Market OK"}',
                            provider=LLMProvider.NIM, model="ultra_reasoning", latency_ms=100
                        )
                    elif stage == 3:  # Defect
                        return LLMResponse(
                            content='{"passed": true, "confidence_score": 85.0, "fatal_hazard_detected": false, "feasibility_score": 85.0, "estimated_bom_delta": 0.50, "summary": "Quality OK"}',
                            provider=LLMProvider.NIM, model="deep_reasoning", latency_ms=100
                        )
                    elif stage == 4:  # Economics - FAIL
                        return LLMResponse(
                            content='{"passed": false, "confidence_score": 40.0, "primary_risk": "Negative margins", "margin_assessment": "UNSUSTAINABLE", "summary": "Economics fail"}',
                            provider=LLMProvider.NIM, model="long_context_synthesis", latency_ms=100
                        )
                    elif stage == 5:  # Arbiter
                        return LLMResponse(
                            content='{"final_verdict": "CONSENSUS_FAIL", "confidence_score": 35.0, "dissenting_concerns": ["Economics fail"], "risk_mitigation_notes": "Reject", "summary": "Rejected"}',
                            provider=LLMProvider.NIM, model="nemotron_arbiter", latency_ms=100
                        )
                    return LLMResponse(content='{"passed": true}', provider=LLMProvider.NIM, model="default", latency_ms=100)
                
                mock_query.side_effect = mock_fail_side_effect
                
                swarm = NIMSwarmOrchestrator()

                fail_prod = {
                    "id": "FAIL_001",
                    "name": "Low Margin Unstable Gadget",
                    "region": "India",
                    "competitor_flaw": "Fails constantly",
                    "upgrade_v2": "Unknown"
                }
                fail_econ = {
                    "gross_margin_pct": 30.0,
                    "net_profit_pct": 4.0,
                    "worst_case_stress_margin_pct": -5.0
                }
                res_fail = await swarm.run_full_swarm_audit(fail_prod, fail_econ)
                self.assertEqual(res_fail["consensus_status"], "CONSENSUS_FAIL")
                self.assertEqual(res_fail["backtracked_at"], "economics_auditor")
                self.assertIsNotNone(res_fail["reason"])

                # Verify audit logs in database
                audit_logs = get_swarm_audit_logs(product_id="FAIL_001")
                self.assertGreaterEqual(len(audit_logs), 2)
                has_backtrack = any(l["action"] == "BACKTRACK_ALARM" for l in audit_logs)
                self.assertTrue(has_backtrack)

        asyncio.run(test_passing())
        asyncio.run(test_failing())

    def test_unified_ssot_database_explorer(self):
        """Tests universal multi-table schema introspection and querying."""
        from core.database import get_all_table_names, get_table_data

        tables = get_all_table_names()
        self.assertIn("master_products", tables)
        self.assertIn("trend_signals", tables)
        self.assertIn("multi_platform_listings", tables)
        self.assertIn("swarm_audit_log", tables)

        # Test querying master_products
        data = get_table_data("master_products", limit=50)
        self.assertIsInstance(data, list)


if __name__ == "__main__":
    unittest.main()

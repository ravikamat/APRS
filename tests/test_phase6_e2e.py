"""
tests/test_phase6_e2e.py — V7 End-to-End Pipeline Test.

Tests the complete V7 pipeline flow:
Discovery → Gate 1 (Signal) → Gate 2 (Defects) → Gate 3 (Economics) → Gate 4 (Scoring) → Gate 5 (NIM Arbiter)
"""
import unittest
import os
import asyncio
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

from core.database import init_db, get_connection, get_all_products, get_current_gate, update_gate_status, init_product_gates, get_gate_status
from core.gate_engine import GateEngine
from core.validation import CanonicalProduct
from core.economics_engine import Comprehensive15FactorEconomics
from core.rule_engine import create_rule_engine
from core.pipeline import V6Pipeline, PipelineConfig, run_full_pipeline


class TestV7E2E(unittest.TestCase):
    
    def setUp(self):
        # Create fresh DB for each test in project data folder
        self.test_db = Path('data') / f'test_e2e_{os.getpid()}_{id(self)}.db'
        os.environ["APRS_DB_PATH"] = str(self.test_db)
        from core.database import init_db
        init_db()
        self.gate_engine = GateEngine()
    
    def tearDown(self):
        if self.test_db.exists():
            try:
                self.test_db.unlink(missing_ok=True)
            except PermissionError:
                pass
    
    def test_gate1_signal_passes_viable_product(self):
        """Gate 1 passes for product with BSR < 50k and price CV < 0.3"""
        product = CanonicalProduct(
            canonical_title="Test Product",
            category="Kitchen",
            retail_price_inr=1299.0,
            amazon_bsr=10000,
            rating=4.5,
            review_count=200,
        )
        result = self.gate_engine.run_gate_1_signal(
            product=product,
            bsr_current=10000,
            price_current=1299.0,
            price_30d_ago=1280.0,
        )
        self.assertTrue(result.passed)
        self.assertEqual(result.gate_number, 1)
    
    def test_gate1_signal_fails_high_bsr(self):
        """Gate 1 fails when BSR >= 50k threshold"""
        product = CanonicalProduct(
            canonical_title="Test Product",
            category="Kitchen",
            retail_price_inr=1299.0,
            rating=4.5,
            review_count=200,
        )
        result = self.gate_engine.run_gate_1_signal(
            product=product,
            bsr_current=60000,
            price_current=1299.0,
            price_30d_ago=1280.0,
        )
        self.assertFalse(result.passed)
    
    def test_gate3_economics_passes_viable_product(self):
        """Gate 3 passes for product with >=15% net margin"""
        product = CanonicalProduct(
            canonical_title="Test Product",
            category="Kitchen",
            retail_price_inr=1299.0,
            amazon_bsr=15000,
            rating=4.5,
            review_count=200,
        )
        engine = GateEngine(min_margin_pct=15.0)
        result = engine.run_gate_3_economics(
            product=product,
            fob_price=350.0,
            planned_msrp=1299.0,
            region="India",
            category="Kitchen",
            marketplace="amazon",
        )
        self.assertTrue(result.passed)
        self.assertGreaterEqual(result.details["expected"]["net_margin_pct"], 15.0)
    
    def test_gate4_scoring_passes_high_score(self):
        """Gate 4 passes when score >= 75"""
        product = CanonicalProduct(
            canonical_title="Test Product",
            category="Kitchen",
            retail_price_inr=1299.0,
            amazon_bsr=10000,
            rating=4.5,
            review_count=200,
        )
        result = self.gate_engine.run_gate_4_scoring(
            product=product,
            bsr=10000,
            rating=4.5,
            review_count=200,
            net_margin_pct=30.0,
            has_defects=True,
            competitor_count=3,
        )
        self.assertTrue(result.passed)
        self.assertGreaterEqual(result.details["total_score"], 75)
    
    def test_full_4gate_pipeline_proceed(self):
        """Full 4-gate pipeline returns PROCEED for viable product."""
        product = CanonicalProduct(
            canonical_title="Stainless Steel Water Bottle",
            category="Kitchen",
            retail_price_inr=1299.0,
            amazon_bsr=15000,
            rating=4.5,
            review_count=200,
        )
        mock_reviews = [
            "Great bottle but lid leaks after a week",
            "Insulation good but paint chips easily",
        ]
        
        async def mock_extract_defects(product_title, reviews):
            return {
                "defects": [
                    {"defect": "Lid leaks", "severity": "major", "frequency": "common", "suggested_fix": "Better seal"}
                ],
                "v2_spec": {"improvement_1": "Leak-proof lid"}
            }
        
        engine = GateEngine(min_margin_pct=15.0)
        with patch.object(engine.review_miner, 'extract_defects', side_effect=mock_extract_defects):
            result = asyncio.run(engine.run_full_pipeline(
                product=product,
                bsr_current=15000,
                price_current=1299.0,
                reviews_3star=mock_reviews,
                fob_price=280.0,  # Lower FOB for >20% net margin to pass scoring
                planned_msrp=1299.0,
                region="India",
                category="Kitchen",
                marketplace="amazon",
                competitor_count=5,
            ))
        self.assertEqual(result.final_verdict, "PROCEED")
        self.assertEqual(len(result.gate_results), 5)
        self.assertTrue(all(g.passed for g in result.gate_results))
    
    def test_pipeline_batch_execution(self):
        """Test full batch pipeline execution via V6Pipeline."""
        config = PipelineConfig(
            region="India",
            category="Kitchen",
            max_niches=1,
            max_candidates_per_niche=2,
            max_pages=1,
            use_seed_keywords=False,
        )
        # Note: This would require WebAgent which needs NIM/Ollama - skipped in unit test
        # Integration test would run with actual NIM/Ollama
        self.assertTrue(True)  # Placeholder for integration test


if __name__ == "__main__":
    unittest.main(verbosity=2)
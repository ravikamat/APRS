import unittest
import os
from pathlib import Path
from unittest.mock import patch

from core.orchestrator import AutonomousProductResearchOrchestrator
from core.database import (
    init_db, get_connection, get_all_products, 
    get_current_gate, update_gate_status, init_product_gates, get_gate_status
)
from tools.keepa_api_client import KeepaProduct

class TestPhase6E2E(unittest.TestCase):
    
    def setUp(self):
        # Create fresh DB for each test in project data folder
        self.test_db = Path('data') / f'test_e2e_{os.getpid()}_{id(self)}.db'
        os.environ["APRS_DB_PATH"] = str(self.test_db)
        from core.database import init_db
        init_db()
        self.orch = AutonomousProductResearchOrchestrator()
    
    def tearDown(self):
        if self.test_db.exists():
            try:
                self.test_db.unlink(missing_ok=True)
            except PermissionError:
                pass
    
    def test_full_pipeline_honest_flow(self):
        """Test the complete honest pipeline flow: Gate 1 -> Gate 2 -> Gate 3 -> Gate 4 -> Gate 5 -> Gate 6"""
        orch = self.orch
        
        # Mock Keepa and Scraper
        from unittest.mock import MagicMock, patch
        from tools.keepa_api_client import KeepaProduct
        
        mock_k = MagicMock()
        mock_prod = KeepaProduct(
            asin="B0TEST1234",
            title="Premium Kitchen Organizer System",
            current_price=149.99,  # Higher MSRP to pass stress test
            currency="USD",
            bsr_current=250,
            product_url="https://amazon.com/dp/B0TEST1234",
            price_30d_avg=145.0,
            price_90d_avg=142.0,
            price_historical_low=135.0,
            rating=4.5,
            review_count=100
        )
        mock_k.get_product.return_value = mock_prod
        mock_k._enabled = True
        
        mock_scraper_instance = MagicMock()
        mock_scraper_instance.search.return_value = [{"asin": "B0TEST1234", "title": "Premium Kitchen Organizer System", "price": 149.99}]
        
        orch.amazon_scraper = mock_scraper_instance
        orch.keepa = mock_k
        
        # Mock AI Supervisor to always return valid for test products
        from tools.ai_supervisor import get_supervisor, LLMRouter
        from models.llm_router import LLMResponse, LLMProvider
        from unittest.mock import AsyncMock
        
        supervisor = get_supervisor()
        with patch.object(LLMRouter, 'query', new_callable=AsyncMock) as mock_query:
            call_count = {"count": 0}
            
            async def mock_query_side_effect(prompt, task_type, **kwargs):
                call_count["count"] += 1
                stage = call_count["count"]
                
                from models.llm_router import LLMResponse, LLMProvider, LLMTaskType
                
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
            
            # Also mock the batch validation to return all valid
with patch.object(supervisor, 'validate_products_batch', return_value={"valid": 1, "invalid": 0, "auto_deleted": 0}):
            # Step 1: Discover - should block at Gate 2
            result = orch.discover_and_evaluate_products(region="USA", category="Kitchen Storage", max_candidates=1)
            
            self.assertTrue(len(result) > 0)
            self.assertEqual(result[0]["status"], "BLOCKED_AT_GATE_2")
            pid = result[0]["product_id"]
            
            # Step 2: Verify Gate 1 PASS, Gate 2 BLOCKED
            self.assertEqual(get_current_gate(pid), 2)
        
        # Step 3: Simulate Gate 2 manual completion
            conn = get_connection()
            cur = conn.cursor()
            cur.execute("UPDATE product_gate_progress SET status='PASS' WHERE product_id=? AND gate_number=2", (pid,))
            conn.commit()
            conn.close()
            
            # Step 4: Verify economics NOT computed yet (Gate 3 blocked)
            prods = get_all_products()
            target = next(p for p in prods if p["product_id"] == pid)
            self.assertEqual(target["status"], "PENDING")
            self.assertEqual(target["gross_margin_pct"], 0.0)  # Not faked
            
            # Step 5: Simulate Gate 4 FOB entry (proportional to MSRP, low enough to pass)
            conn = get_connection()
            cur = conn.cursor()
            cur.execute("UPDATE master_products SET factory_cogs = ? WHERE product_id = ?", (10.0, pid))
            conn.commit()
            conn.close()
            
            # Step 6: Re-evaluate Gate 3 (should now run)
            orch.re_evaluate_single_product(pid)
            
            # Step 7: Verify Gate 3 now has real economics
            prods = get_all_products()
            target = next(p for p in prods if p["product_id"] == pid)
            self.assertNotEqual(target["gross_margin_pct"], 0.0)
            self.assertNotEqual(target["net_profit_pct"], 0.0)
            
            # Step 6: Verify Gate 3 status
            gates = get_gate_status(pid)
            gate3 = next(g for g in gates if g['gate_number'] == 3)
            self.assertIn(gate3['status'], ['PASS', 'FAIL'])
            
            # Step 7: Simulate Gate 4 PASS (FOB already entered)
            update_gate_status(pid, 4, 'PASS', completed_by='human')
            
            # Step 8: Simulate Gate 5 PASS
            update_gate_status(pid, 5, 'PASS', completed_by='human')
            
            # Step 9: Verify Gate 6 can be generated
            gates = get_gate_status(pid)
            all_prior_passed = all(g['status'] in ('PASS', 'OVERRIDDEN') for g in get_gate_status(pid) if g['gate_number'] < 6)
            self.assertTrue(all_prior_passed)
            
            # Step 9: Verify Gate 6 can be marked PASS
            update_gate_status(pid, 6, 'PASS', completed_by='human')
            self.assertEqual(get_current_gate(pid), 7)

if __name__ == "__main__":
    unittest.main(verbosity=2)
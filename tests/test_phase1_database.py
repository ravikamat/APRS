import unittest
import os
import tempfile
from pathlib import Path

from core.database import init_db, get_connection, record_product_evaluation, get_current_gate, init_product_gates

class TestPhase1Database(unittest.TestCase):
    
    def setUp(self):
        # Create a unique temp database for each test
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / 'test_research_engine.db'
        os.environ["APRS_DB_PATH"] = str(self.db_path)
        init_db()
        self.conn = get_connection()
    
    def tearDown(self):
        try:
            self.conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
        except Exception:
            pass
        self.conn.close()
        # Remove DB files manually to avoid Windows lock on WAL/SHM
        import glob, gc
        gc.collect()
        for f in glob.glob(str(self.db_path) + "*"):
            try:
                os.unlink(f)
            except OSError:
                pass
        try:
            self.temp_dir.cleanup()
        except (PermissionError, OSError):
            pass  # Best-effort on Windows
    
    def test_pragma_foreign_keys_enabled(self):
        cur = self.conn.cursor()
        cur.execute("PRAGMA foreign_keys")
        self.assertEqual(cur.fetchone()[0], 1)
    
    def test_master_products_has_all_columns(self):
        cur = self.conn.cursor()
        cur.execute("PRAGMA table_info(master_products)")
        cols = {row[1] for row in cur.fetchall()}
        required = {
            "first_discovered_date", "last_evaluated_date", "keepa_price_stability",
            "helium_monthly_revenue", "factory_cogs", "landed_cogs", "estimated_cac",
            "gross_margin_pct", "net_profit_pct", "worst_case_stress_margin_pct",
            "overall_score", "consensus_status", "human_override_status",
            "sourcing_cluster", "marketplace_url", "competitor_3star_flaws",
            "upgrade_v2_engineering", "bsr_rank", "estimated_daily_units",
            "ad_active_days", "action_plan", "status"
        }
        self.assertTrue(required.issubset(cols), f"Missing: {required - cols}")
    
    def test_arbiter_decision_log_exists(self):
        cur = self.conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='arbiter_decision_log'")
        self.assertIsNotNone(cur.fetchone())
    
    def test_product_gate_progress_unique_constraint(self):
        # Create product first (FK requirement)
        cur = self.conn.cursor()
        cur.execute('''
            INSERT INTO master_products (product_id, name, category, region, planned_msrp, landed_cogs, gross_margin_pct, estimated_cac, net_profit_pct, worst_case_stress_margin_pct, status, overall_score, consensus_status, first_discovered_date, last_evaluated_date, sourcing_cluster)
            VALUES ('TEST_UNIQUE_001', 'Test', 'Cat', 'USA', 50, 10, 20, 5, 10, 5, 'PENDING', 50, 'PENDING', date('now'), date('now'), '')
        ''')
        self.conn.commit()
        
        init_product_gates("TEST_UNIQUE_001")
        # Second init should not create duplicates
        init_product_gates("TEST_UNIQUE_001")
        cur = self.conn.cursor()
        cur.execute("SELECT COUNT(*) FROM product_gate_progress WHERE product_id = ?", ("TEST_UNIQUE_001",))
        self.assertEqual(cur.fetchone()[0], 6)
    
    def test_record_product_evaluation_rejects_empty_econ(self):
        with self.assertRaises(ValueError) as ctx:
            record_product_evaluation(
                {"id": "TEST_EMPTY", "name": "Test", "category": "Test", "region": "USA", "retail_msrp": 50, "factory_cogs": 10, "est_cac": 5, "suppliers": []},
                {}
            )
        self.assertIn("cannot be empty", str(ctx.exception))
    
    def test_get_current_gate_auto_initializes(self):
        # Insert minimal product with all required NOT NULL columns
        cur = self.conn.cursor()
        cur.execute('''
            INSERT INTO master_products (product_id, name, category, region, planned_msrp, landed_cogs, gross_margin_pct, estimated_cac, net_profit_pct, worst_case_stress_margin_pct, status, overall_score, consensus_status, first_discovered_date, last_evaluated_date, sourcing_cluster)
            VALUES ('TEST_GATE_INIT', 'Test', 'Cat', 'USA', 50, 10, 20, 5, 10, 5, 'PENDING', 50, 'PENDING', date('now'), date('now'), '')
        ''')
        self.conn.commit()
        gate = get_current_gate("TEST_GATE_INIT")
        self.assertEqual(gate, 1)

if __name__ == "__main__":
    unittest.main(verbosity=2)
"""
tests/test_phase2_orchestrator.py — V7 AgentOrchestrator Tests.

Tests the deterministic agent orchestrator (replaces V5 AutonomousProductResearchOrchestrator).
"""
import unittest
import os
import tempfile
import glob
import gc
from pathlib import Path

from core.database import init_db, get_connection
from core.agent_orchestrator import AgentOrchestrator, AgentState, OrchestratorMode, AgentConfig


class TestPhase2Orchestrator(unittest.TestCase):

    def setUp(self):
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmp_dir.name) / f'test_orch_{os.getpid()}.db'
        os.environ["APRS_DB_PATH"] = str(self.db_path)
        init_db()

    def tearDown(self):
        try:
            conn = get_connection()
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
            conn.close()
        except Exception:
            pass
        gc.collect()
        for f in glob.glob(str(self.db_path) + "*"):
            try:
                os.unlink(f)
            except OSError:
                pass
        try:
            self._tmp_dir.cleanup()
        except (PermissionError, OSError):
            pass
        if "APRS_DB_PATH" in os.environ:
            del os.environ["APRS_DB_PATH"]

    def test_orchestrator_instantiation(self):
        """V7 AgentOrchestrator can be created with default config."""
        orch = AgentOrchestrator()
        self.assertIsNotNone(orch)
        self.assertEqual(orch.mode, OrchestratorMode.SINGLE_CYCLE)

    def test_agent_order_has_all_agents(self):
        """Agent execution order includes all 16 pipeline agents."""
        orch = AgentOrchestrator()
        expected = [
            "strategy_planner", "ai_scout", "internet_crawler", "trend_signal",
            "demand_sense", "competition_xray", "niche_expander", "discovery",
            "problem_miner", "gate_engine", "supplier_agent", "outreach_engine",
            "winner_score", "maintenance", "weight_tuner", "learning_agent",
        ]
        self.assertEqual(orch.AGENT_ORDER, expected)

    def test_agent_configs_loaded(self):
        """Each agent should have a config entry."""
        orch = AgentOrchestrator()
        for agent_name in orch.AGENT_ORDER:
            self.assertIn(agent_name, orch._agent_configs,
                          f"Missing config for agent: {agent_name}")

    def test_agent_initial_state_is_idle(self):
        """All agents should start in IDLE state."""
        orch = AgentOrchestrator()
        for agent_name in orch.AGENT_ORDER:
            state = orch._agent_states.get(agent_name)
            self.assertEqual(state, AgentState.IDLE,
                             f"Agent {agent_name} should start IDLE, got {state}")


if __name__ == '__main__':
    unittest.main()
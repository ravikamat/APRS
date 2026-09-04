"""
tests/test_ollama_manager.py — Unit tests for Ollama background lifecycle manager.
"""
import unittest
from unittest.mock import patch, MagicMock

from core.ollama_manager import is_ollama_running, ensure_ollama_running, get_installed_models


class TestOllamaManager(unittest.TestCase):

    def test_is_ollama_running_live_or_mocked(self):
        """is_ollama_running returns boolean."""
        res = is_ollama_running("http://localhost:11434")
        self.assertIsInstance(res, bool)

    def test_is_ollama_running_offline_port(self):
        """is_ollama_running returns False on non-existent port."""
        res = is_ollama_running("http://localhost:59999", timeout=0.2)
        self.assertFalse(res)

    @patch("core.ollama_manager.is_ollama_running")
    def test_ensure_ollama_running_when_already_active(self, mock_is_running):
        """ensure_ollama_running returns True immediately if already running."""
        mock_is_running.return_value = True
        self.assertTrue(ensure_ollama_running())

    @patch("core.ollama_manager.subprocess.Popen")
    @patch("core.ollama_manager.is_ollama_running")
    def test_ensure_ollama_running_spawns_process(self, mock_is_running, mock_popen):
        """ensure_ollama_running spawns background daemon when inactive."""
        # First call False, second call True
        mock_is_running.side_effect = [False, True]
        res = ensure_ollama_running(max_wait_sec=2)
        self.assertTrue(res)
        mock_popen.assert_called_once()


if __name__ == "__main__":
    unittest.main()

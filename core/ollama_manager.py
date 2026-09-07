"""
core/ollama_manager.py — Automatic lifecycle manager for local Ollama server.

Ensures Ollama is running in the background whenever an agent or router needs it.
No manual 'ollama serve' required from the user.
"""
import os
import sys
import time
import json
import logging
import subprocess
import urllib.request
import urllib.error
from typing import List, Optional

logger = logging.getLogger(__name__)


def is_ollama_running(url: str = "http://localhost:11434", timeout: float = 1.5) -> bool:
    """Checks whether the Ollama server is responding to HTTP requests."""
    try:
        req = urllib.request.Request(
            f"{url.rstrip('/')}/api/tags",
            headers={"User-Agent": "APRS-OllamaManager/1.0"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


def pull_ollama_model(model: str, url: str = "http://localhost:11434", max_wait_sec: int = 300) -> bool:
    """Pull a model from Ollama registry if not already installed."""
    try:
        logger.info(f"Pulling Ollama model: {model}...")
        result = subprocess.run(
            ["ollama", "pull", model],
            capture_output=True,
            text=True,
            timeout=max_wait_sec
        )
        if result.returncode == 0:
            logger.info(f"Successfully pulled model: {model}")
            return True
        else:
            logger.error(f"Failed to pull model {model}: {result.stderr}")
            return False
    except subprocess.TimeoutExpired:
        logger.error(f"Model pull timed out after {max_wait_sec}s")
        return False
    except Exception as e:
        logger.error(f"Error pulling model {model}: {e}")
        return False


def ensure_model_available(model: str, url: str = "http://localhost:11434") -> bool:
    """Ensure model is installed, pull if missing."""
    if not ensure_ollama_running(url):
        return False
    
    # Check if model exists
    try:
        req = urllib.request.Request(f"{url.rstrip('/')}/api/tags")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            models = [m.get("name", "") for m in data.get("models", [])]
            # Check for exact match or with tag
            for m in models:
                if m == model or m.startswith(model + ":"):
                    return True
    except Exception:
        pass
    
    # Model not found, pull it
    return pull_ollama_model(model, url)


def ensure_ollama_running(url: str = "http://localhost:11434", max_wait_sec: int = 15) -> bool:
    """
    Guarantees that Ollama is running. If offline, automatically spawns 'ollama serve'
    in the background as a detached daemon process without popping up console windows.
    """
    if is_ollama_running(url):
        return True

    logger.info(f"Ollama server is offline at {url}. Initiating auto-start in background...")

    creationflags = 0
    if sys.platform == "win32":
        # 0x08000000 = CREATE_NO_WINDOW, 0x00000008 = DETACHED_PROCESS
        creationflags = subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS

    try:
        subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            creationflags=creationflags,
            shell=False,
            close_fds=(sys.platform != "win32")
        )

        # Wait up to max_wait_sec for server port to bind
        start_time = time.time()
        while time.time() - start_time < max_wait_sec:
            time.sleep(0.8)
            if is_ollama_running(url, timeout=1.0):
                elapsed = time.time() - start_time
                logger.info(f"Ollama server auto-started successfully in {elapsed:.1f}s.")
                return True

        logger.warning(f"Ollama 'serve' command executed, but server did not respond within {max_wait_sec}s.")
        return False

    except FileNotFoundError:
        logger.error("'ollama' command not found in PATH. Please install Ollama from https://ollama.com")
        return False
    except Exception as e:
        logger.error(f"Unexpected error while attempting to auto-start Ollama: {e}")
        return False


def get_installed_models(url: str = "http://localhost:11434") -> List[str]:
    """Returns list of installed model tags in Ollama."""
    if not ensure_ollama_running(url):
        return []
    try:
        req = urllib.request.Request(f"{url.rstrip('/')}/api/tags")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return [m.get("name", "") for m in data.get("models", [])]
    except Exception as e:
        logger.error(f"Failed to fetch Ollama models: {e}")
        return []

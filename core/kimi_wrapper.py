"""
core/kimi_wrapper.py — Kimi-K3 (2.78T) C Binary Wrapper for APRS V7.

Wraps the kimi-k3-in-c C99 binary via subprocess/WSL2.
Only used for overnight batch deep reasoning tasks due to slow speed.

IMPORTANT constraints:
- Requires 1.56 TB model checkpoint on disk (not included — must download)
- Linux x86-64 only (binary won't run on Windows natively)
- 26.5 s/token on 8GB RAM — use ONLY for batch overnight tasks
- Windows workaround: run inside WSL2 or Docker Linux container

Setup (one-time):
  1. WSL2: wsl --install
  2. Inside WSL: cd /mnt/h/trade/kimi-k3-in-c && make
  3. Download 1.56 TB checkpoint (Hugging Face: moonshotai/Kimi-K3)
  4. Set KIMI_MODEL_PATH in .env

Practical reality:
- At 26.5 s/token, a 200-token response = ~88 minutes
- ONLY suitable for: weekly synthesis report, overnight deep analysis,
  one-time product category deep dive (schedule Sunday 00:00, done by 06:00)
- NOT suitable for: any real-time decision, scraping, gate validation
"""

import asyncio
import logging
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Any, Optional

from config.settings import settings

logger = logging.getLogger("aprs.kimi_wrapper")


@dataclass
class KimiResponse:
    """Kimi-K3 response wrapper."""
    content: str
    model: str = "kimi-k3-2.78T"
    latency_ms: int = 0
    tokens_used: int = 0
    success: bool = True
    error: Optional[str] = None


class KimiK3Wrapper:
    """
    Wraps the kimi-k3-in-c C99 binary via subprocess/WSL2.
    
    ONLY used for overnight batch deep reasoning tasks due to slow speed.
    """
    
    def __init__(self):
        self.binary_path = "wsl /mnt/h/trade/kimi-k3-in-c/bin/k3"
        self._available: Optional[bool] = None
    
    def is_available(self) -> bool:
        """Check: WSL installed + binary compiled + model checkpoint exists."""
        if self._available is not None:
            return self._available
        
        try:
            result = subprocess.run(["wsl", "--status"], capture_output=True, timeout=5)
            model_path = settings.kimi_model_path
            available = result.returncode == 0 and Path(model_path).exists()
            self._available = available
            return available
        except Exception:
            self._available = False
            return False
    
    async def chat(self, messages: List[Dict[str, str]], max_tokens: int = 100) -> KimiResponse:
        """
        Call kimi-k3 binary via WSL subprocess.
        
        Args:
            messages: OpenAI-style messages list
            max_tokens: Maximum tokens to generate
            
        Returns:
            KimiResponse with content and metadata
        """
        if not self.is_available():
            return KimiResponse(
                content="",
                latency_ms=0,
                success=False,
                error="kimi-k3 not available (WSL/binary/model missing)",
            )
        
        # Convert messages to a single prompt (kimi-k3 is a base model, no chat template)
        prompt = self._messages_to_prompt(messages)
        
        # Build command
        cmd = [
            "wsl", "/mnt/h/trade/kimi-k3-in-c/bin/k3",
            settings.kimi_model_path,
            "--trunk", settings.kimi_trunk_path,
            "--preset", settings.kimi_preset,  # "laptop" | "server"
            "--tok", settings.kimi_model_path,
            "--prompt", prompt,
            "--gen", str(max_tokens),
            "--incremental"
        ]
        
        start = time.time()
        try:
            # Use asyncio subprocess for non-blocking
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=max_tokens * 35  # 35s/token safety buffer
            )
            
            latency_ms = int((time.time() - start) * 1000)
            
            if proc.returncode != 0:
                error_msg = stderr.decode() if stderr else "Unknown error"
                return KimiResponse(
                    content="",
                    latency_ms=latency_ms,
                    success=False,
                    error=f"kimi-k3 exited with code {proc.returncode}: {error_msg}",
                )
            
            # Parse output between "--- generated text ---" markers
            output = self._extract_generated_text(stdout.decode())
            
            return KimiResponse(
                content=output,
                latency_ms=latency_ms,
                success=True,
            )
            
        except asyncio.TimeoutError:
            return KimiResponse(
                content="",
                latency_ms=int((time.time() - start) * 1000),
                success=False,
                error=f"kimi-k3 timed out after {max_tokens * 35}s",
            )
        except Exception as e:
            return KimiResponse(
                content="",
                latency_ms=int((time.time() - start) * 1000),
                success=False,
                error=f"kimi-k3 error: {e}",
            )
    
    def _messages_to_prompt(self, messages: List[Dict[str, str]]) -> str:
        """Convert OpenAI-style messages to a single prompt for kimi-k3 base model."""
        parts = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                parts.append(f"System: {content}")
            elif role == "user":
                parts.append(f"User: {content}")
            elif role == "assistant":
                parts.append(f"Assistant: {content}")
        return "\n\n".join(parts)
    
    def _extract_generated_text(self, stdout: str) -> str:
        """Extract generated text from kimi-k3 output between markers."""
        import re
        # kimi-k3 outputs generated text between "--- generated text ---" markers
        match = re.search(r"--- generated text ---\s*(.*?)\s*---", stdout, re.DOTALL)
        if match:
            return match.group(1).strip()
        # Fallback: return last few lines
        lines = stdout.strip().split('\n')
        return '\n'.join(lines[-5:]) if lines else ""
    
    def get_status(self) -> Dict[str, Any]:
        """Get wrapper status for monitoring."""
        return {
            "available": self.is_available(),
            "binary_path": self.binary_path,
            "model_path": settings.kimi_model_path,
            "preset": settings.kimi_preset,
        }


if __name__ == "__main__":
    async def test():
        wrapper = KimiK3Wrapper()
        print("Kimi-K3 Status:", wrapper.get_status())
        
        if wrapper.is_available():
            print("Kimi-K3 is available, running test...")
            messages = [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "What is 2+2?"}
            ]
            response = await wrapper.chat(messages, max_tokens=50)
            print(f"Response: {response.content}")
            print(f"Success: {response.success}, Latency: {response.latency_ms}ms")
        else:
            print("Kimi-K3 not available (WSL/binary/model missing)")
            print("Setup required:")
            print("  1. WSL2: wsl --install")
            print("  2. Inside WSL: cd /mnt/h/trade/kimi-k3-in-c && make")
            print("  3. Download 1.56 TB checkpoint (Hugging Face: moonshotai/Kimi-K3)")
            print("  4. Set KIMI_MODEL_PATH in .env")
    
    asyncio.run(test())
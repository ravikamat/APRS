"""
tools/import_gguf_to_ollama.py — Helper to Register Any Local Quantized GGUF Model into Ollama.

Allows loading quantized 27B / 14B / 8B GGUF weights directly into system RAM
without Python memory bloat, enabling zero-cost local LLM fallback for APRS.
"""
import argparse
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent


def register_gguf_in_ollama(gguf_path: str, model_name: str, context_window: int = 8192, update_env: bool = True):
    path_obj = Path(gguf_path)
    if not path_obj.exists():
        print(f"❌ Error: GGUF file not found at: {gguf_path}")
        return False

    posix_path = path_obj.as_posix()
    modelfile_content = (
        f'FROM "{posix_path}"\n'
        f'PARAMETER temperature 0.2\n'
        f'PARAMETER num_ctx {context_window}\n'
        f'PARAMETER stop "<|im_end|>"\n'
        f'PARAMETER stop "<|endoftext|>"\n'
        f'SYSTEM """You are an expert e-commerce product intelligence assistant. '
        f'You provide structured, data-driven analysis and respond in valid JSON format only."""\n'
    )

    modelfile_path = _ROOT / "data" / f"Modelfile_{model_name}"
    modelfile_path.parent.mkdir(parents=True, exist_ok=True)
    modelfile_path.write_text(modelfile_content, encoding="utf-8")
    print(f"📄 Generated Modelfile at: {modelfile_path}")

    print(f"🚀 Registering model '{model_name}' with Ollama...")
    try:
        res = subprocess.run(["ollama", "create", model_name, "-f", str(modelfile_path)], capture_output=True, text=True, check=True)
        print(f"✅ Successfully registered '{model_name}' in Ollama!")
        if res.stdout:
            print(res.stdout)
    except FileNotFoundError:
        print("❌ Error: 'ollama' CLI command not found. Ensure Ollama is installed and running.")
        return False
    except subprocess.CalledProcessError as e:
        print(f"❌ Ollama create failed: {e.stderr}")
        return False

    if update_env:
        env_file = _ROOT / ".env"
        if env_file.exists():
            lines = env_file.read_text(encoding="utf-8").splitlines()
            new_lines = []
            set_var = False
            for line in lines:
                if line.startswith("LOCAL_OLLAMA_MODEL="):
                    new_lines.append(f"LOCAL_OLLAMA_MODEL={model_name}")
                    set_var = True
                else:
                    new_lines.append(line)
            if not set_var:
                new_lines.append(f"LOCAL_OLLAMA_MODEL={model_name}")
            env_file.write_text("\n".join(new_lines), encoding="utf-8")
            print(f"⚙️ Updated .env with LOCAL_OLLAMA_MODEL={model_name}")

    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Register local quantized GGUF model in Ollama")
    parser.add_argument("--path", required=True, help="Full path to the .gguf file")
    parser.add_argument("--name", default="qwen27b-local", help="Name for the model in Ollama")
    parser.add_argument("--ctx", type=int, default=8192, help="Context window size (default: 8192)")
    parser.add_argument("--no-env", action="store_true", help="Do not update .env file")

    args = parser.parse_args()
    register_gguf_in_ollama(args.path, args.name, context_window=args.ctx, update_env=not args.no_env)

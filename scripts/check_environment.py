#!/usr/bin/env python3
"""
ORCA Environment & Prerequisites Check Script.
Verifies system dependencies, Python runtime, Node runtime, and environment variables.
"""
import os
import sys
import shutil
import subprocess
from pathlib import Path

def print_status(component: str, ok: bool, details: str = ""):
    symbol = "✓" if ok else "✗"
    color = "\033[92m" if ok else "\033[91m"
    reset = "\033[0m"
    print(f"[{color}{symbol}{reset}] {component:25} {details}")

def main():
    print("=" * 60)
    print("ORCA System & Environment Check")
    print("=" * 60)

    # 1. Python version
    py_ver = sys.version_info
    py_ok = (py_ver.major == 3 and py_ver.minor >= 11)
    print_status("Python Runtime", py_ok, f"{py_ver.major}.{py_ver.minor}.{py_ver.micro}")

    # 2. Node.js check
    node_bin = shutil.which("node")
    if node_bin:
        try:
            node_ver = subprocess.check_output(["node", "--version"], text=True).strip()
            print_status("Node.js Runtime", True, node_ver)
        except Exception:
            print_status("Node.js Runtime", False, "Error querying node")
    else:
        print_status("Node.js Runtime", False, "Node binary not found on PATH")

    # 3. Environment configuration
    root_dir = Path(__file__).resolve().parent.parent
    env_file = root_dir / ".env"
    env_example = root_dir / ".env.example"

    print_status(".env.example", env_example.exists(), "Template available")
    print_status(".env Active File", env_file.exists(), "Configured" if env_file.exists() else "Missing (copy from .env.example)")

    # 4. Check critical environment variables
    groq_key = os.getenv("GROQ_API_KEY", "")
    gemini_key = os.getenv("GEMINI_API_KEY", "")
    openrouter_key = os.getenv("OPENROUTER_API_KEY", "")

    llm_present = bool(groq_key or gemini_key or openrouter_key)
    print_status("LLM Provider Keys", llm_present, f"Groq={'yes' if groq_key else 'no'}, Gemini={'yes' if gemini_key else 'no'}, OpenRouter={'yes' if openrouter_key else 'no'}")

    print("=" * 60)
    print("Environment check completed.")

if __name__ == "__main__":
    main()

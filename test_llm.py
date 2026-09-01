import sys
from pathlib import Path

# Add backend to path so we can import modules
sys.path.append(str(Path("backend").resolve()))

import config
import llm

# Ensure we test gemini directly
config.LLM_PROVIDER = "gemini"
config.LLM_FALLBACK_PROVIDERS = ""

try:
    print(f"Testing Gemini API with model: {config.GEMINI_MODEL}")
    result = llm.call_llm(
        system_prompt="You are a helpful assistant. Always return JSON.",
        user_prompt="Return a JSON object with a key 'status' and value 'ok'.",
    )
    print("SUCCESS! Result:")
    print(result)
except Exception as e:
    import traceback
    print(f"ERROR: {e}")
    traceback.print_exc()

"""DRIFTIQ MVP — Configuration
Loads settings from environment variables (.env file).
Change LLM_PROVIDER and ASR_PROVIDER to swap between backends without code changes.
"""
import os
from pathlib import Path

# Load .env from project root if present
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass


# ============ ASR (Speech-to-Text) ============
# Options: "local" (Whisper on your machine, free), "groq" (Whisper Large-v3, free tier),
#          "openai" (OpenAI Whisper API, paid)
ASR_PROVIDER = os.getenv("ASR_PROVIDER", "local").lower()

# Local Whisper model size: tiny, base, small, medium, large
# Bigger = more accurate but slower and needs more RAM.
# base = ~150 MB, good enough for MVP testing.
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "base")

# API keys (only needed for the provider you actually use)
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_LLM_MODEL = os.getenv("GROQ_LLM_MODEL", "llama-3.1-8b-instant")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")


# ============ LLM (Structured Extraction) ============
# Options: "ollama" (local, free), "gemini" (Google, free tier),
#          "openai" (GPT), "claude" (Anthropic)
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama").lower()

# Fallback providers tried in order if the primary fails (comma-separated).
# Example: "groq,gemini" means try Groq first, then Gemini on failure.
# Leave empty to disable fallback (hard-fail on primary error).
LLM_FALLBACK_PROVIDERS = os.getenv("LLM_FALLBACK_PROVIDERS", "")

# Model per provider — sensible defaults, override with env if you want
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
OLLAMA_HOST  = os.getenv("OLLAMA_HOST", "http://localhost:11434")

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

OPENAI_LLM_MODEL = os.getenv("OPENAI_LLM_MODEL", "gpt-4o-mini")

CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-haiku-4-5")
CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY", "") or os.getenv("ANTHROPIC_API_KEY", "")


# ============ Database ============
# Postgres in production (Neon / Supabase / Railway). If DATABASE_URL is not
# set, fall back to a local SQLite file so dev works without Postgres.
_DEFAULT_SQLITE = f"sqlite:///{(Path(__file__).parent.parent / 'driftiq.db').as_posix()}"
DATABASE_URL = os.getenv("DATABASE_URL", "") or _DEFAULT_SQLITE


# ============ Auth ============
# HS256 signing secret for JWTs. The dev default is fine locally but MUST
# be overridden in any deployed environment.
JWT_SECRET = os.getenv("JWT_SECRET", "driftiq-dev-only-secret-change-me-in-production")
JWT_EXPIRES_MINUTES = int(os.getenv("JWT_EXPIRES_MINUTES", "10080"))  # 7 days


# ============ Server ============
PORT = int(os.getenv("PORT", "8000"))
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "/tmp/driftiq_uploads"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Reject raw uploads above this size (a 50-min m4a is ~50 MB; webm/opus less).
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "200"))

# API ASR providers cap request size (Groq/OpenAI: 25 MB). Transcoded audio
# above this is split into sequential chunks before transcription.
ASR_CHUNK_MB = int(os.getenv("ASR_CHUNK_MB", "20"))


def summary() -> str:
    return (
        f"DRIFTIQ config:\n"
        f"  ASR       : {ASR_PROVIDER}  (whisper model={WHISPER_MODEL})\n"
        f"  LLM       : {LLM_PROVIDER}\n"
        f"  Port      : {PORT}\n"
        f"  UploadDir : {UPLOAD_DIR}"
    )

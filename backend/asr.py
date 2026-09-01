"""DRIFTIQ — Speech-to-Text abstraction.
Swappable ASR providers behind a single transcribe() function.

Accuracy & Multilingual improvements (v3):
  - Language constraint REMOVED — Whisper auto-detects and handles code-switching
    (e.g. Tamil ↔ English mid-sentence, as common in Indian classrooms)
  - Local Whisper: beam_size=5, vad_filter=True, temperature=0, per-segment lang tags
  - Groq: whisper-large-v3-turbo, verbose_json for detected language
  - OpenAI: verbose_json for detected language
  - transcribe() returns (transcript: str, detected_lang: str) tuple
"""
from __future__ import annotations
from pathlib import Path
import requests
import config


# Language code → readable name mapping for common Indian classroom languages
LANG_NAMES = {
    "en": "English", "ta": "Tamil", "hi": "Hindi", "te": "Telugu",
    "kn": "Kannada", "ml": "Malayalam", "mr": "Marathi", "bn": "Bengali",
    "gu": "Gujarati", "pa": "Punjabi", "ur": "Urdu",
}


def _lang_label(code: str) -> str:
    return LANG_NAMES.get(code.lower(), code.upper())


# ---------- Provider implementations — return (transcript, detected_language) ----------

_local_model = None

def _local_whisper(audio_path: str, initial_prompt: str = "") -> tuple[str, str]:
    """Local Whisper via faster-whisper — full multilingual code-switching support.

    With language=None, Whisper auto-detects the primary language but naturally
    handles mid-sentence switches (Tamil→English, Hindi→English etc.).
    Per-segment language tags are injected when the detected language is non-English,
    making the transcript show exactly which portions were in which language.
    """
    global _local_model
    if _local_model is None:
        from faster_whisper import WhisperModel
        _local_model = WhisperModel(config.WHISPER_MODEL, device="cpu", compute_type="int8")

    segments_gen, info = _local_model.transcribe(
        audio_path,
        beam_size=5,
        language=None,          # ← removed "en" constraint — auto-detect per-audio
        temperature=0,
        vad_filter=True,
        initial_prompt=initial_prompt or None,
        word_timestamps=False,
    )

    detected = (info.language or "en").lower()
    segments = list(segments_gen)

    if detected == "en":
        # English-only: clean transcript, no annotations needed
        transcript = " ".join(seg.text.strip() for seg in segments).strip()
    else:
        # Non-English or code-switched: annotate with language label
        parts = []
        lang_label = _lang_label(detected)
        parts.append(f"[🌐 {lang_label}–English code-switching detected]")
        for seg in segments:
            parts.append(seg.text.strip())
        transcript = " ".join(parts).strip()

    return transcript, detected


def _groq_whisper(audio_path: str, initial_prompt: str = "") -> tuple[str, str]:
    """Groq Whisper Large-v3-Turbo — multilingual, verbose_json for language detection."""
    if not config.GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY not set — cannot use Groq ASR.")
    url = "https://api.groq.com/openai/v1/audio/transcriptions"
    with open(audio_path, "rb") as f:
        files = {"file": (Path(audio_path).name, f, "audio/mpeg")}
        data = {
            "model":           "whisper-large-v3-turbo",
            "response_format": "verbose_json",  # returns language field
            "temperature":     "0",
            # No language= field → multilingual auto-detection
        }
        if initial_prompt:
            data["prompt"] = initial_prompt
        headers = {"Authorization": f"Bearer {config.GROQ_API_KEY}"}
        r = requests.post(url, headers=headers, files=files, data=data, timeout=300)
    r.raise_for_status()
    body = r.json()
    transcript = body.get("text", "").strip()
    detected = (body.get("language") or "en").lower()
    # Annotate non-English transcripts
    if detected != "en":
        transcript = f"[🌐 {_lang_label(detected)}–English code-switching detected]\n{transcript}"
    return transcript, detected


def _openai_whisper(audio_path: str, initial_prompt: str = "") -> tuple[str, str]:
    """OpenAI Whisper API — multilingual, verbose_json for language detection."""
    if not config.OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY not set — cannot use OpenAI ASR.")
    url = "https://api.openai.com/v1/audio/transcriptions"
    with open(audio_path, "rb") as f:
        files = {"file": (Path(audio_path).name, f, "audio/mpeg")}
        data = {
            "model":           "whisper-1",
            "response_format": "verbose_json",
            "temperature":     "0",
        }
        if initial_prompt:
            data["prompt"] = initial_prompt
        headers = {"Authorization": f"Bearer {config.OPENAI_API_KEY}"}
        r = requests.post(url, headers=headers, files=files, data=data, timeout=600)
    r.raise_for_status()
    body = r.json()
    transcript = body.get("text", "").strip()
    detected = (body.get("language") or "en").lower()
    if detected != "en":
        transcript = f"[🌐 {_lang_label(detected)}–English code-switching detected]\n{transcript}"
    return transcript, detected


_ROUTES = {
    "local":  _local_whisper,
    "groq":   _groq_whisper,
    "openai": _openai_whisper,
}


# ---------- Public API ----------

def _fmt_offset(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 60:02d}:{s % 60:02d}"


def transcribe(audio_path: str, initial_prompt: str = "") -> tuple[str, str]:
    """Transcribe an audio file to plain text + detected language code.

    Returns:
        (transcript: str, detected_language: str)
        detected_language is an ISO 639-1 code, e.g. "en", "ta", "hi"

    With language auto-detection enabled, Whisper handles code-switching
    (Tamil ↔ English, Hindi ↔ English etc.) naturally. Non-English segments
    are annotated with a language label so the professor can see which parts
    were in which language.

    `initial_prompt` seeds the model with subject vocabulary (e.g. "DBMS, SQL")
    for improved technical term recognition.

    API providers cap request size — oversized files are split into sequential
    chunks with time-offset markers (see config.ASR_CHUNK_MB).
    """
    provider = config.ASR_PROVIDER
    if provider not in _ROUTES:
        raise ValueError(f"Unknown ASR provider: {provider}. Options: {list(_ROUTES)}")
    fn = _ROUTES[provider]
    if provider == "local":
        return fn(audio_path, initial_prompt)

    import audio_prep
    chunks = audio_prep.split_if_needed(Path(audio_path), config.ASR_CHUNK_MB * 1024 * 1024)
    if len(chunks) == 1:
        return fn(audio_path, initial_prompt)

    parts = []
    detected = "en"
    try:
        for chunk_path, offset in chunks:
            text, lang = fn(str(chunk_path), initial_prompt)
            if lang != "en":
                detected = lang   # report non-English if any chunk has it
            if offset:
                parts.append(f"[continued at {_fmt_offset(offset)}]\n{text}")
            else:
                parts.append(text)
    finally:
        for chunk_path, _ in chunks:
            if str(chunk_path) != audio_path:
                chunk_path.unlink(missing_ok=True)
    return "\n\n".join(parts), detected

"""DRIFTIQ — Audio preprocessing for ASR.
Transcodes uploads to 16 kHz mono 32 kbps MP3 (a 50-min lecture lands
around 12 MB) and splits oversized results into sequential chunks so
API ASR providers with request-size limits (Groq/OpenAI: 25 MB) never
see a file they cannot take.

ffmpeg comes from the system PATH when available, otherwise from the
static binary shipped by the imageio-ffmpeg wheel (Render's Python
runtime has no apt, so this is how the build gets ffmpeg).
"""
from __future__ import annotations
import math
import re
import shutil
import subprocess
from pathlib import Path


def find_ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        raise RuntimeError(
            "ffmpeg not found — install ffmpeg or `pip install imageio-ffmpeg`"
        )


def transcode_for_asr(src: Path) -> Path:
    """Transcode any input audio to 16 kHz mono 32 kbps MP3 next to src."""
    dst = src.with_name(src.stem + "_asr.mp3")
    subprocess.run(
        [find_ffmpeg(), "-y", "-hide_banner", "-loglevel", "error",
         "-i", str(src), "-vn", "-ac", "1", "-ar", "16000", "-b:a", "32k",
         str(dst)],
        check=True, capture_output=True, timeout=600,
    )
    return dst


def duration_seconds(path: Path) -> float:
    """Media duration. Static ffmpeg builds ship no ffprobe, so parse the
    `Duration: HH:MM:SS.cc` line ffmpeg prints for any input."""
    proc = subprocess.run(
        [find_ffmpeg(), "-hide_banner", "-i", str(path)],
        capture_output=True, text=True, timeout=60,
    )
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", proc.stderr)
    if not m:
        raise RuntimeError(f"Could not read duration of {path.name}")
    h, mnt, sec = int(m.group(1)), int(m.group(2)), float(m.group(3))
    return h * 3600 + mnt * 60 + sec


def split_if_needed(path: Path, max_bytes: int) -> list[tuple[Path, float]]:
    """Return [(chunk_path, start_offset_seconds)]. A file within the limit
    comes back as a single entry pointing at the original (no copy)."""
    size = path.stat().st_size
    if size <= max_bytes:
        return [(path, 0.0)]
    total = duration_seconds(path)
    n_chunks = math.ceil(size / (max_bytes * 0.9))  # 10% headroom per chunk
    seg_time = max(60.0, total / n_chunks)
    pattern = path.with_name(f"{path.stem}_part%03d{path.suffix}")
    subprocess.run(
        [find_ffmpeg(), "-y", "-hide_banner", "-loglevel", "error",
         "-i", str(path), "-f", "segment", "-segment_time", str(seg_time),
         "-c", "copy", str(pattern)],
        check=True, capture_output=True, timeout=600,
    )
    parts = sorted(path.parent.glob(f"{path.stem}_part*{path.suffix}"))
    if not parts:
        raise RuntimeError(f"ffmpeg produced no segments for {path.name}")
    return [(p, i * seg_time) for i, p in enumerate(parts)]

"""تنظیمات کلی برنامه."""
from __future__ import annotations

import os
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
ROOT_DIR = APP_DIR.parent
JOBS_DIR = ROOT_DIR / "jobs"
STATIC_DIR = APP_DIR / "static"
FONT_DIR = APP_DIR / "fonts"

def _default_model_path() -> str:
    """WHISPER_MODEL یا اولین مسیر موجود از گزینه‌های متداول."""
    env = os.environ.get("WHISPER_MODEL")
    if env:
        return env
    candidates = [
        ROOT_DIR / "models" / "large-v3-turbo-local",
        ROOT_DIR / "models" / "large-v3-turbo",
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return str(ROOT_DIR / "models" / "large-v3-turbo")


MODEL_PATH = _default_model_path()
MODEL_LABEL = os.environ.get("WHISPER_LABEL", Path(MODEL_PATH).name or "large-v3-turbo")

HOST = os.environ.get("SUBS_HOST", "127.0.0.1")
BASE_PORT = int(os.environ.get("SUBS_PORT", "7861"))

FONT_NAME = "Vazirmatn"
FONT_FILE = FONT_DIR / "Vazirmatn-Regular.ttf"

FFMPEG = os.environ.get("FFMPEG_BIN", "ffmpeg")
FFPROBE = os.environ.get("FFPROBE_BIN", "ffprobe")

CPU_THREADS = int(os.environ.get("SUBS_THREADS", "8"))

# محدودیت‌ها
MAX_UPLOAD_BYTES = 12 * 1024**3  # ۱۲ گیگابایت
ALLOWED_EXT = {
    ".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v", ".ts", ".flv", ".wmv",
    ".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".wma",
}

JOBS_DIR.mkdir(parents=True, exist_ok=True)

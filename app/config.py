"""تنظیمات کلی برنامه."""
from __future__ import annotations

import os
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
ROOT_DIR = APP_DIR.parent
JOBS_DIR = ROOT_DIR / "jobs"
MODELS_DIR = ROOT_DIR / "models"
TOOLS_DIR = ROOT_DIR / "tools"
STATIC_DIR = APP_DIR / "static"
FONT_DIR = APP_DIR / "fonts"


def _default_model_path() -> str:
    """WHISPER_MODEL یا اولین مسیر موجود از گزینه‌های متداول."""
    env = os.environ.get("WHISPER_MODEL")
    if env:
        return env
    for name in ("large-v3-turbo", "large-v3-turbo-local"):
        candidate = MODELS_DIR / name
        if candidate.exists():
            return str(candidate)
    return str(MODELS_DIR / "large-v3-turbo")


MODEL_PATH = _default_model_path()
MODEL_LABEL = os.environ.get("WHISPER_LABEL", Path(MODEL_PATH).name or "large-v3-turbo")

HOST = os.environ.get("SUBS_HOST", "127.0.0.1")
BASE_PORT = int(os.environ.get("SUBS_PORT", "7861"))

FONT_NAME = "Vazirmatn"
FONT_FILE = FONT_DIR / "Vazirmatn-Regular.ttf"


def _binary(name: str, env_var: str) -> str:
    """اول متغیر محیطی، بعد نسخه‌ی همراه برنامه در tools/، بعد PATH."""
    env = os.environ.get(env_var)
    if env:
        return env
    suffix = ".exe" if os.name == "nt" else ""
    local = TOOLS_DIR / "ffmpeg" / "bin" / f"{name}{suffix}"
    if local.exists():
        return str(local)
    return name


FFMPEG = _binary("ffmpeg", "FFMPEG_BIN")
FFPROBE = _binary("ffprobe", "FFPROBE_BIN")

CPU_THREADS = int(os.environ.get("SUBS_THREADS", "8"))

# محدودیت‌ها
MAX_UPLOAD_BYTES = 12 * 1024**3  # ۱۲ گیگابایت
ALLOWED_EXT = {
    ".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v", ".ts", ".flv", ".wmv",
    ".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".wma",
}

JOBS_DIR.mkdir(parents=True, exist_ok=True)

"""راه‌اندازی اولیه: دریافت ffmpeg (ویندوز) و مدل ویسپر در صورت نبود.

اجرا:
    python -m app.setup
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

from . import config

FFMPEG_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
MODEL_NAME = os.environ.get("ATLANSUB_MODEL", "large-v3-turbo")
MODEL_SIZES = {
    "tiny": "75 MB",
    "base": "145 MB",
    "small": "480 MB",
    "medium": "1.5 GB",
    "large-v3": "3.1 GB",
    "large-v3-turbo": "1.6 GB",
}


def log(msg: str = "") -> None:
    print(msg, flush=True)


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "Atlansub-setup"})
    with urllib.request.urlopen(req, timeout=60) as resp, open(dest, "wb") as fh:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        step = -1
        while True:
            chunk = resp.read(1024 * 1024)
            if not chunk:
                break
            fh.write(chunk)
            done += len(chunk)
            if total:
                pct = done * 100 // total
                if pct >= step + 5:
                    step = pct
                    log(f"  {pct:3d}%   {done / 1048576:6.0f} / {total / 1048576:.0f} MB")
    log("")


def _has(binary: str) -> bool:
    return bool(shutil.which(binary)) or Path(binary).exists()


def _resolve(binary: str) -> str:
    """مسیر واقعی فایل اجرایی برای نمایش."""
    if Path(binary).is_file():
        return str(Path(binary).resolve())
    return shutil.which(binary) or binary


def ensure_ffmpeg(force: bool = False) -> None:
    if not force and _has(config.FFMPEG) and _has(config.FFPROBE):
        log(f"ffmpeg : OK  ({_resolve(config.FFMPEG)})")
        return

    if os.name != "nt":
        log("ffmpeg/ffprobe not found. Install them and run again:")
        log("  Debian/Ubuntu : sudo apt install ffmpeg")
        log("  Fedora        : sudo dnf install ffmpeg")
        log("  macOS         : brew install ffmpeg")
        raise SystemExit(1)

    bin_dir = config.TOOLS_DIR / "ffmpeg" / "bin"
    ffmpeg_exe = bin_dir / "ffmpeg.exe"
    if force or not ffmpeg_exe.exists():
        archive = config.TOOLS_DIR / "ffmpeg-download.zip"
        log("ffmpeg not found - downloading a static build (~110 MB) ...")
        _download(FFMPEG_URL, archive)

        log("Extracting ...")
        extract_dir = config.TOOLS_DIR / "ffmpeg-extract"
        shutil.rmtree(extract_dir, ignore_errors=True)
        extract_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(extract_dir)

        found = next(extract_dir.rglob("ffmpeg.exe"), None)
        if found is None:
            shutil.rmtree(extract_dir, ignore_errors=True)
            raise SystemExit("ffmpeg.exe was not found inside the downloaded archive.")

        bin_dir.mkdir(parents=True, exist_ok=True)
        for exe in found.parent.glob("*.exe"):
            shutil.copy2(exe, bin_dir / exe.name)
        shutil.rmtree(extract_dir, ignore_errors=True)
        archive.unlink(missing_ok=True)

    try:
        out = subprocess.run(
            [str(ffmpeg_exe), "-version"],
            capture_output=True, text=True, timeout=30,
            creationflags=0x08000000 if os.name == "nt" else 0,
        )
    except OSError as exc:
        raise SystemExit(f"Could not run ffmpeg: {exc}") from exc
    if out.returncode != 0:
        raise SystemExit("ffmpeg was installed but does not run correctly.")
    log(f"ffmpeg : OK  ({ffmpeg_exe})")


def ensure_model() -> None:
    model_dir = Path(config.MODEL_PATH)
    if (model_dir / "model.bin").exists():
        log(f"model  : OK  ({model_dir})")
        return

    if os.environ.get("WHISPER_MODEL"):
        log(f"WHISPER_MODEL points to '{config.MODEL_PATH}' but no model.bin exists there.")
        log("Fix the path, or unset WHISPER_MODEL so the setup can download the model.")
        raise SystemExit(1)

    target = config.MODELS_DIR / MODEL_NAME
    size = MODEL_SIZES.get(MODEL_NAME)
    size_note = f" (~{size})" if size else ""
    log(f"Downloading the '{MODEL_NAME}' speech model{size_note} from Hugging Face.")
    log("This is a one-time download and may take a few minutes.")
    try:
        from faster_whisper.utils import download_model
    except ImportError as exc:  # pragma: no cover
        raise SystemExit(
            "faster-whisper is not installed. Run: pip install -r requirements.txt"
        ) from exc

    download_model(MODEL_NAME, output_dir=str(target))
    if not (target / "model.bin").exists():
        raise SystemExit("The download finished but model.bin was not found.")
    log(f"model  : OK  ({target})")


def main() -> None:
    parser = argparse.ArgumentParser(description="Atlansub first-run setup")
    parser.add_argument("--force-ffmpeg", action="store_true",
                        help="download the bundled ffmpeg again")
    parser.add_argument("--skip-model", action="store_true",
                        help="do not download the speech model")
    args = parser.parse_args()

    log("=" * 62)
    log("  Atlansub setup")
    log("=" * 62)
    ensure_ffmpeg(force=args.force_ffmpeg)
    if not args.skip_model:
        ensure_model()
    log("")
    log("Setup complete.")


if __name__ == "__main__":
    sys.exit(main())

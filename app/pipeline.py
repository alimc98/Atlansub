"""هسته‌ی پردازش: رونویسی، ساخت خروجی‌ها و رندر لایه‌ی شفاف."""
from __future__ import annotations

import json
import os
import queue
import re
import shutil
import subprocess
import threading
import time
import traceback
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import config
from .ass_gen import build_ass
from .srt_utils import (
    Cue,
    build_cues,
    format_srt,
    make_premiere_srt,
    normalize_fa,
    parse_srt,
)

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


# ---------------------------------------------------------------- probe

def probe_media(path: Path) -> dict[str, Any]:
    cmd = [
        config.FFPROBE, "-v", "error", "-print_format", "json",
        "-show_format", "-show_streams", str(path),
    ]
    raw = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                         errors="replace", creationflags=CREATE_NO_WINDOW)
    if raw.returncode != 0:
        raise RuntimeError(f"خواندن مشخصات فایل ممکن نشد: {raw.stderr.strip()[:300]}")
    data = json.loads(raw.stdout or "{}")
    streams = data.get("streams", [])
    vstream = next((s for s in streams if s.get("codec_type") == "video"), None)
    astream = next((s for s in streams if s.get("codec_type") == "audio"), None)

    duration = 0.0
    try:
        duration = float(data.get("format", {}).get("duration") or 0)
    except (TypeError, ValueError):
        duration = 0.0
    if duration <= 0 and vstream:
        try:
            duration = float(vstream.get("duration") or 0)
        except (TypeError, ValueError):
            pass

    width = int(vstream.get("width") or 0) if vstream else 0
    height = int(vstream.get("height") or 0) if vstream else 0
    rotation = 0.0
    if vstream:
        for sd in vstream.get("side_data_list", []) or []:
            if "rotation" in sd:
                try:
                    rotation = float(sd["rotation"])
                except (TypeError, ValueError):
                    rotation = 0.0
        if rotation == 0 and vstream.get("tags", {}).get("rotate"):
            try:
                rotation = float(vstream["tags"]["rotate"])
            except (TypeError, ValueError):
                rotation = 0.0
    if abs(rotation) % 180 == 90:
        width, height = height, width

    fps_str = "30/1"
    if vstream:
        fps_str = vstream.get("avg_frame_rate") or vstream.get("r_frame_rate") or "30/1"
        if fps_str in ("0/0", "0/1"):
            fps_str = vstream.get("r_frame_rate") or "30/1"
    try:
        num, den = fps_str.split("/")
        fps = float(num) / float(den) if float(den) else 30.0
    except (ValueError, ZeroDivisionError):
        fps, fps_str = 30.0, "30/1"
    if fps <= 0 or fps > 240:
        fps, fps_str = 30.0, "30/1"

    return {
        "duration": duration,
        "width": width,
        "height": height,
        "fps": fps,
        "fps_str": fps_str,
        "has_audio": astream is not None,
        "has_video": vstream is not None,
        "format_name": data.get("format", {}).get("format_name", ""),
    }


def short_side_dims(width: int, height: int, target_short: int) -> tuple[int, int]:
    short = min(width, height)
    if short <= 0:
        return width, height
    scale = target_short / short
    w = max(2, int(round(width * scale / 2)) * 2)
    h = max(2, int(round(height * scale / 2)) * 2)
    return w, h


# ---------------------------------------------------------------- model

_model = None
_model_lock = threading.Lock()


def get_model():
    global _model
    with _model_lock:
        if _model is None:
            from faster_whisper import WhisperModel

            _model = WhisperModel(
                config.MODEL_PATH,
                device="cpu",
                compute_type="int8",
                cpu_threads=config.CPU_THREADS,
                num_workers=1,
            )
    return _model


# ---------------------------------------------------------------- job

def _sanitize_stem(name: str) -> str:
    stem = Path(name).stem
    stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", stem).strip(" .")
    return stem[:80] or "video"


class Canceled(Exception):
    pass


@dataclass
class Job:
    id: str
    title: str
    directory: Path
    source: Path
    stem: str
    options: dict = field(default_factory=dict)

    state: str = "queued"
    stage: str = "در صف"
    progress: float = 0.0
    error: str = ""
    created: float = field(default_factory=time.time)
    started: float | None = None
    finished: float | None = None
    meta: dict = field(default_factory=dict)
    files: dict[str, dict] = field(default_factory=dict)
    logs: list[str] = field(default_factory=list)
    cancel: bool = False
    proc: subprocess.Popen | None = None

    def __post_init__(self) -> None:
        self._lock = threading.Lock()

    # -- helpers
    def log(self, msg: str) -> None:
        line = f"{time.strftime('%H:%M:%S')}  {msg}"
        with self._lock:
            self.logs.append(line)
            if len(self.logs) > 300:
                self.logs = self.logs[-300:]

    def update(self, **kw) -> None:
        with self._lock:
            for k, v in kw.items():
                setattr(self, k, v)

    def set_progress(self, value: float, stage: str | None = None) -> None:
        with self._lock:
            self.progress = min(1.0, max(0.0, float(value)))
            if stage:
                self.stage = stage

    def add_file(self, key: str, path: Path, label: str) -> None:
        self.files[key] = {
            "key": key,
            "name": path.name,
            "label": label,
            "size": path.stat().st_size if path.exists() else 0,
        }

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "state": self.state,
            "stage": self.stage,
            "progress": round(self.progress, 4),
            "error": self.error,
            "meta": self.meta,
            "files": list(self.files.values()),
            "logs": self.logs[-60:],
            "created": self.created,
            "started": self.started,
            "finished": self.finished,
        }


# ---------------------------------------------------------------- manager

class JobManager:
    def __init__(self) -> None:
        self.jobs: dict[str, Job] = {}
        self._queue: queue.Queue = queue.Queue()
        self._thread = threading.Thread(target=self._worker, daemon=True, name="subs-worker")
        self._thread.start()

    def create(self, upload_name: str, source: Path, options: dict) -> Job:
        job_id = uuid.uuid4().hex[:12]
        stem = _sanitize_stem(upload_name)
        job_dir = config.JOBS_DIR / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        job = Job(id=job_id, title=Path(upload_name).name, directory=job_dir,
                  source=source, stem=stem, options=options)
        self.jobs[job_id] = job
        return job

    def enqueue(self, job: Job, action: str = "transcribe") -> None:
        job.update(state="queued", stage="در صف پردازش", error="")
        job.cancel = False
        self._queue.put((job, action))

    def _worker(self) -> None:
        while True:
            job, action = self._queue.get()
            try:
                if job.cancel:
                    job.update(state="canceled", stage="لغو شد")
                    continue
                if action == "transcribe":
                    run_job(job)
                elif action == "rerender":
                    rerender_overlay(job)
            except Canceled:
                job.update(state="canceled", stage="لغو شد")
            except Exception as exc:  # noqa: BLE001
                job.update(state="error", stage="خطا", error=str(exc))
                job.log("خطا: " + str(exc))
                job.log(traceback.format_exc(limit=6))
            finally:
                job.proc = None
                job.finished = time.time()
                self._queue.task_done()


manager = JobManager()


# ---------------------------------------------------------------- pipeline

def _write_outputs(job: Job, cues: list[Cue]) -> None:
    srt_path = job.directory / f"{job.stem}.fa.srt"
    txt_path = job.directory / f"{job.stem}.fa.txt"
    prem_path = job.directory / f"{job.stem}.fa.premiere.srt"

    srt_path.write_text(format_srt(cues), encoding="utf-8")
    txt_path.write_text("\n".join(c.text for c in cues) + "\n", encoding="utf-8")
    job.add_file("srt", srt_path, "زیرنویس SRT")

    if job.options.get("premiere", True):
        prem_path.write_text(make_premiere_srt(cues), encoding="utf-8")
        job.add_file("premiere", prem_path, "SRT آماده‌ی پریمیر")
    else:
        job.files.pop("premiere", None)


def _load_audio(job: Job):
    """صدا را با ffmpeg به WAV 16k مونو تبدیل و در حافظه می‌خواند.

    این کار وابستگی به PyAV را حذف می‌کند و روی همه‌ی فرمت‌ها پایدار است.
    """
    import wave

    import numpy as np

    wav_path = job.directory / "audio16k.wav"
    job.update(stage="استخراج صدا")
    job.log("استخراج صدا با ffmpeg")
    cmd = [
        config.FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(job.source), "-vn", "-ac", "1", "-ar", "16000",
        "-c:a", "pcm_s16le", str(wav_path),
    ]
    res = subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
        creationflags=CREATE_NO_WINDOW,
    )
    if res.returncode != 0 or not wav_path.exists():
        raise RuntimeError("استخراج صدا ناموفق بود: " + (res.stderr or "").strip()[:300])

    with wave.open(str(wav_path), "rb") as wf:
        frames = wf.readframes(wf.getnframes())
    audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    try:
        wav_path.unlink()
    except OSError:
        pass
    return audio, len(audio) / 16000.0


def _transcribe(job: Job) -> list[Cue]:
    meta = job.meta
    if not meta.get("has_audio"):
        raise RuntimeError("این فایل صدا ندارد؛ چیزی برای رونویسی پیدا نشد.")

    audio, audio_duration = _load_audio(job)

    job.update(stage="بارگذاری مدل")
    job.log("بارگذاری مدل " + config.MODEL_LABEL)
    model = get_model()

    fast = job.options.get("quality") == "fast"
    language = job.options.get("language") or "fa"
    job.update(stage="رونویسی گفتار")
    job.log(f"شروع رونویسی (زبان: {language})")

    segments, info = model.transcribe(
        audio,
        language=None if language == "auto" else language,
        task="transcribe",
        beam_size=1 if fast else 5,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 500},
        word_timestamps=True,
        condition_on_previous_text=False,
    )

    total = float(getattr(info, "duration", 0) or audio_duration or 0) or 1.0

    def tracked():
        for seg in segments:
            if job.cancel:
                raise Canceled()
            frac = min(1.0, float(seg.end) / total)
            job.set_progress(0.05 + 0.72 * frac,
                             f"رونویسی گفتار — {int(frac * 100)}٪")
            yield seg

    cues = build_cues(tracked())
    if not cues:
        raise RuntimeError("گفتاری تشخیص داده نشد. شاید فایل بدون صدا یا زبان آن فارسی نیست.")
    job.log(f"{len(cues)} کیو ساخته شد")
    return cues


def run_job(job: Job) -> None:
    job.update(state="running", started=time.time(), stage="بررسی فایل")
    job.set_progress(0.01)
    job.log("شروع پردازش " + job.title)

    meta = probe_media(job.source)
    job.meta.update({
        "duration": round(meta["duration"], 2),
        "width": meta["width"],
        "height": meta["height"],
        "fps": round(meta["fps"], 3),
        "has_audio": meta["has_audio"],
        "has_video": meta["has_video"],
    })
    job.set_progress(0.03, "آماده‌سازی")

    cues = _transcribe(job)

    job.set_progress(0.8, "ساخت فایل‌های زیرنویس")
    _write_outputs(job, cues)

    if job.options.get("overlay") and meta.get("has_video"):
        job.set_progress(0.85, "رندر لایه‌ی شفاف")
        _render_overlay(job, cues, base_progress=0.85, span=0.14)

    job.set_progress(1.0, "پایان")
    job.update(state="done")
    job.log("تمام شد")


def rerender_overlay(job: Job) -> None:
    job.update(state="running", stage="رندر لایه‌ی شفاف", error="")
    srt_path = job.directory / f"{job.stem}.fa.srt"
    if not srt_path.exists():
        raise RuntimeError("فایل زیرنویس پیدا نشد.")
    cues = parse_srt(srt_path.read_text(encoding="utf-8"))
    if not cues:
        raise RuntimeError("فایل زیرنویس خالی است.")
    _render_overlay(job, cues, base_progress=0.0, span=0.99)
    job.set_progress(1.0, "پایان")
    job.update(state="done")
    job.log("لایه‌ی شفاف بازسازی شد")


def _render_overlay(job: Job, cues: list[Cue], base_progress: float, span: float) -> None:
    meta = job.meta
    if not meta.get("width") or not meta.get("height"):
        raise RuntimeError("ابعاد ویدیو مشخص نیست؛ رندر لایه ممکن نیست.")

    width, height = int(meta["width"]), int(meta["height"])
    scale_opt = job.options.get("overlay_scale", "native")
    if scale_opt in ("1080", "720"):
        width, height = short_side_dims(width, height, int(scale_opt))

    fps_str = meta.get("fps_str") or "30/1"
    duration = float(meta.get("duration") or 0)
    if duration <= 0:
        raise RuntimeError("مدت ویدیو مشخص نیست.")

    job_dir = job.directory
    ass_path = job_dir / "subs.ass"
    ass_path.write_text(build_ass(cues, width, height, config.FONT_NAME), encoding="utf-8")

    fonts_dir = job_dir / "fonts"
    fonts_dir.mkdir(exist_ok=True)
    if config.FONT_FILE.exists():
        shutil.copy2(config.FONT_FILE, fonts_dir / config.FONT_FILE.name)

    out_path = job_dir / f"{job.stem}.fa.overlay.mov"
    cmd = [
        config.FFMPEG, "-hide_banner", "-nostats", "-loglevel", "error",
        "-progress", "pipe:1", "-y",
        "-f", "lavfi", "-i",
        f"color=c=black@0.0:s={width}x{height}:r={fps_str}:d={duration:.3f},format=rgba",
        "-vf", "subtitles=subs.ass:fontsdir=fonts:alpha=1",
        "-c:v", "prores_ks", "-profile:v", "4", "-pix_fmt", "yuva444p10le",
        "-alpha_bits", "16", "-threads", str(config.CPU_THREADS),
        str(out_path),
    ]

    job.log(f"رندر لایه {width}×{height} با ProRes 4444")
    err_path = job_dir / "ffmpeg.log"
    with open(err_path, "w", encoding="utf-8") as err_file:
        proc = subprocess.Popen(
            cmd, cwd=str(job_dir), stdout=subprocess.PIPE, stderr=err_file,
            text=True, encoding="utf-8", errors="replace",
            creationflags=CREATE_NO_WINDOW,
        )
        job.proc = proc
        assert proc.stdout is not None
        for line in proc.stdout:
            if job.cancel:
                proc.kill()
                raise Canceled()
            line = line.strip()
            if line.startswith(("out_time_ms=", "out_time_us=")):
                try:
                    sec = float(line.split("=", 1)[1]) / 1_000_000.0
                except ValueError:
                    continue
                frac = min(1.0, sec / duration)
                job.set_progress(base_progress + span * frac,
                                 f"رندر لایه‌ی شفاف — {int(frac * 100)}٪")
        code = proc.wait()

    if code != 0:
        tail = ""
        try:
            tail = err_path.read_text(encoding="utf-8", errors="replace")[-600:]
        except OSError:
            pass
        raise RuntimeError("رندر لایه‌ی شفاف شکست خورد.\n" + tail.strip())

    job.add_file("overlay", out_path, "لایه‌ی شفاف (ProRes 4444)")
    job.meta["overlay_dims"] = f"{width}×{height}"
    job.meta["overlay_mb"] = round(out_path.stat().st_size / 1024 / 1024, 1)

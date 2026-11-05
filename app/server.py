"""سرور محلی برنامه‌ی زیرنویس‌ساز."""
from __future__ import annotations

import json
import os
import shutil
import socket
import threading
import uuid
import webbrowser
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import config
from .pipeline import Job, manager, probe_media, _sanitize_stem
from .srt_utils import Cue, format_srt, make_premiere_srt, parse_srt

app = FastAPI(title="Atlansub", docs_url=None, redoc_url=None)


# ---------------------------------------------------------------- static

app.mount("/static", StaticFiles(directory=str(config.STATIC_DIR)), name="static")


@app.get("/", response_class=HTMLResponse)
async def index() -> FileResponse:
    return FileResponse(config.STATIC_DIR / "index.html")


@app.get("/api/info")
async def info() -> dict:
    return {
        "model": config.MODEL_LABEL,
        "model_path": config.MODEL_PATH,
        "model_exists": Path(config.MODEL_PATH).exists(),
        "threads": config.CPU_THREADS,
        "max_upload_gb": round(config.MAX_UPLOAD_BYTES / 1024**3, 1),
    }


# ---------------------------------------------------------------- jobs

def _bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in ("1", "true", "on", "yes")


@app.post("/api/jobs")
async def create_job(
    file: UploadFile = File(...),
    overlay: str = Form("false"),
    premiere: str = Form("true"),
    quality: str = Form("accurate"),
    overlay_scale: str = Form("native"),
    language: str = Form("fa"),
) -> JSONResponse:
    filename = file.filename or "video.mp4"
    ext = Path(filename).suffix.lower()
    if ext not in config.ALLOWED_EXT:
        raise HTTPException(400, f"فرمت «{ext or 'نامشخص'}» پشتیبانی نمی‌شود.")

    job_id = uuid.uuid4().hex[:12]
    job_dir = config.JOBS_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    dest = job_dir / ("input" + ext)

    size = 0
    try:
        with open(dest, "wb") as out:
            while True:
                chunk = await file.read(4 * 1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > config.MAX_UPLOAD_BYTES:
                    raise HTTPException(413, "حجم فایل بیش از حد مجاز است.")
                out.write(chunk)
    except HTTPException:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise
    except Exception as exc:  # noqa: BLE001
        shutil.rmtree(job_dir, ignore_errors=True)
        raise HTTPException(500, f"ذخیره‌ی فایل ناموفق بود: {exc}") from exc
    finally:
        await file.close()

    if size == 0:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise HTTPException(400, "فایل خالی است.")

    options = {
        "overlay": _bool(overlay),
        "premiere": _bool(premiere, True),
        "quality": "fast" if quality == "fast" else "accurate",
        "overlay_scale": overlay_scale if overlay_scale in ("native", "1080", "720") else "native",
        "language": language if language in ("fa", "auto") else "fa",
    }

    job = Job(
        id=job_id,
        title=filename,
        directory=job_dir,
        source=dest,
        stem=_sanitize_stem(filename),
        options=options,
    )
    job.meta["upload_mb"] = round(size / 1024 / 1024, 1)
    manager.jobs[job_id] = job
    manager.enqueue(job)
    return JSONResponse({"id": job_id})


def _get_job(job_id: str) -> Job:
    job = manager.jobs.get(job_id)
    if job is None:
        raise HTTPException(404, "کار پیدا نشد.")
    return job


@app.get("/api/jobs/{job_id}")
async def job_status(job_id: str) -> dict:
    return _get_job(job_id).to_dict()


@app.get("/api/jobs/{job_id}/cues")
async def job_cues(job_id: str) -> JSONResponse:
    job = _get_job(job_id)
    path = job.directory / f"{job.stem}.fa.srt"
    if not path.exists():
        raise HTTPException(404, "فایل زیرنویس هنوز ساخته نشده است.")
    cues = parse_srt(path.read_text(encoding="utf-8"))
    return JSONResponse({"cues": [{"start": c.start, "end": c.end, "text": c.text} for c in cues]})


@app.post("/api/jobs/{job_id}/cues")
async def update_cues(job_id: str, payload: dict) -> dict:
    job = _get_job(job_id)
    raw = payload.get("cues") or []
    cues = []
    for item in raw:
        try:
            start = float(item.get("start", 0))
            end = float(item.get("end", 0))
        except (TypeError, ValueError):
            continue
        text = str(item.get("text", "")).strip()
        if not text or end <= start:
            continue
        cues.append(Cue(start, end, text))
    cues.sort(key=lambda c: c.start)
    if not cues:
        raise HTTPException(400, "هیچ کیوی معتبری باقی نمانده است.")

    srt_path = job.directory / f"{job.stem}.fa.srt"
    srt_path.write_text(format_srt(cues), encoding="utf-8")
    job.add_file("srt", srt_path, "زیرنویس SRT")

    if job.options.get("premiere", True):
        prem_path = job.directory / f"{job.stem}.fa.premiere.srt"
        prem_path.write_text(make_premiere_srt(cues), encoding="utf-8")
        job.add_file("premiere", prem_path, "SRT آماده‌ی پریمیر")

    if payload.get("rerender_overlay") and job.options.get("overlay"):
        manager.enqueue(job, "rerender")

    job.log(f"زیرنویس ویرایش شد ({len(cues)} کیو)")
    return job.to_dict()


@app.post("/api/jobs/{job_id}/overlay")
async def rebuild_overlay(job_id: str) -> dict:
    job = _get_job(job_id)
    if job.state in ("running", "queued"):
        raise HTTPException(409, "یک پردازش در حال اجراست.")
    if not job.meta.get("duration"):
        try:
            meta = probe_media(job.source)
            job.meta.update({
                "duration": round(meta["duration"], 2),
                "width": meta["width"],
                "height": meta["height"],
                "fps": round(meta["fps"], 3),
                "fps_str": meta["fps_str"],
                "has_video": meta["has_video"],
            })
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(500, str(exc)) from exc
    job.options["overlay"] = True
    manager.enqueue(job, "rerender")
    return job.to_dict()


@app.post("/api/jobs/{job_id}/cancel")
async def cancel_job(job_id: str) -> dict:
    job = _get_job(job_id)
    job.cancel = True
    if job.proc is not None:
        try:
            job.proc.kill()
        except Exception:  # noqa: BLE001
            pass
    job.log("درخواست لغو")
    return job.to_dict()


@app.delete("/api/jobs/{job_id}")
async def delete_job(job_id: str) -> dict:
    job = _get_job(job_id)
    if job.state in ("running", "queued"):
        raise HTTPException(409, "پردازش در حال اجراست.")
    shutil.rmtree(job.directory, ignore_errors=True)
    manager.jobs.pop(job_id, None)
    return {"ok": True}


@app.get("/api/jobs/{job_id}/download/{key}")
async def download(job_id: str, key: str) -> FileResponse:
    job = _get_job(job_id)
    entry = job.files.get(key)
    if not entry:
        raise HTTPException(404, "فایل موجود نیست.")
    path = job.directory / entry["name"]
    if not path.exists():
        raise HTTPException(404, "فایل حذف شده است.")
    return FileResponse(path, filename=entry["name"])


# ---------------------------------------------------------------- main

def _free_port(start: int) -> int:
    for port in range(start, start + 40):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((config.HOST, port))
                return port
            except OSError:
                continue
    return start


def main() -> None:
    import sys

    import uvicorn

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass

    port = _free_port(config.BASE_PORT)
    url = f"http://{config.HOST}:{port}"
    print("=" * 60)
    print("  Atlansub - Persian subtitle generator")
    print(f"  {url}")
    print("  Close this window to stop the server.")
    print("=" * 60)

    if os.environ.get("SUBS_NO_BROWSER") != "1":
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    uvicorn.run(app, host=config.HOST, port=port, log_level="warning")


if __name__ == "__main__":
    main()

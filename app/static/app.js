"use strict";

const $ = (id) => document.getElementById(id);

const els = {
  dropzone: $("dropzone"),
  fileInput: $("fileInput"),
  fileRow: $("fileRow"),
  fileThumb: $("fileThumb"),
  fileName: $("fileName"),
  fileSub: $("fileSub"),
  clearFile: $("clearFile"),
  qualitySeg: $("qualitySeg"),
  language: $("language"),
  optPremiere: $("optPremiere"),
  optOverlay: $("optOverlay"),
  overlayScaleRow: $("overlayScaleRow"),
  overlayScale: $("overlayScale"),
  startBtn: $("startBtn"),
  progressCard: $("progressCard"),
  stageText: $("stageText"),
  pctText: $("pctText"),
  barFill: $("barFill"),
  elapsed: $("elapsed"),
  cancelBtn: $("cancelBtn"),
  errorBox: $("errorBox"),
  logBox: $("logBox"),
  logText: $("logText"),
  resultCard: $("resultCard"),
  resultSub: $("resultSub"),
  files: $("files"),
  newJobBtn: $("newJobBtn"),
  deleteJobBtn: $("deleteJobBtn"),
  editorCard: $("editorCard"),
  cueList: $("cueList"),
  cueCount: $("cueCount"),
  saveSrtBtn: $("saveSrtBtn"),
  rebuildOverlayBtn: $("rebuildOverlayBtn"),
  modelInfo: $("modelInfo"),
  toast: $("toast"),
};

const state = {
  file: null,
  meta: {},
  jobId: null,
  timer: null,
  cues: [],
  busy: false,
  startedAt: 0,
  maxProgress: 0,
};

const faNum = (n, digits = 0) =>
  new Intl.NumberFormat("fa-IR", { maximumFractionDigits: digits }).format(n);

const fmtBytes = (b) => {
  if (!b) return "—";
  if (b < 1024 * 1024) return faNum(b / 1024, 0) + " کیلوبایت";
  if (b > 1024 ** 3) return faNum(b / 1024 ** 3, 2) + " گیگابایت";
  return faNum(b / 1024 ** 2, 1) + " مگابایت";
};

const fmtDuration = (s) => {
  if (!s || !isFinite(s)) return "";
  const m = Math.floor(s / 60);
  const sec = Math.round(s % 60);
  if (m <= 0) return `${faNum(sec)} ثانیه`;
  return `${faNum(m)} دقیقه و ${faNum(sec)} ثانیه`;
};

const fmtClock = (s) => {
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${String(sec).padStart(2, "0")}`;
};

let toastTimer = null;
function toast(msg, isError = false) {
  els.toast.textContent = msg;
  els.toast.classList.toggle("err", isError);
  els.toast.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => els.toast.classList.remove("show"), 3200);
}

/* ---------------------------------------------------------------- info */

fetch("/api/info")
  .then((r) => r.json())
  .then((info) => {
    els.modelInfo.textContent = `مدل: ${info.model} · CPU · ${info.threads} رشته`;
    if (!info.model_exists) {
      toast("مدل ویسپر پیدا نشد: " + info.model_path, true);
    }
  })
  .catch(() => {});

/* ---------------------------------------------------------------- file */

function setFile(file) {
  if (!file) return;
  const okExt = /\.(mp4|mov|mkv|avi|webm|m4v|ts|flv|wmv|mp3|wav|m4a|aac|flac|ogg|opus|wma)$/i;
  if (!okExt.test(file.name)) {
    toast("این فرمت پشتیبانی نمی‌شود.", true);
    return;
  }
  state.file = file;
  state.meta = {};
  els.fileRow.hidden = false;
  els.dropzone.style.display = "none";
  els.fileName.textContent = file.name;
  els.fileSub.textContent = fmtBytes(file.size);
  els.startBtn.disabled = false;

  if (file.type.startsWith("video/")) {
    const v = document.createElement("video");
    v.preload = "metadata";
    const url = URL.createObjectURL(file);
    v.onloadedmetadata = () => {
      state.meta = { duration: v.duration, width: v.videoWidth, height: v.videoHeight };
      const bits = [fmtBytes(file.size)];
      if (v.duration) bits.push(fmtDuration(v.duration));
      if (v.videoWidth) {
        const short = Math.min(v.videoWidth, v.videoHeight);
        const quality = short >= 2000 ? "۴K" : short >= 1000 ? "Full HD" : "HD";
        const orient = v.videoHeight > v.videoWidth ? "عمودی" : "افقی";
        bits.push(`${quality} ${orient}`);
      }
      els.fileSub.textContent = bits.join(" · ");
      URL.revokeObjectURL(url);
    };
    v.onerror = () => URL.revokeObjectURL(url);
    v.src = url;
  }
}

els.dropzone.addEventListener("click", () => els.fileInput.click());
els.dropzone.addEventListener("keydown", (e) => {
  if (e.key === "Enter" || e.key === " ") {
    e.preventDefault();
    els.fileInput.click();
  }
});
els.fileInput.addEventListener("change", () => setFile(els.fileInput.files[0]));

["dragenter", "dragover"].forEach((ev) =>
  els.dropzone.addEventListener(ev, (e) => {
    e.preventDefault();
    els.dropzone.classList.add("drag");
  })
);
["dragleave", "drop"].forEach((ev) =>
  els.dropzone.addEventListener(ev, (e) => {
    e.preventDefault();
    els.dropzone.classList.remove("drag");
  })
);
els.dropzone.addEventListener("drop", (e) => {
  const file = e.dataTransfer.files && e.dataTransfer.files[0];
  if (file) setFile(file);
});
window.addEventListener("dragover", (e) => e.preventDefault());
window.addEventListener("drop", (e) => e.preventDefault());

els.clearFile.addEventListener("click", () => resetFile());

function resetFile() {
  state.file = null;
  state.meta = {};
  els.fileInput.value = "";
  els.fileRow.hidden = true;
  els.dropzone.style.display = "";
  els.startBtn.disabled = true;
}

/* ---------------------------------------------------------------- options */

els.qualitySeg.addEventListener("click", (e) => {
  const btn = e.target.closest("button");
  if (!btn) return;
  [...els.qualitySeg.children].forEach((b) => b.classList.toggle("active", b === btn));
});

els.optOverlay.addEventListener("change", () => {
  els.overlayScaleRow.hidden = !els.optOverlay.checked;
});

/* ---------------------------------------------------------------- progress */

function setProgress(frac, stage) {
  const pct = Math.max(0, Math.min(1, frac));
  state.maxProgress = Math.max(state.maxProgress, pct);
  els.barFill.style.width = (pct * 100).toFixed(1) + "%";
  els.pctText.textContent = faNum(Math.round(pct * 100)) + "٪";
  if (stage) els.stageText.textContent = stage;
}

function tickElapsed() {
  if (!state.startedAt) return;
  const sec = (Date.now() - state.startedAt) / 1000;
  els.elapsed.textContent = "زمان: " + fmtDuration(sec);
}

/* ---------------------------------------------------------------- start */

els.startBtn.addEventListener("click", () => {
  if (!state.file || state.busy) return;
  startJob();
});

function startJob() {
  state.busy = true;
  state.maxProgress = 0;
  state.startedAt = Date.now();
  els.startBtn.disabled = true;
  els.startBtn.querySelector("span").textContent = "در حال ارسال…";
  els.progressCard.hidden = false;
  els.cancelBtn.hidden = false;
  els.resultCard.hidden = true;
  els.editorCard.hidden = true;
  els.errorBox.hidden = true;
  els.logBox.open = false;
  els.logText.textContent = "";
  setProgress(0, "در حال ارسال فایل…");
  els.elapsed.textContent = "زمان: ۰ ثانیه";

  const fd = new FormData();
  fd.append("file", state.file);
  fd.append("overlay", els.optOverlay.checked ? "true" : "false");
  fd.append("premiere", els.optPremiere.checked ? "true" : "false");
  fd.append(
    "quality",
    els.qualitySeg.querySelector(".active")?.dataset.value || "accurate"
  );
  fd.append("overlay_scale", els.overlayScale.value);
  fd.append("language", els.language.value);

  const xhr = new XMLHttpRequest();
  xhr.open("POST", "/api/jobs");
  xhr.upload.onprogress = (e) => {
    if (!e.lengthComputable) return;
    const frac = (e.loaded / e.total) * 0.99;
    setProgress(frac, `در حال ارسال فایل — ${faNum(Math.round((e.loaded / e.total) * 100))}٪`);
  };
  xhr.onerror = () => fail("ارتباط با سرور برقرار نشد.");
  xhr.onload = () => {
    if (xhr.status !== 200) {
      let msg = "ارسال فایل ناموفق بود.";
      try {
        const data = JSON.parse(xhr.responseText);
        if (data.detail) msg = data.detail;
      } catch (_) {}
      fail(msg);
      return;
    }
    const data = JSON.parse(xhr.responseText);
    state.jobId = data.id;
    try { localStorage.setItem("lastJob", data.id); } catch (_) {}
    els.startBtn.querySelector("span").textContent = "در حال پردازش…";
    pollLoop();
  };
  xhr.send(fd);

  state.timer = setInterval(tickElapsed, 1000);
}

function fail(message) {
  state.busy = false;
  clearInterval(state.timer);
  els.stageText.textContent = "خطا";
  els.errorBox.hidden = false;
  els.errorBox.textContent = message;
  els.startBtn.disabled = !state.file;
  els.startBtn.querySelector("span").textContent = "شروع ساخت زیرنویس";
  toast(message, true);
}

/* ---------------------------------------------------------------- polling */

function pollLoop() {
  clearTimeout(state.poll);
  const run = async () => {
    if (!state.jobId) return;
    try {
      const res = await fetch(`/api/jobs/${state.jobId}`);
      if (!res.ok) throw new Error("وضعیت دریافت نشد");
      const job = await res.json();
      applyJob(job);
      if (["done", "error", "canceled"].includes(job.state)) {
        clearInterval(state.timer);
        return;
      }
    } catch (err) {
      console.warn(err);
    }
    state.poll = setTimeout(run, 900);
  };
  run();
}

function applyJob(job) {
  if (job.error) {
    els.errorBox.hidden = false;
    els.errorBox.textContent = job.error;
  }
  if (job.logs && job.logs.length) {
    els.logText.textContent = job.logs.join("\n");
  }
  if (job.state === "running" || job.state === "queued") {
    if (job.progress >= state.maxProgress) setProgress(job.progress, job.stage);
    else els.stageText.textContent = job.stage;
  }

  if (job.state === "done") {
    setProgress(1, "پایان");
    state.busy = false;
    els.startBtn.querySelector("span").textContent = "ساخت دوباره";
    els.startBtn.disabled = false;
    els.progressCard.hidden = true;
    els.cancelBtn.hidden = true;
    renderResults(job);
    loadCues();
  } else if (job.state === "error") {
    state.busy = false;
    els.stageText.textContent = job.stage || "خطا";
    els.startBtn.querySelector("span").textContent = "تلاش دوباره";
    els.startBtn.disabled = false;
    toast("پردازش با خطا متوقف شد.", true);
  } else if (job.state === "canceled") {
    state.busy = false;
    els.stageText.textContent = "لغو شد";
    els.startBtn.querySelector("span").textContent = "شروع مجدد";
    els.startBtn.disabled = false;
    toast("پردازش لغو شد.");
  }
}

/* ---------------------------------------------------------------- results */

const ICONS = {
  srt: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/><path d="M8.5 13h7M8.5 16.5h4.5"/></svg>`,
  premiere: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="16" rx="3"/><path d="M7.5 9.5h4.2a2 2 0 0 1 0 4H7.5V9.5zm0 4V16"/><path d="M15 16v-4.5a1.5 1.5 0 0 1 3 0V16"/></svg>`,
  overlay: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><rect x="2.5" y="5" width="19" height="14" rx="3"/><path d="M7 15h10"/><path d="M7 9.5h6"/></svg>`,
  download: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M12 4v11m0 0l4-4m-4 4l-4-4"/><path d="M5 19h14"/></svg>`,
  video: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="2.5" y="6" width="13" height="12" rx="2.5"/><path d="M15.5 10.5l6-3v9l-6-3z"/></svg>`,
};

function renderResults(job) {
  els.resultCard.hidden = false;
  const total = job.files.reduce((s, f) => s + (f.size || 0), 0);
  const dur = job.meta && job.meta.duration ? " · " + fmtDuration(job.meta.duration) : "";
  els.resultSub.textContent = `${faNum(job.files.length)} فایل · ${fmtBytes(total)}${dur}`;

  els.files.innerHTML = job.files
    .map((f) => {
      const icon = ICONS[f.key] || ICONS.srt;
      const cls = f.key === "overlay" ? "tile-icon mov" : "tile-icon";
      return `
        <div class="file-tile">
          <div class="${cls}">${icon}</div>
          <div class="tile-body">
            <div class="tile-label">${f.label}</div>
            <div class="tile-name">${f.name}</div>
          </div>
          <div class="tile-actions">
            <span class="tile-size">${fmtBytes(f.size)}</span>
            <a class="dl" href="/api/jobs/${job.id}/download/${f.key}">${ICONS.download} دانلود</a>
          </div>
        </div>`;
    })
    .join("");

  const hasOverlay = job.files.some((f) => f.key === "overlay");
  els.rebuildOverlayBtn.hidden = !hasOverlay;
  els.editorCard.hidden = false;
}

/* ---------------------------------------------------------------- editor */

async function loadCues() {
  if (!state.jobId) return;
  try {
    const res = await fetch(`/api/jobs/${state.jobId}/cues`);
    if (!res.ok) return;
    const data = await res.json();
    state.cues = data.cues || [];
    els.cueCount.textContent = faNum(state.cues.length) + " کیو";
    els.cueList.innerHTML = state.cues
      .map(
        (c, i) => `
        <div class="cue-row">
          <span class="cue-time">${fmtClock(c.start)}</span>
          <input class="cue-input" data-i="${i}" value="${escapeAttr(c.text)}" />
        </div>`
      )
      .join("");
    els.editorCard.hidden = false;
  } catch (err) {
    console.warn(err);
  }
}

function escapeAttr(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/"/g, "&quot;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

els.saveSrtBtn.addEventListener("click", async () => {
  if (!state.jobId) return;
  const inputs = [...els.cueList.querySelectorAll(".cue-input")];
  const cues = inputs.map((inp) => {
    const base = state.cues[Number(inp.dataset.i)];
    return { start: base.start, end: base.end, text: inp.value.trim() };
  });
  els.saveSrtBtn.disabled = true;
  try {
    const res = await fetch(`/api/jobs/${state.jobId}/cues`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ cues }),
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.detail || "ذخیره ناموفق بود");
    }
    const job = await res.json();
    applyJob({ ...job, state: "done" });
    toast("زیرنویس ذخیره و بازسازی شد.");
  } catch (err) {
    toast(err.message, true);
  } finally {
    els.saveSrtBtn.disabled = false;
  }
});

els.rebuildOverlayBtn.addEventListener("click", async () => {
  if (!state.jobId) return;
  try {
    const res = await fetch(`/api/jobs/${state.jobId}/overlay`, { method: "POST" });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.detail || "شروع رندر ناموفق بود");
    }
    els.resultCard.hidden = true;
    els.progressCard.hidden = false;
    els.errorBox.hidden = true;
    state.busy = true;
    state.maxProgress = 0;
    state.startedAt = Date.now();
    clearInterval(state.timer);
    state.timer = setInterval(tickElapsed, 1000);
    setProgress(0, "در صف رندر…");
    pollLoop();
    toast("رندر لایه‌ی شفاف آغاز شد.");
  } catch (err) {
    toast(err.message, true);
  }
});

/* ---------------------------------------------------------------- actions */

els.cancelBtn.addEventListener("click", async () => {
  if (!state.jobId) return;
  els.cancelBtn.disabled = true;
  try {
    await fetch(`/api/jobs/${state.jobId}/cancel`, { method: "POST" });
  } finally {
    els.cancelBtn.disabled = false;
  }
});

els.deleteJobBtn.addEventListener("click", async () => {
  if (!state.jobId) return;
  if (!confirm("همه‌ی فایل‌های این پروژه پاک شود؟")) return;
  try {
    await fetch(`/api/jobs/${state.jobId}`, { method: "DELETE" });
    toast("فایل‌ها پاک شد.");
    newJob();
  } catch (_) {
    toast("پاک کردن ناموفق بود.", true);
  }
});

els.newJobBtn.addEventListener("click", newJob);

function newJob() {
  clearTimeout(state.poll);
  clearInterval(state.timer);
  try { localStorage.removeItem("lastJob"); } catch (_) {}
  state.jobId = null;
  state.cues = [];
  state.busy = false;
  state.maxProgress = 0;
  state.startedAt = 0;
  state.file = null;
  state.meta = {};
  els.fileInput.value = "";
  els.fileRow.hidden = true;
  els.dropzone.style.display = "";
  els.resultCard.hidden = true;
  els.editorCard.hidden = true;
  els.progressCard.hidden = true;
  els.errorBox.hidden = true;
  els.cueList.innerHTML = "";
  els.startBtn.disabled = true;
  els.startBtn.querySelector("span").textContent = "شروع ساخت زیرنویس";
  window.scrollTo({ top: 0, behavior: "smooth" });
}

/* ---------------------------------------------------------------- restore */

(async function restoreSession() {
  let id = null;
  try { id = localStorage.getItem("lastJob"); } catch (_) {}
  if (!id) return;
  try {
    const res = await fetch(`/api/jobs/${id}`);
    if (!res.ok) {
      localStorage.removeItem("lastJob");
      return;
    }
    const job = await res.json();
    state.jobId = id;
    state.startedAt = job.started ? job.started * 1000 : Date.now();

    els.fileRow.hidden = false;
    els.dropzone.style.display = "none";
    els.fileName.textContent = job.title;
    els.fileSub.textContent =
      job.state === "done" ? "پروژه‌ی قبلی" : "پروژه‌ی در حال انجام";

    if (["running", "queued"].includes(job.state)) {
      els.progressCard.hidden = false;
      els.cancelBtn.hidden = false;
      state.busy = true;
      state.timer = setInterval(tickElapsed, 1000);
      applyJob(job);
      pollLoop();
    } else {
      applyJob(job);
    }
  } catch (_) {
    /* ignore */
  }
})();

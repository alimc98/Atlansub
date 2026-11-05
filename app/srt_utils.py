"""ابزارهای ساخت و ویرایش SRT، نرمال‌سازی فارسی و آماده‌سازی برای پریمیر."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Iterator

# ---------------------------------------------------------------- نرمال‌سازی

_CHAR_MAP = str.maketrans({
    "ي": "ی",   # Arabic yeh
    "ك": "ک",   # Arabic kaf
    "ﻻ": "لا",
    "ٱ": "ا",
    "\u200f": "",  # RLM
    "\u200e": "",  # LRM
    "\ufeff": "",
})

_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")

_ZWNJ_FIXES = [
    (r"\bمی\s+", "می\u200c"),
    (r"\bنمی\s+", "نمی\u200c"),
    (r"ها\s+ی\b", "ها\u200cی"),
    (r"\bها\b(?!\u200c)", "ها"),
]


def normalize_fa(text: str, persian_digits: bool = True) -> str:
    """پاک‌سازی و یکدست‌سازی متن فارسی."""
    if not text:
        return ""
    s = text.translate(_CHAR_MAP)
    s = re.sub(r"\u200c{2,}", "\u200c", s)
    s = re.sub(r"[ \t\u00a0]+", " ", s)
    s = re.sub(r"\s+([،؛؟!:.…»])", r"\1", s)
    s = re.sub(r"([«])\s+", r"\1", s)
    s = re.sub(r"\s+([\u0600-\u06FF])", r" \1", s)
    s = re.sub(r"([،؛؟!:])(?=[^\s\d])", r"\1 ", s)
    s = s.strip(" ،")
    if persian_digits:
        s = s.translate(_DIGITS)
    return s.strip()


# ---------------------------------------------------------------- Cue

@dataclass
class Cue:
    start: float
    end: float
    text: str

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


_TIME_RE = re.compile(
    r"(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})\s*-->\s*(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})"
)


def _to_seconds(h: str, m: str, s: str, ms: str) -> float:
    frac = ms.ljust(3, "0")[:3]
    return int(h) * 3600 + int(m) * 60 + int(s) + int(frac) / 1000.0


def _fmt_time(t: float) -> str:
    t = max(0.0, t)
    h = int(t // 3600)
    m = int(t % 3600 // 60)
    s = int(t % 60)
    ms = int(round((t - int(t)) * 1000))
    if ms == 1000:
        s += 1
        ms = 0
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def parse_srt(text: str) -> list[Cue]:
    """پارس مقاوم SRT (با یا بدون شماره‌ی ترتیب)."""
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return []
    cues: list[Cue] = []
    for block in re.split(r"\n\s*\n", text):
        lines = [ln for ln in block.split("\n")]
        idx = next((i for i, ln in enumerate(lines) if "-->" in ln), None)
        if idx is None:
            continue
        m = _TIME_RE.search(lines[idx])
        if not m:
            continue
        start = _to_seconds(*m.group(1, 2, 3, 4))
        end = _to_seconds(*m.group(5, 6, 7, 8))
        body = " ".join(ln.strip() for ln in lines[idx + 1:] if ln.strip())
        body = re.sub(r"\s+", " ", body).strip()
        if body:
            cues.append(Cue(start, end, body))
    cues.sort(key=lambda c: c.start)
    return cues


def format_srt(cues: Iterable[Cue]) -> str:
    out: list[str] = []
    for i, c in enumerate(cues, 1):
        out.append(f"{i}\n{_fmt_time(c.start)} --> {_fmt_time(c.end)}\n{c.text}\n")
    return "\n".join(out)


# ---------------------------------------------------------------- ساخت از کلمات

SENT_END = "؟?!.…؛:"
MAX_CHARS = 42
MAX_DURATION = 6.0
PAUSE_SPLIT = 0.75


def _clean_join(words: list[str]) -> str:
    return normalize_fa("".join(words))


def build_cues(
    segments: Iterator,
    max_chars: int = MAX_CHARS,
    max_duration: float = MAX_DURATION,
    pause: float = PAUSE_SPLIT,
) -> list[Cue]:
    """تبدیل خروجی faster-whisper (با word_timestamps) به کیوهای خوانا."""
    cues: list[Cue] = []
    cur: list = []

    def flush() -> None:
        nonlocal cur
        if not cur:
            return
        text = _clean_join([w.word for w in cur])
        if text:
            cues.append(Cue(float(cur[0].start), float(cur[-1].end), text))
        cur = []

    for seg in segments:
        words = getattr(seg, "words", None)
        if not words:
            txt = normalize_fa((seg.text or "").strip())
            if txt:
                cues.append(Cue(float(seg.start), float(seg.end), txt))
            continue
        for w in words:
            if cur and (float(w.start) - float(cur[-1].end)) > pause:
                flush()
            cur.append(w)
            text = _clean_join([x.word for x in cur])
            too_long = len(text) >= max_chars
            too_slow = (float(w.end) - float(cur[0].start)) >= max_duration
            if text.endswith(tuple(SENT_END)) or too_long or too_slow:
                flush()
    flush()
    return _tidy(cues)


def _tidy(cues: list[Cue]) -> list[Cue]:
    if not cues:
        return cues
    # ادغام کیوهای فوق‌کوتاه با کیوی بعدی
    merged: list[Cue] = []
    for c in cues:
        c.text = c.text.strip()
        if not c.text:
            continue
        if merged and c.duration < 0.55 and (len(merged[-1].text) + len(c.text)) < 56:
            merged[-1].text = normalize_fa(merged[-1].text + " " + c.text)
            merged[-1].end = c.end
        else:
            merged.append(c)

    # حداقل مدت و جلوگیری از همپوشانی
    for i, c in enumerate(merged):
        if c.end - c.start < 0.85:
            c.end = c.start + 0.85
        if i + 1 < len(merged):
            limit = merged[i + 1].start - 0.04
            if c.end > limit:
                c.end = max(c.start + 0.35, limit)
    return merged


# ---------------------------------------------------------------- پریمیر

def _shape_line(line: str) -> str:
    if not re.search(r"[\u0600-\u06FF]", line):
        return line
    import arabic_reshaper
    from bidi.algorithm import get_display

    return get_display(arabic_reshaper.reshape(line))


def shape_text_visual(text: str) -> str:
    """متن را به فرم‌های نمایشی + ترتیب بصری تبدیل می‌کند (برای رندررهای بدون shaping)."""
    lines = text.replace("\r\n", "\n").split("\n")
    return "\n".join(_shape_line(ln) for ln in lines)


def make_premiere_srt(cues: list[Cue]) -> str:
    """SRT با متن از پیش شکل‌گرفته برای موتور زیرنویس پریمیر."""
    shaped = [Cue(c.start, c.end, shape_text_visual(c.text)) for c in cues]
    return format_srt(shaped)


# ---------------------------------------------------------------- شکستن خط

def wrap_balanced(text: str, max_chars: int) -> list[str]:
    """متن را به حداکثر دو خط متوازن می‌شکند."""
    text = text.strip()
    if len(text) <= max_chars:
        return [text]
    words = text.split()
    if len(words) < 2:
        return [text]
    best: tuple[int, list[str]] | None = None
    for i in range(1, len(words)):
        a = " ".join(words[:i])
        b = " ".join(words[i:])
        if len(a) > max_chars or len(b) > max_chars:
            continue
        score = abs(len(a) - len(b)) + (0 if a.endswith(tuple("،؛")) else 0)
        if best is None or score < best[0]:
            best = (score, [a, b])
    if best:
        return best[1]
    # اگر دو خط جا نشد، نقطه‌ی نزدیک به وسط
    mid = len(words) // 2
    return [" ".join(words[:mid]), " ".join(words[mid:])]

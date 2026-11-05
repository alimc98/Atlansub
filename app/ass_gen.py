"""ساخت فایل ASS برای رندر لایه‌ی شفاف زیرنویس."""
from __future__ import annotations

from .srt_utils import Cue, wrap_balanced


def _ass_time(t: float) -> str:
    t = max(0.0, t)
    h = int(t // 3600)
    m = int(t % 3600 // 60)
    s = t % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "(").replace("}", ")")


def style_metrics(width: int, height: int) -> dict:
    """نسبت‌های استایل بر اساس ابعاد فریم."""
    return {
        "font_size": max(12, round(height * 0.03125)),
        "outline": max(1, round(height * 0.0016)),
        "shadow": max(1, round(height * 0.0008)),
        "margin_v": max(10, round(height * 0.065)),
        "margin_x": max(10, round(width * 0.037)),
    }


def build_ass(
    cues: list[Cue],
    width: int,
    height: int,
    font_name: str = "Vazirmatn",
) -> str:
    m = style_metrics(width, height)
    font_size = m["font_size"]
    margin_x = m["margin_x"]
    usable = max(200, width - 2 * margin_x)
    # میانگین عرض هر کاراکتر فارسی ≈ ۰٫۵۸ برابر اندازه‌ی فونت
    max_chars = max(12, int(usable / (font_size * 0.58)))

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: FA,{font_name},{font_size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,{m['outline']},{m['shadow']},2,{margin_x},{margin_x},{m['margin_v']},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    # نکته: مقدار Spacing باید صفر بماند؛ در libass هر مقدار غیرصفر
    # ترتیب حروف فارسی را برعکس می‌کند.
    lines: list[str] = []
    for c in cues:
        parts = wrap_balanced(c.text, max_chars)
        text = r"\N".join(_escape(p) for p in parts)
        lines.append(
            f"Dialogue: 0,{_ass_time(c.start)},{_ass_time(c.end)},FA,,0,0,0,,{text}"
        )
    return header + "\n".join(lines) + "\n"

#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
rtl_isolate.py — ایزوله‌کردن بلوک‌های فارسی با نویسه‌های کنترلی bidi
====================================================================

برای رندرکننده‌هایی که HTML خام را حذف می‌کنند — مثل ZCode با رندرر
Streamdown — بستهٔ <div dir="rtl"> کار نمی‌کند و خودش به‌صورت متن دیده
می‌شود. راه‌حل، نویسه‌های کنترلی یونیکد است که داخل خود متن زندگی می‌کند:

    RLI = U+2067  آغاز ایزولهٔ راست‌به‌چپ
    PDI = U+2069  پایان ایزوله

هر واحد متنی که نویسهٔ فارسی/عربی دارد بین این دو نویسه بسته می‌شود:
پاراگراف (پیوه‌خط‌های سادهٔ پیاپی) یک‌جا، سطرهای ساختاری (تیتر، فهرست،
نقل‌قول) جداگانه و خانه‌های جدول یکی‌یکی. بلوک کد، سطرهای فقط‌لاتین و
کد درون‌خطی دست‌نخورده می‌مانند.

محدودیت: سطرهای ادامهٔ آیتم چندخطی (خط تورفتگی پس از فهرست) به‌عنوان
پاراگراف جدا بسته می‌شوند؛ چنین آیتمی را در یک سطر بنویسید.

استفاده:
    python tools/rtl_isolate.py file.md              # چاپ نتیجه در خروجی
    python tools/rtl_isolate.py file.md --in-place   # نوشتن روی همان فایل
    python tools/rtl_isolate.py file.md --check      # ۰ اگر همه ایزوله باشند، وگرنه ۱
    python tools/rtl_isolate.py file.md --undo --in-place  # حذف ایزوله‌های این ابزار
    python tools/rtl_isolate.py --check docs/*.md    # بررسی گروهی
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

RLI = "\u2067"  # Right-to-Left Isolate — آغاز ایزولهٔ راست‌به‌چپ
PDI = "\u2069"  # Pop Directional Isolate — پایان ایزوله
UNDO_RE = re.compile("[\u2067\u2069]")
RTL_RE = re.compile(
    "[\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF]"
)
FENCE_RE = re.compile(r"^\s*(?:```|~~~)")
# نشانهٔ ساختاری آغاز سطر: تیتر، نقل‌قول، فهرست گلوله‌ای یا شماره‌ای
PREFIX_RE = re.compile(r"^(?:\s*(?:#{1,6}\s+|>\s*|[-*+]\s+|\d+[.)]\s+))?")


def _has_rtl(text: str) -> bool:
    return bool(RTL_RE.search(text))


def _wrap_segment(body: str) -> str:
    """بسته‌بندی بدنهٔ فارسی بین RLI و PDI؛ اگر پیش‌تر ایزوله باشد دست‌نخورده می‌ماند."""
    core = body.strip()
    if not core or core.startswith(RLI) or core.endswith(PDI):
        return body
    indent = len(body) - len(body.lstrip())
    head = body[:indent]
    tail = body[len(body.rstrip()):]
    return head + RLI + core + PDI + tail


def _wrap_table_row(line: str) -> str:
    """خانه‌های حاوی فارسی در سطر جدول، یکی‌یکی ایزوله می‌شوند."""
    cells = line.split("|")
    wrapped = (
        cell if not _has_rtl(cell) else _wrap_segment(cell) for cell in cells
    )
    return "|".join(wrapped)


def isolate(text: str) -> str:
    """نسخهٔ ایزوله‌شدهٔ سند را برمی‌گرداند؛ عملیات خودتوان است."""
    out: list[str] = []
    run: list[str] = []
    fence = False

    def flush() -> None:
        if run:
            segment = "\n".join(run)
            out.append(_wrap_segment(segment) if _has_rtl(segment) else segment)
            run.clear()

    for line in text.split("\n"):
        if FENCE_RE.match(line):
            flush()
            fence = not fence
            out.append(line)
        elif fence:
            out.append(line)
        elif not line.strip():
            flush()
            out.append(line)
        elif line.startswith("|"):
            flush()
            out.append(_wrap_table_row(line))
        else:
            match = PREFIX_RE.match(line)
            body = line[match.end():]
            if match.group(0).strip():  # تیتر، نقل‌قول، فهرست
                flush()
                out.append(match.group(0) + (_wrap_segment(body) if _has_rtl(body) else body))
            else:  # خطِ پاراگراف؛ با خط‌های پیوستهٔ بعدی یک واحد است
                run.append(line)
    flush()
    return "\n".join(out)


def undo(text: str) -> str:
    """حذف ایزوله‌هایی که این ابزار می‌افزاید (RLI/PDI)."""
    return UNDO_RE.sub("", text)


def is_isolated(text: str) -> bool:
    """درست اگر سند پیش‌تر کامل ایزوله شده باشد و ابزار چیزی به آن نیفزاید."""
    return isolate(text) == text


def main() -> int:
    parser = argparse.ArgumentParser(description="ایزوله‌سازی فارسی با نویسهٔ کنترلی RLI/PDI")
    parser.add_argument("files", nargs="+", help="مسیر یک یا چند فایل متنی")
    parser.add_argument("--check", action="store_true", help="فقط بررسی؛ کد خروج ۱ در صورت ایزوله‌نبودن")
    parser.add_argument("--undo", action="store_true", help="حذف نویسه‌های RLI/PDI")
    parser.add_argument("--in-place", action="store_true", help="نوشتن روی همان فایل")
    args = parser.parse_args()

    failures = 0
    for name in args.files:
        path = Path(name)
        if not path.is_file():
            print(f"فایل پیدا نشد: {path}", file=sys.stderr)
            failures += 1
            continue

        original = path.read_text(encoding="utf-8")
        if args.check:
            ok = is_isolated(original)
            print(f"{'OK ' if ok else 'RED'} {path}")
            failures += 0 if ok else 1
            continue

        result = undo(original) if args.undo else isolate(original)
        if args.in_place:
            path.write_text(result, encoding="utf-8")
            print(f"نوشته شد: {path}")
        else:
            sys.stdout.write(result)

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

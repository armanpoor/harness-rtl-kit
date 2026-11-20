#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
zcode_rtl_css_patch.py — پچ راست‌چین برای رندرر چت ZCode
=========================================================

قانون نویسهٔ کنترلی (RLI/PDI) ترتیب کاراکترها را درست می‌کند اما چیدمان
صفحه را نه: بولت‌ها و متن‌ها در پایهٔ چپ‌به‌راست می‌مانند. این ابزار یک
لایهٔ CSS کوچک به فایل استایل رندرر ZCode می‌افزاید تا جهت پایهٔ هر بلوک
از نخستین نویسهٔ قوی آن تشخیص داده شود (`unicode-bidi: plaintext`):
پاراگراف فارسی راست‌تراز با بولت راست، پاراگراف لاتین چپ‌تراز؛ کد همیشه
چپ‌به‌راست می‌ماند.

پچ به‌صورت بی‌خطر انجام می‌شود:

    --prepare   استخراج app.asar، تزریق CSS، پک به app.asar.rtl-patched
                (در حین اجرای ZCode هم بی‌خطر است؛ فایل اصلی دست نمی‌خورد)
    --apply     تعویض پچ‌شده با اصلی + نگه‌داری پشتیبان (ZCode باید بسته باشد)
    --restore   بازگرداندن پشتیبان (ZCode باید بسته باشد)
    --status    گزارش وضعیت فایل‌ها

پیش‌نیاز: Node.js در مسیر (ابزار `npx asar` صدا زده می‌شود). پس از هر
به‌روزرسانی خودکار ZCode، پچ پاک می‌شود و باید دوباره اجرا شود.

استفاده:
    python tools/zcode_rtl_css_patch.py --prepare
    python tools/zcode_rtl_css_patch.py --apply
    python tools/zcode_rtl_css_patch.py --restore
    python tools/zcode_rtl_css_patch.py --status
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

DEFAULT_ASAR = Path(r"C:\Program Files\ZCode\resources\app.asar")
PATCHED_SUFFIX = ".rtl-patched"
BACKUP_SUFFIX = ".pre-rtl-backup"
CSS_MARKER = "harness-rtl-kit: content-adaptive RTL"

CSS = """
/* === harness-rtl-kit: content-adaptive RTL for chat markdown (re-runnable patch) ===
   Per-block base direction follows the first strong character (unicode-bidi:plaintext):
   Persian blocks render right-to-left with right alignment, Latin blocks stay LTR.
   Scope: Streamdown markdown roots only (chat messages), so app chrome is untouched. */

.space-y-4.whitespace-normal:has(> [data-streamdown]) p,
.space-y-4.whitespace-normal:has(> [data-streamdown]) blockquote,
.space-y-4.whitespace-normal:has(> [data-streamdown]) li,
.space-y-4.whitespace-normal:has(> [data-streamdown]) [data-streamdown^="heading-"],
.space-y-4.whitespace-normal:has(> [data-streamdown]) [data-streamdown="blockquote"],
.space-y-4.whitespace-normal:has(> [data-streamdown]) [data-streamdown="list-item"],
.space-y-4.whitespace-normal:has(> [data-streamdown]) [data-streamdown="table-cell"],
.space-y-4.whitespace-normal:has(> [data-streamdown]) [data-streamdown="table-header-cell"] {
  unicode-bidi: plaintext;
  text-align: start;
}

.space-y-4.whitespace-normal:has(> [data-streamdown]) [data-streamdown="ordered-list"],
.space-y-4.whitespace-normal:has(> [data-streamdown]) [data-streamdown="unordered-list"] {
  direction: rtl;
}

.space-y-4.whitespace-normal:has(> [data-streamdown]) [data-streamdown="table"] {
  direction: rtl;
}

.space-y-4.whitespace-normal:has(> [data-streamdown]) [data-streamdown="code-block"],
.space-y-4.whitespace-normal:has(> [data-streamdown]) [data-streamdown="code-block-body"],
.space-y-4.whitespace-normal:has(> [data-streamdown]) [data-streamdown="code-block"] code,
.space-y-4.whitespace-normal:has(> [data-streamdown]) [data-streamdown="inline-code"] {
  direction: ltr;
  unicode-bidi: isolate;
  text-align: left;
}
/* === end harness-rtl-kit RTL patch === */
"""


def run(cmd: list[str]) -> None:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        sys.stderr.write(result.stdout + result.stderr)
        raise SystemExit(f"فرمان ناموفق: {' '.join(cmd)}")


def inject_css(app_dir: Path) -> list[str]:
    """CSS را به همهٔ استایل‌های اصلی رندرر می‌افزاید؛ خودتوان است."""
    touched: list[str] = []
    for css in sorted((app_dir / "out" / "renderer" / "assets").glob("styles-*.css")):
        text = css.read_text(encoding="utf-8")
        if CSS_MARKER in text:
            touched.append(f"از پیش پچ‌شده: {css.name}")
            continue
        css.write_text(text + CSS, encoding="utf-8")
        touched.append(f"پچ شد: {css.name}")
    if not touched:
        raise SystemExit("هیچ فایل استایل styles-*.css پیدا نشد؛ ساختار رندرر عوض شده است.")
    return touched


def app_running() -> bool:
    probe = subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq ZCode.exe"], capture_output=True, text=True
    )
    return "ZCode.exe" in probe.stdout


def status(asar: Path) -> int:
    patched = asar.with_suffix(asar.suffix + PATCHED_SUFFIX)
    backup = asar.with_suffix(asar.suffix + BACKUP_SUFFIX)
    print(f"asar اصلی:    {asar} {'[موجود]' if asar.is_file() else '[نیست]'}")
    print(f"asar پچ‌شده:  {patched} {'[موجود]' if patched.is_file() else '[نیست]'}")
    print(f"پشتیبان:      {backup} {'[موجود]' if backup.is_file() else '[نیست]'}")
    print(f"ZCode در حال اجراست: {'بله' if app_running() else 'نه'}")
    return 0


def prepare(asar: Path) -> int:
    if app_running():
        print("ZCode در حال اجراست؛ --prepare در حین اجرا بی‌خطر است (فایل اصلی دست نمی‌خورد).")
    with tempfile.TemporaryDirectory(prefix="harness-rtl-kit-") as tmp:
        work = Path(tmp) / "app"
        run(["npx", "--yes", "asar", "extract", str(asar), str(work)])
        for line in inject_css(work):
            print(line)
        patched = asar.with_suffix(asar.suffix + PATCHED_SUFFIX)
        run(["npx", "--yes", "asar", "pack", str(work), str(patched)])
    print(f"پک شد: {patched}")
    print("برای اعمال: ZCode را ببندید و --apply را اجرا کنید (یا باتِ دسکتاپ را بزنید).")
    return 0


def apply(asar: Path) -> int:
    patched = asar.with_suffix(asar.suffix + PATCHED_SUFFIX)
    backup = asar.with_suffix(asar.suffix + BACKUP_SUFFIX)
    if app_running():
        raise SystemExit("ZCode باز است؛ اول ببندیدش و بعد دوباره اجرا کنید.")
    if not patched.is_file():
        raise SystemExit("asar پچ‌شده پیدا نشد؛ اول --prepare را اجرا کنید.")
    if not backup.is_file():
        print("پشتیبان‌گیری از asar اصلی ...")
        asar.replace(backup)
    patched.replace(asar)
    print(f"پچ اعمال شد: {asar}")
    print("حالا ZCode را روشن کنید.")
    return 0


def restore(asar: Path) -> int:
    backup = asar.with_suffix(asar.suffix + BACKUP_SUFFIX)
    if app_running():
        raise SystemExit("ZCode باز است؛ اول ببندیدش و بعد دوباره اجرا کنید.")
    if not backup.is_file():
        raise SystemExit("پشتیبانی نیست؛ چیزی برای بازگردانی نیست.")
    backup.replace(asar)
    print(f"نسخهٔ اصلی بازگشت: {asar}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="پچ راست‌چین چت ZCode (harness-rtl-kit)")
    parser.add_argument("--asar", default=str(DEFAULT_ASAR), help="مسیر app.asar")
    parser.add_argument("--prepare", action="store_true", help="ساخت asar پچ‌شده (بی‌خطر در حین اجرا)")
    parser.add_argument("--apply", action="store_true", help="تعویض پچ‌شده با اصلی (ZCode بسته باشد)")
    parser.add_argument("--restore", action="store_true", help="بازگردانی پشتیبان (ZCode بسته باشد)")
    parser.add_argument("--status", action="store_true", help="گزارش وضعیت")
    args = parser.parse_args()

    asar = Path(args.asar)
    if not asar.is_file():
        raise SystemExit(f"asar پیدا نشد: {asar}")

    if args.status:
        return status(asar)
    if args.prepare:
        return prepare(asar)
    if args.apply:
        return apply(asar)
    if args.restore:
        return restore(asar)
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

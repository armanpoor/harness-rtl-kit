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
CSS_V2_MARKER = "harness-rtl-kit: content-adaptive RTL for chat markdown (v2"

CSS = """
/* === harness-rtl-kit: content-adaptive RTL for chat markdown (v2, re-runnable patch) ===
   v2: no dependency on Streamdown root classes (tailwind-merge may drop them).
   1) Every text block gets unicode-bidi:plaintext — first-strong base direction:
      Persian renders RTL/right-aligned, English stays LTR. Safe app-wide.
   2) Chat markdown lists/tables mirror via their stable data-streamdown attributes.
   3) Blockquotes mirror via data-markdown-blockquote.
   4) Code always stays LTR. */

p, li, td, th, h1, h2, h3, h4, h5, h6, blockquote, dt, dd, summary, figcaption {
  unicode-bidi: plaintext;
  text-align: start;
}

[data-streamdown="unordered-list"],
[data-streamdown="ordered-list"],
[data-streamdown="table"] {
  direction: rtl;
}

[data-streamdown="unordered-list"] {
  padding-left: 0 !important;
  padding-right: 1.25rem !important;
}

[data-streamdown="list-item"] {
  padding-left: 0;
  padding-right: 0.25rem;
}

blockquote[data-markdown-blockquote] {
  border-left-width: 0 !important;
  border-right-width: 2px !important;
  padding-left: 0 !important;
  padding-right: 0.75rem !important;
}

pre, code,
[data-streamdown="code-block"],
[data-streamdown="code-block-body"],
[data-streamdown="inline-code"] {
  direction: ltr;
  text-align: left;
}
/* === end harness-rtl-kit RTL patch (v2) === */
"""

import re as _re

BLOCK_RE = _re.compile(
    r"\n?/\* === harness-rtl-kit:.*?/\* === end harness-rtl-kit RTL patch(?: \(v2\))? === \*/\n?",
    _re.S,
)


def run(cmd: list[str]) -> None:
    import os
    if os.name == "nt" and cmd and cmd[0] == "npx":
        cmd = ["cmd", "/c"] + cmd  # npx در ویندوز شیم .cmd است
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        sys.stderr.write(result.stdout + result.stderr)
        raise SystemExit(f"فرمان ناموفق: {' '.join(cmd)}")


JS = """/* harness-rtl-kit v3 — renderer-side bidi normalizer
   Strips bidi isolates/marks from chat text blocks whose true first-strong
   direction is RTL (they then render RTL under the patched CSS), keeps
   isolates inside Latin-first blocks (they protect Persian there), and wraps
   Persian runs inside code blocks so comments stay readable in LTR code. */
(function () {
  "use strict";
  var ISO_RE = /[\\u2066-\\u2069\\u200e\\u200f]/g;
  var RTL_RE = /[\\u0590-\\u05FF\\u0600-\\u06FF\\u0750-\\u077F\\uFB50-\\uFDFF\\uFE70-\\uFEFF]/;
  var LTR_RE = /[A-Za-z\\u00C0-\\u024F\\u0370-\\u04FF]/;
  var BLOCK_SEL = "p,li,h1,h2,h3,h4,h5,h6,blockquote,td,th,dt,dd";
  var CODE_SEL = '[data-streamdown="code-block"],[data-streamdown="inline-code"],pre,code';
  var RUN_RE = /[\\u0600-\\u06FF\\u0750-\\u077F\\uFB50-\\uFDFF\\uFE70-\\uFEFF][\\u0600-\\u06FF\\u0750-\\u077F\\uFB50-\\uFDFF\\uFE70-\\uFEFF\\u200c \\t0-9\\u060C\\u061B\\u061F.,:()%-]*[\\u0600-\\u06FF\\u0750-\\u077F\\uFB50-\\uFDFF\\uFE70-\\uFEFF]|[\\u0600-\\u06FF\\u0750-\\u077F\\uFB50-\\uFDFF\\uFE70-\\uFEFF]/g;

  function firstStrong(text) {
    for (var i = 0; i < text.length; i++) {
      var ch = text.charAt(i);
      if (RTL_RE.test(ch)) return "R";
      if (LTR_RE.test(ch)) return "L";
    }
    return "L";
  }
  function inCode(el) { return !!(el.closest && el.closest(CODE_SEL)); }
  function textNodes(el) {
    var out = [], w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT, null), n;
    while ((n = w.nextNode())) out.push(n);
    return out;
  }
  function stripIsolates(el) {
    textNodes(el).forEach(function (n) {
      if (ISO_RE.test(n.data)) n.data = n.data.replace(ISO_RE, "");
    });
  }
  function isolatePersianRuns(el) {
    textNodes(el).forEach(function (n) {
      if (!RTL_RE.test(n.data) || n.data.indexOf("\\u2067") !== -1) return;
      n.data = n.data.replace(RUN_RE, function (m) { return "\\u2067" + m + "\\u2069"; });
    });
  }
  function process(root) {
    try {
      var blocks = root.querySelectorAll ? root.querySelectorAll(BLOCK_SEL) : [];
      if (root.matches && root.matches(BLOCK_SEL)) {
        blocks = [root].concat(Array.prototype.slice.call(blocks));
      }
      Array.prototype.forEach.call(blocks, function (el) {
        if (inCode(el)) return;
        var text = el.textContent || "";
        if (!RTL_RE.test(text)) return;
        if (firstStrong(text.replace(ISO_RE, "")) === "R") stripIsolates(el);
      });
      var codes = root.querySelectorAll ? root.querySelectorAll(CODE_SEL) : [];
      if (root.matches && root.matches(CODE_SEL)) {
        codes = [root].concat(Array.prototype.slice.call(codes));
      }
      Array.prototype.forEach.call(codes, isolatePersianRuns);
    } catch (e) { /* never break the app */ }
  }
  var pending = false;
  function schedule() {
    if (pending) return;
    pending = true;
    setTimeout(function () { pending = false; process(document.body); }, 100);
  }
  function start() {
    try {
      new MutationObserver(schedule).observe(document.body, {
        childList: true, subtree: true, characterData: true
      });
    } catch (e) { /* ignore */ }
    schedule();
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }
})();
"""

SCRIPT_TAG = '<script src="./assets/rtl-harness-kit.js"></script>'


def inject_js(app_dir: Path) -> list[str]:
    """نرمال‌ایزر رندرر را به‌صورت فایل + ارجاع در index.html می‌نشاند؛ خودتوان."""
    touched: list[str] = []
    assets = app_dir / "out" / "renderer" / "assets"
    js_file = assets / "rtl-harness-kit.js"
    js_file.write_text(JS, encoding="utf-8")
    touched.append(f"نوشته شد: {js_file.name}")

    index = app_dir / "out" / "renderer" / "index.html"
    html = index.read_text(encoding="utf-8")
    if "rtl-harness-kit.js" not in html:
        if "</body>" not in html:
            raise SystemExit("ساختار index.html تغییر کرده؛ نقطهٔ تزریق پیدا نشد.")
        html = html.replace("</body>", f"{SCRIPT_TAG}\n</body>")
        index.write_text(html, encoding="utf-8")
        touched.append("تزریق شد: ارجاع اسکریپت در index.html")
    else:
        touched.append("ارجاع اسکریپت از قبل در index.html هست")
    return touched


def inject_css(app_dir: Path) -> list[str]:
    """CSS را در استایل‌های رندرر می‌نشاند؛ بلاک پیشین حذف و v2 جایگزین می‌شود."""
    touched: list[str] = []
    for css in sorted((app_dir / "out" / "renderer" / "assets").glob("styles-*.css")):
        text = css.read_text(encoding="utf-8")
        if CSS_V2_MARKER in text:
            touched.append(f"از پیش v2: {css.name}")
            continue
        text = BLOCK_RE.sub("\n", text)  # حذف بلاک قدیمی اگر باشد
        css.write_text(text.rstrip() + "\n" + CSS, encoding="utf-8")
        touched.append(f"پچ شد (v2): {css.name}")
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
        for line in inject_js(work):
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

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
    --apply-when-closed   منتظر می‌ماند ZCode بسته شود، بعد apply می‌کند؛
                برای خودکارسازی پس از آپدیت خودکار اپ (با --relaunch اپ
                بلافاصله دوباره باز می‌شود)
    --doctor    حالت «دکتر» برای زمان‌بندی دوره‌ای: اگر asar پچ‌شده است کاری
                نمی‌کند؛ اگر آپدیتِ اپ پچ را پاک کرده، خودش prepare می‌کند و
                در نخستین تیکِ بعد از بستنِ اپ اعمال می‌کند (اگر اپ همین تازه
                بسته شده باشد، دوباره هم بازش می‌کند). اگر کاربر اپ را نبندد،
                پس از ۱۰ دقیقه انتظار خودش اپ را بااحترام می‌بندد (--no-
                auto-restart برای خاموش‌کردن این رفتار). تیک‌ها کوتاه می‌مانند و
                تشخیصِ حالت پایدار با امضای فایل تقریباً رایگان است. با
                --install-task یک‌بار نصب کنید تا همیشه خودکار باشد.
    --install-task   ساخت زمان‌بندی ویندوز برای اجرای دوره‌ای --doctor
                (هر ۱ دقیقه، بدون پنجره، با pythonw)
    --remove-task    حذف همان زمان‌بندی
    --restore   بازگرداندن پشتیبان (ZCode باید بسته باشد)
    --status    گزارش وضعیت فایل‌ها (شامل پچ‌بودن یا نبودن asar فعلی)
    --force     apply حتی با ZCode باز (اگر سیستم‌عامل فایل را قفل کرده
                باشد با پیام روشن شکست می‌خورد)

پیش‌نیاز: Node.js در مسیر (ابزار `npx asar` صدا زده می‌شود). پس از هر
به‌روزرسانی خودکار ZCode، پچ پاک می‌شود و باید دوباره اجرا شود.
(`--apply` هنگام تعویض، اگر نسخهٔ اصلیِ بی‌پچِ تازه‌تر از پشتیبانِ موجود
باشد — یعنی اپ آپدیت شده — پشتیبان را پیش از تعویض تازه‌سازی می‌کند تا
--restore هیچ‌وقت اپ را به نسخهٔ کهنه برگرداند.)

استفاده:
    python tools/zcode_rtl_css_patch.py --prepare
    python tools/zcode_rtl_css_patch.py --apply
    python tools/zcode_rtl_css_patch.py --apply-when-closed --relaunch
    python tools/zcode_rtl_css_patch.py --install-task   # یک‌بار؛ برای همیشه خودکار
    python tools/zcode_rtl_css_patch.py --doctor         # همان کاری که زمان‌بندی می‌کند
    python tools/zcode_rtl_css_patch.py --restore
    python tools/zcode_rtl_css_patch.py --status
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# زیر pythonw هیچ کنسولی وجود ندارد؛ هر فرزندِ کنسولی (tasklist، cmd، schtasks)
# وگرنه برای خودش پنجرهٔ سیاهِ چشمک‌زن می‌سازد (گزارش ۲۰۲۶-۱۱-۲۸).
CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0

# خروجی فارسی روی کنسول/لولهٔ ویندوز: کدپیج ANSI هرگز نباید print را بشکند
# (مثلاً در اجرای زمان‌بندی‌شده که stdout به فایل لاگ می‌رود)؛ line_buffering
# برای این است که لاگِ واچرِ در حال انتظار زنده دیده شود، نه در لحظهٔ خروج
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

DEFAULT_ASAR = Path(r"C:\Program Files\ZCode\resources\app.asar")
PATCHED_SUFFIX = ".rtl-patched"
BACKUP_SUFFIX = ".pre-rtl-backup"
DOCTOR_LOCK_SUFFIX = ".doctor-lock"
DOCTOR_LOCK_MAX_AGE = 2 * 3600  # قفلِ بی‌صاحبِ کهنه‌تر از این = به‌جامانده از کرش
AUTO_RESTART_GRACE = 600  # ثانیه؛ پس از این‌قدر انتظار، دکتر خودش اپ را بااحترام می‌بندد
TASK_NAME = "HarnessRTLKit-Doctor"
DEFAULT_LOG = Path.home() / ".harness-rtl-kit" / "rtl-doctor.log"
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

CHUNK = 8 * 1024 * 1024  # اسکن نشانِ پچ در asar چندصد-مگابایتی، تکه‌تکه


def is_patched(asar: Path) -> bool:
    """آیا asar فعلی نشان پچ را دارد؟ (بدون استخراج، با اسکن بایتی)"""
    needle = CSS_V2_MARKER.encode("utf-8")
    with asar.open("rb") as fh:
        tail = b""
        while True:
            block = fh.read(CHUNK)
            if not block:
                return False
            if needle in tail + block:
                return True
            tail = block[-len(needle):]


def file_sha256(path: Path) -> str:
    import hashlib

    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            block = fh.read(CHUNK)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def _sig_of(path: Path) -> dict:
    """امضای ارزان فایل برای تشخیص تغییر (بدون خواندن محتوا)."""
    st = path.stat()
    return {"size": st.st_size, "mtime_ns": st.st_mtime_ns}


def run(cmd: list[str]) -> None:
    if os.name == "nt" and cmd and cmd[0] == "npx":
        cmd = ["cmd", "/c"] + cmd  # npx در ویندوز شیم .cmd است
    result = subprocess.run(
        cmd, capture_output=True, text=True, creationflags=CREATE_NO_WINDOW
    )
    if result.returncode != 0:
        if sys.stderr is not None:  # در pythonw استانداردِ خطا نیست
            sys.stderr.write(result.stdout + result.stderr)
        raise SystemExit(f"فرمان ناموفق: {' '.join(cmd)}")


JS = """/* harness-rtl-kit v4 — renderer-side bidi normalizer
   v3 behavior kept: strips bidi isolates/marks from RTL chat blocks and wraps
   Persian runs inside code blocks.
   v4 — majority-direction policy (fixes the "sometimes it falls apart" class):
   1) RTL-majority blocks: when Arabic-script strong chars outnumber Latin ones
      (>=3 Arabic chars), the block is forced RTL (dir=rtl + inline
      unicode-bidi:normal, overriding the plaintext CSS). A Persian sentence led
      by a Latin chip ("G0 — چک سلامت نود VPN — پروب را اجرا می‌کنم …") now reads
      correctly right-to-left instead of rendering its body as a mirrored box.
   2) LTR-majority blocks (mostly-English lines with some Persian): bare Persian
      runs are auto-wrapped in ⁧…⁩ (the treatment code blocks already had), so
      unwrapped Persian inside Latin-led lines can no longer scramble.
   3) Coverage widened: pure text leaves outside p/li/h* (sidebar titles,
      collapsed message previews, buttons, labels) are normalized too, guarded
      against code/input/contenteditable and against flex/grid containers.
   Re-verified on ZCode 3.19.1 / Electron 44.7.0 (2026-11-22): data-streamdown
   list/table attributes are still emitted; code blocks render as plain <pre>
   (covered by pre,code); the data-streamdown="code-block"/"inline-code"
   selectors are kept for older builds and stay harmless. */
(function () {
  "use strict";
  var ISO_RE = /[\\u202A-\\u202E\\u2066-\\u2069\\u200e\\u200f]/g;
  var ISO_TEST_RE = /[\\u202A-\\u202E\\u2066-\\u2069\\u200e\\u200f]/;
  var HAS_ISO_RE = /[\\u202A-\\u202E\\u2066-\\u2069]/;
  var RTL_RE = /[\\u0590-\\u05FF\\u0600-\\u06FF\\u0750-\\u077F\\uFB50-\\uFDFF\\uFE70-\\uFEFF]/;
  var LTR_RE = /[A-Za-z\\u00C0-\\u024F\\u0370-\\u04FF]/;
  var BLOCK_SEL = "p,li,h1,h2,h3,h4,h5,h6,blockquote,td,th,dt,dd,summary,figcaption";
  var CODE_SEL = '[data-streamdown="code-block"],[data-streamdown="inline-code"],pre,code';
  var GUARD_SEL = CODE_SEL + ',input,textarea,select,[contenteditable="true"],[contenteditable=""]';
  var INLINE_OK = /^(span|strong|em|b|i|a|code|small|mark|sub|sup|u|s|abbr|time)$/i;
  var SKIP_TAG = { SCRIPT: 1, STYLE: 1, NOSCRIPT: 1, TEXTAREA: 1, TEMPLATE: 1 };
  var RUN_RE = /[\\u0600-\\u06FF\\u0750-\\u077F\\uFB50-\\uFDFF\\uFE70-\\uFEFF][\\u0600-\\u06FF\\u0750-\\u077F\\uFB50-\\uFDFF\\uFE70-\\uFEFF\\u200c \\t0-9\\u060C\\u061B\\u061F.,:()%-]*[\\u0600-\\u06FF\\u0750-\\u077F\\uFB50-\\uFDFF\\uFE70-\\uFEFF]|[\\u0600-\\u06FF\\u0750-\\u077F\\uFB50-\\uFDFF\\uFE70-\\uFEFF]/g;

  function counts(text) {
    var ar = 0, la = 0, i, ch;
    for (i = 0; i < text.length; i++) {
      ch = text.charAt(i);
      if (RTL_RE.test(ch)) ar++;
      else if (LTR_RE.test(ch)) la++;
    }
    return { ar: ar, la: la };
  }
  function inCode(el) { return !!(el.closest && el.closest(GUARD_SEL)); }
  function textNodes(el) {
    var out = [], w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT, null), n;
    while ((n = w.nextNode())) out.push(n);
    return out;
  }
  function stripIsolates(el) {
    textNodes(el).forEach(function (n) {
      if (!n.parentElement || SKIP_TAG[n.parentElement.tagName]) return;
      if (ISO_TEST_RE.test(n.data)) n.data = n.data.replace(ISO_RE, "");
    });
  }
  function isolatePersianRuns(el) {
    textNodes(el).forEach(function (n) {
      if (!n.parentElement || SKIP_TAG[n.parentElement.tagName]) return;
      if (!RTL_RE.test(n.data) || HAS_ISO_RE.test(n.data)) return;
      n.data = n.data.replace(RUN_RE, function (m) { return "\\u2067" + m + "\\u2069"; });
    });
  }
  function displayOf(el) {
    try { return getComputedStyle(el).display; } catch (e) { return ""; }
  }
  function isSafeForDir(el) {
    // Direction is only forced on block-ish elements: never on bare inline
    // (their block ancestor carries it) and never on flex/grid containers
    // (direction mirrors flex/grid child layout).
    var disp = displayOf(el);
    if (disp === "inline" || disp === "flex" || disp === "inline-flex" ||
        disp === "grid" || disp === "inline-grid" || disp === "none") return false;
    for (var i = 0; i < el.children.length; i++) {
      if (!INLINE_OK.test(el.children[i].tagName)) return false;
    }
    return true;
  }
  function normalize(el) {
    if (!el || !el.tagName || SKIP_TAG[el.tagName] || inCode(el)) return;
    var raw = el.textContent || "";
    if (!RTL_RE.test(raw)) return;
    var c = counts(raw.replace(ISO_RE, ""));
    if (c.ar === 0) return;
    if (c.ar > c.la && c.ar >= 3 && isSafeForDir(el)) {
      el.setAttribute("dir", "rtl");
      el.style.unicodeBidi = "normal";
      stripIsolates(el);
    } else if (c.la >= c.ar && isSafeForDir(el)) {
      // Latin-led line with some Persian: protect each Persian run so the
      // bidi algorithm cannot reorder fragments (same treatment as code).
      isolatePersianRuns(el);
    }
  }
  function nearestBlockish(el) {
    while (el && el !== document.body) {
      if (SKIP_TAG[el.tagName]) return null;
      if (el.matches && el.matches(BLOCK_SEL)) return null; // blocks pass owns it
      if (displayOf(el) !== "inline") return el;
      el = el.parentElement;
    }
    return null;
  }
  function process(root) {
    try {
      var blocks = root.querySelectorAll ? root.querySelectorAll(BLOCK_SEL) : [];
      if (root.matches && root.matches(BLOCK_SEL)) {
        blocks = [root].concat(Array.prototype.slice.call(blocks));
      }
      Array.prototype.forEach.call(blocks, normalize);
      // Text leaves outside the standard blocks (sidebar titles, collapsed
      // previews, buttons): climb from each text node to the nearest
      // block-ish ancestor and normalize that, deduped per pass.
      try {
        var seen = typeof WeakSet === "function" ? new WeakSet() : null;
        var w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, null), n;
        while ((n = w.nextNode())) {
          var tEl = n.parentElement;
          if (!tEl || SKIP_TAG[tEl.tagName]) continue;
          var pEl = nearestBlockish(tEl);
          if (!pEl || (seen && seen.has(pEl))) continue;
          if (seen) seen.add(pEl);
          normalize(pEl);
        }
      } catch (e2) { /* ignore */ }
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
        ["tasklist", "/FI", "IMAGENAME eq ZCode.exe"],
        capture_output=True, text=True, creationflags=CREATE_NO_WINDOW,
    )
    return "ZCode.exe" in probe.stdout


def status(asar: Path) -> int:
    patched = asar.with_suffix(asar.suffix + PATCHED_SUFFIX)
    backup = asar.with_suffix(asar.suffix + BACKUP_SUFFIX)
    print(f"asar اصلی:    {asar} {'[موجود]' if asar.is_file() else '[نیست]'}")
    if asar.is_file():
        state = "پچ‌شده (v2)" if is_patched(asar) else "بدون پچ (مثلاً پس از آپدیت خودکار اپ)"
        print(f"وضعیت asar اصلی: {state}")
    print(f"asar پچ‌شده:  {patched} {'[موجود]' if patched.is_file() else '[نیست]'}")
    print(f"پشتیبان:      {backup} {'[موجود]' if backup.is_file() else '[نیست]'}")
    if asar.is_file() and backup.is_file():
        same = (
            asar.stat().st_size == backup.stat().st_size
            and file_sha256(asar) == file_sha256(backup)
        )
        print(f"پشتیبان هم‌اندازهٔ asar اصلی: {'بله' if same else 'نه (اپ آپدیت شده)'}")
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
    print("برای اعمال: ZCode را ببندید و --apply را اجرا کنید،")
    print("یا همین حالا --apply-when-closed --relaunch را به‌صورت پس‌زمینه راه بیندازید.")
    return 0


def ensure_backup(asar: Path, backup: Path) -> bool:
    """پشتیبانِ نسخهٔ اصلیِ بی‌پچ را تازه نگه می‌دارد. True یعنی پشتیبان تازه نوشته شد.

    پشتیبان با «کپی اتمیک» ساخته می‌شود نه move — اگر تعویض بعدی به‌خاطر
    قفلِ فایل شکست بخورد، asar اصلی باید سر جای خودش باشد.
    """
    if backup.is_file():
        if (
            asar.stat().st_size == backup.stat().st_size
            and file_sha256(asar) == file_sha256(backup)
        ):
            return False
        print("پشتیبانِ موجود با نسخهٔ اصلی فعلی فرق دارد (اپ آپدیت شده)؛ تازه‌سازی پشتیبان ...")
    else:
        print("پشتیبان‌گیری از asar اصلی ...")
    tmp = backup.with_name(backup.name + ".tmp")
    shutil.copyfile(asar, tmp)
    os.replace(tmp, backup)
    return True


def apply(asar: Path, force: bool = False, retries: int = 0, retry_pause: float = 2.0) -> int:
    patched = asar.with_suffix(asar.suffix + PATCHED_SUFFIX)
    backup = asar.with_suffix(asar.suffix + BACKUP_SUFFIX)
    if not patched.is_file():
        raise SystemExit("asar پچ‌شده پیدا نشد؛ اول --prepare را اجرا کنید.")
    if app_running():
        if not force:
            raise SystemExit(
                "ZCode باز است؛ اول ببندیدش و بعد دوباره اجرا کنید "
                "(یا از --apply-when-closed استفاده کنید)."
            )
        print("هشدار: ZCode باز است (--force)؛ اگر فایل قفل باشد تعویض شکست می‌خورد.")
    if not is_patched(asar):
        ensure_backup(asar, backup)
    attempt = 0
    while True:
        try:
            patched.replace(asar)
            break
        except OSError as exc:
            attempt += 1
            if attempt > retries:
                raise SystemExit(
                    "تعویض asar ناموفق بود؛ فایل در حال استفاده است:\n"
                    f"    {exc}\n"
                    "ZCode را کامل ببندید و دوباره تلاش کنید (یا --apply-when-closed)."
                ) from exc
            print(f"فایل قفل بود (تلاش {attempt} از {retries})؛ "
                  f"{retry_pause:.0f} ثانیه بعد دوباره ...")
            time.sleep(retry_pause)
    print(f"پچ اعمال شد: {asar}")
    print("حالا ZCode را روشن کنید.")
    return 0


def apply_when_closed(asar: Path, relaunch: bool, poll_seconds: int) -> int:
    """واچر: بعد از بسته‌شدن ZCode پچ را اعمال می‌کند؛ کاربرد پس از آپدیت خودکار اپ.

    درست همان لحظهٔ بسته‌شدن، خروجِ اپ یا بازشدنِ دوبارهٔ سریعِ آن می‌تواند
    فایل را چند ثانیه‌ای دوباره قفل کند؛ به‌جای تسلیم‌شدن، تلاش مجدد می‌کنیم
    و اگر اپ واقعاً دوباره باز شده باشد، به حلقهٔ انتظار برمی‌گردیم.
    """
    patched = asar.with_suffix(asar.suffix + PATCHED_SUFFIX)
    if not patched.is_file():
        raise SystemExit("asar پچ‌شده پیدا نشد؛ اول --prepare را اجرا کنید.")
    print(f"منتظر بسته‌شدن ZCode (بررسی هر {poll_seconds} ثانیه)؛ این فرایند را باز نگه دارید ...")
    while True:
        while app_running():
            time.sleep(poll_seconds)
        print("ZCode بسته شد؛ اعمال پچ ...")
        try:
            code = apply(asar, force=True, retries=30, retry_pause=2.0)
        except SystemExit as exc:
            if app_running():
                # بین کشفِ بسته‌شدن و تعویض، اپ دوباره باز شده؛ تسلیم نه، انتظار
                print("اپ دوباره باز شده و فایل را قفل کرده؛ پچ اعمال نشد — دوباره به انتظار می‌روم ...")
                continue
            raise
        break
    if relaunch and code == 0:
        exe = asar.parent.parent / "ZCode.exe"
        if exe.is_file():
            os.startfile(str(exe))  # جدا از این فرایند باز می‌شود
            print(f"ZCode دوباره باز شد: {exe}")
        else:
            print(f"ZCode.exe در مسیر متعارف نبود؛ دستی باز کنید: {exe}")
    return code


def _doctor_log(msg: str, log_path: Path | None) -> None:
    line = time.strftime("%Y-%m-%d %H:%M:%S") + "  " + msg
    print(line)  # در pythonw بی‌اثر است؛ لاگِ فایل نقش را می‌برد
    if log_path is not None:
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with log_path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        except OSError:
            pass


def _relaunch_zcode(asar: Path, log) -> None:
    exe = asar.parent.parent / "ZCode.exe"
    if exe.is_file():
        os.startfile(str(exe))  # جدا از این فرایند باز می‌شود
        log(f"ZCode دوباره باز شد: {exe}")
    else:
        log(f"ZCode.exe در مسیر متعارف نبود؛ دستی باز کنید: {exe}")


def _graceful_close_app(timeout: float = 25.0) -> bool:
    """بستنِ بااحترام ZCode (همانند کلیکِ X؛ سشن‌ها ذخیره می‌شوند) و انتظار تا خروج کامل."""
    subprocess.run(
        ["taskkill", "/IM", "ZCode.exe"],
        capture_output=True, text=True, creationflags=CREATE_NO_WINDOW,
    )
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not app_running():
            return True
        time.sleep(2)
    return False


def doctor(asar: Path, log_path: Path | None, force: bool = False,
           auto_restart: bool = True) -> int:
    """حالت «دکتر» برای زمان‌بندی دوره‌ای — چرخهٔ آپدیت اپ را خودکار می‌بندد.

    هر تیک کوتاه است و هیچ‌وقت منتظر نمی‌ماند:
    - اگر asar پچ‌شده است (تشخیص ارزان با امضای size+mtime در فایل وضعیت)،
      بی‌هزینه خارج می‌شود.
    - اگر آپدیت اپ پچ را پاک کرده باشد: prepare می‌کند (در حین اجرای اپ امن
      است) و تیک‌های بعدی منتظر بسته‌شدن اپ می‌مانند؛ در نخستین تیکِ پس از
      بستن، apply می‌شود. اگر اپ همین تازه بسته شده باشد دوباره بازش می‌کند؛
      اگر از قبل بسته بوده، بی‌سروصدا اعمال می‌کند تا در باز شدنِ بعدیِ خودِ
      کاربر پچ‌شده بالا بیاید.
    - اگر آپدیت‌کننده همین لحظه در حال نوشتن asar باشد، به تیک بعدی می‌سپارد؛
      فایل پچ‌شدهٔ ناقص (pack نیمه‌کاره) حذف و بازسازی می‌شود.
    قفلِ فایل، نمونه‌های موازی را یکی می‌کند و قفلِ به‌جا مانده از کرش بعد از
    دو ساعت کهنه می‌شود.
    """
    def log(msg: str) -> None:
        _doctor_log(msg, log_path)

    state_path = (log_path or DEFAULT_LOG).with_suffix(".state.json")
    patched = asar.with_suffix(asar.suffix + PATCHED_SUFFIX)
    lock = asar.with_suffix(asar.suffix + DOCTOR_LOCK_SUFFIX)
    got_lock = False
    for attempt in (1, 2):
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            got_lock = True
            break
        except FileExistsError:
            if time.time() - lock.stat().st_mtime < DOCTOR_LOCK_MAX_AGE:
                return 0  # تیک موازی؛ بی‌سروصدا (لاگ هر دقیقه بی‌معناست)
            log("قفلِ کهنه و بی‌صاحب پاک شد؛ ادامه.")
            lock.unlink(missing_ok=True)
    if not got_lock:
        log("قفلِ doctor آزاد نشد؛ خروج.")
        return 1

    def save_state(st: dict) -> None:
        try:
            state_path.parent.mkdir(parents=True, exist_ok=True)
            state_path.write_text(
                json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8"
            )
        except OSError:
            pass

    try:
        st = {}
        try:
            st = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
        now = time.time()
        sig = _sig_of(asar)

        if sig == st.get("patched_sig"):
            # حالت پایدار؛ فقط ضربان ساعتی برای اطمینانِ زنده‌بودن
            if now - st.get("heartbeat_ts", 0) > 3600:
                log("وضعیت سالم: asar پچ‌شده است.")
                st["heartbeat_ts"] = now
                save_state(st)
            return 0

        if running := app_running():
            st["last_seen_running_ts"] = now

        if sig != st.get("unpatched_sig"):
            # چهرهٔ ناشناخته: آپدیت تازه یا نخستین اجرا — بررسی کامل
            if is_patched(asar):
                st["patched_sig"] = sig
                save_state(st)
                log("asar پچ‌شده است (امضا ثبت شد).")
                return 0
            # اگر آپدیت‌کننده همین لحظه در حال نوشتن asar باشد، به تیک بعدی می‌سپاریم
            time.sleep(3)
            if _sig_of(asar) != sig:
                log("asar در حال تغییر است (آپدیت در جریان)؛ تیک بعدی بررسی می‌کند.")
                save_state(st)
                return 0
            if not patched.is_file() or patched.stat().st_mtime < asar.stat().st_mtime:
                log("asar بی‌پچ است (آپدیت اپ پچ را پاک کرده)؛ ساخت نسخهٔ پچ‌شده ...")
                prepare(asar)
            if not is_patched(patched):
                # فایل ناقص (مثلاً pack نیمه‌کاره پس از قطع فرایند): بازسازی
                log("فایل پچ‌شده نشان پچ را ندارد؛ حذف و ساخت دوباره ...")
                patched.unlink(missing_ok=True)
                prepare(asar)
                if not is_patched(patched):
                    log("خطا: دوباره بدون نشان؛ تیک بعدی دوباره تلاش می‌کند.")
                    save_state(st)
                    return 1
            st["unpatched_sig"] = sig
            save_state(st)

        # asar بی‌پچِ شناخته‌شده و نسخهٔ پچ‌شدهٔ آماده
        if running and not force:
            st.setdefault("unpatched_first_seen_ts", now)
            if auto_restart and now - st["unpatched_first_seen_ts"] >= AUTO_RESTART_GRACE:
                # کاربر فرصتِ بستنِ دستی را داشته؛ حالا خودمان بااحترام می‌بندیم
                log("بیش از ۱۰ دقیقه است اپ با asar بی‌پچ باز است؛ بستنِ بااحترامِ خودکار ...")
                if _graceful_close_app():
                    log("ZCode بسته شد؛ اعمال پچ ...")
                else:
                    log("اپ بسته نشد؛ تیک بعدی دوباره تلاش می‌کند.")
                    save_state(st)
                    return 0
            else:
                save_state(st)  # ضربان: به‌روزرسانیِ last_seen_running_ts روی دیسک
                return 0
        else:
            log("ZCode بسته است؛ اعمال پچ ...")
        save_state(st)
        log("ZCode بسته است؛ اعمال پچ ...")
        new_sig = _sig_of(patched)  # پس از تعویض، امضای asar همین می‌شود
        code = apply(asar, force=True, retries=30)
        if code == 0:
            log("پچ اعمال شد.")
            st["patched_sig"] = new_sig
            st.pop("unpatched_first_seen_ts", None)
            if now - st.get("last_seen_running_ts", 0) < 180:
                # اپ همین تازه بسته شده (کاربر منتظرِ چرخه است)؛ دوباره بازش کن
                _relaunch_zcode(asar, log)
            else:
                log("در باز شدنِ بعدیِ ZCode، نسخهٔ پچ‌شده بالا می‌آید.")
            save_state(st)
            return code
        log("اعمال پچ ناموفق بود؛ تیک بعدی دوباره تلاش می‌کند.")
        save_state(st)
        return code
    finally:
        lock.unlink(missing_ok=True)


def install_task(log_path: Path) -> int:
    """زمان‌بندی ویندوز: اجرای دوره‌ای --doctor با pythonw، بدون پنجره."""
    if os.name != "nt":
        raise SystemExit("زمان‌بندی فقط روی ویندوز است؛ در بقیهٔ سیستم‌ها cron بچینید.")
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    if not pythonw.is_file():
        pythonw = Path(sys.executable)
    script = Path(__file__).resolve()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    parts = [pythonw, script, "--doctor", "--log", log_path]
    tr = " ".join(f'"{p}"' if " " in str(p) else str(p) for p in parts)
    run(["schtasks", "/create", "/tn", TASK_NAME, "/tr", tr,
         "/sc", "minute", "/mo", "1", "/f"])
    # پیش‌فرضِ schtasks: «شروع فقط با برق شهری» — روی لپ‌تاپِ باتری‌ای تسک
    # هرگز اجرا نمی‌شود و در وضعیت Queued می‌ماند (گزارش ۲۰۲۶-۱۱-۲۸)
    ps = (
        "$t = Get-ScheduledTask -TaskName '" + TASK_NAME + "';"
        "$t.Settings.DisallowStartIfOnBatteries = $false;"
        "$t.Settings.StopIfGoingOnBatteries = $false;"
        "$t.Settings.StartWhenAvailable = $true;"
        "$t | Set-ScheduledTask | Out-Null"
    )
    run(["powershell", "-NoProfile", "-Command", ps])
    print("شرایط باتری/خواب تنظیم شد: روی باتری هم اجرا می‌شود و تیک‌های از دست رفته پس از بیداری جبران می‌شوند.")
    print(f"زمان‌بندی «{TASK_NAME}» ساخته شد: هر ۱ دقیقه (بی‌پنجره، با pythonw).")
    print(f"حذف: python \"{script}\" --remove-task")
    print(f"لاگ دکتر: {log_path}")
    return 0


def remove_task() -> int:
    if os.name != "nt":
        raise SystemExit("زمان‌بندی فقط روی ویندوز است.")
    run(["schtasks", "/delete", "/tn", TASK_NAME, "/f"])
    print(f"زمان‌بندی «{TASK_NAME}» حذف شد.")
    return 0


def restore(asar: Path, force: bool = False) -> int:
    backup = asar.with_suffix(asar.suffix + BACKUP_SUFFIX)
    if app_running() and not force:
        raise SystemExit("ZCode باز است؛ اول ببندیدش و بعد دوباره اجرا کنید.")
    if not backup.is_file():
        raise SystemExit("پشتیبانی نیست؛ چیزی برای بازگردانی نیست.")
    tmp = backup.with_name(backup.name + ".tmp")
    shutil.copyfile(backup, tmp)
    os.replace(tmp, asar)  # پشتیبان حذف نمی‌شود؛ restore قابل تکرار است
    print(f"نسخهٔ اصلی بازگشت: {asar}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="پچ راست‌چین چت ZCode (harness-rtl-kit)")
    parser.add_argument("--asar", default=str(DEFAULT_ASAR), help="مسیر app.asar")
    parser.add_argument("--prepare", action="store_true", help="ساخت asar پچ‌شده (بی‌خطر در حین اجرا)")
    parser.add_argument("--apply", action="store_true", help="تعویض پچ‌شده با اصلی (ZCode بسته باشد)")
    parser.add_argument(
        "--apply-when-closed",
        action="store_true",
        help="منتظر بسته‌شدن ZCode می‌ماند و بعد apply می‌کند",
    )
    parser.add_argument(
        "--relaunch",
        action="store_true",
        help="بعد از --apply-when-closed، اپ را دوباره باز می‌کند",
    )
    parser.add_argument(
        "--poll-interval",
        type=int,
        default=15,
        help="فاصلهٔ بررسی در --apply-when-closed (ثانیه، پیش‌فرض ۱۵)",
    )
    parser.add_argument("--force", action="store_true", help="apply حتی با ZCode باز")
    parser.add_argument(
        "--retries",
        type=int,
        default=3,
        help="تعداد تلاش مجدد تعویض در صورت قفل‌بودن فایل (پیش‌فرض ۳؛ واچر ۳۰)",
    )
    parser.add_argument(
        "--doctor",
        action="store_true",
        help="بررسی دوره‌ای: پاک‌شدن پچ را خودکار ترمیم می‌کند (برای زمان‌بندی)",
    )
    parser.add_argument(
        "--no-auto-restart",
        action="store_true",
        help="دکتر خودش اپ را برای اعمال پچ نبندد؛ فقط منتظر بستنِ دستی بماند",
    )
    parser.add_argument(
        "--install-task",
        action="store_true",
        help="زمان‌بندی ویندوز برای اجرای دوره‌ای --doctor (هر ۱۵ دقیقه)",
    )
    parser.add_argument("--remove-task", action="store_true", help="حذف زمان‌بندی دکتر")
    parser.add_argument(
        "--log",
        default=None,
        help="مسیر فایل لاگ برای --doctor (پیش‌فرض فقط خروجی)",
    )
    parser.add_argument("--restore", action="store_true", help="بازگردانی پشتیبان (ZCode بسته باشد)")
    parser.add_argument("--status", action="store_true", help="گزارش وضعیت")
    args = parser.parse_args()

    asar = Path(args.asar)
    if not asar.is_file():
        raise SystemExit(f"asar پیدا نشد: {asar}")

    if args.install_task:
        return install_task(Path(args.log) if args.log else DEFAULT_LOG)
    if args.remove_task:
        return remove_task()
    if args.status:
        return status(asar)
    if args.prepare:
        return prepare(asar)
    if args.apply:
        return apply(asar, force=args.force, retries=args.retries)
    if args.apply_when_closed:
        return apply_when_closed(asar, relaunch=args.relaunch, poll_seconds=args.poll_interval)
    if args.doctor:
        return doctor(
            asar,
            Path(args.log) if args.log else None,
            force=args.force,
            auto_restart=not args.no_auto_restart,
        )
    if args.restore:
        return restore(asar, force=args.force)
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

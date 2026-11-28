# -*- coding: utf-8 -*-
"""تست پایان‌به‌انتهای v3 اسکریپت پچ ZCode روی یک asar فیکسچر کوچک.

مسیر واقعی app.asar دست نمی‌خورد؛ همه‌چیز روی فیکسچر موقت است.
فازها: prepare → apply → شبیه‌سازی آپدیت خودکار اپ → apply با تازه‌سازی
پشتیبان → apply دوباره (بدون خراب‌کردن پشتیبان) → restore قابل تکرار.
در محیط بدون npx با ملایمت رد می‌شود (SKIP).
"""
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "tools" / "zcode_rtl_css_patch.py"
MARKER = "harness-rtl-kit: content-adaptive RTL for chat markdown (v2".encode("utf-8")

if not SCRIPT.is_file():
    sys.exit("اسکریپت پچ پیدا نشد")
if shutil.which("npx") is None:
    print("SKIP: npx در دسترس نیست؛ تست جریان پچ رد شد")
    sys.exit(0)

WORK = Path(tempfile.mkdtemp(prefix="zcode-patch-fixture-"))
FX = WORK / "fx"
ASAR = WORK / "fixture.asar"

failures = []


def check(name: str, ok: bool, extra: str = "") -> None:
    print(("PASS " if ok else "FAIL ") + name + ((" — " + extra) if extra else ""))
    if not ok:
        failures.append(name)


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def run(args, expect_rc=0):
    r = subprocess.run(
        [sys.executable, "-I", str(SCRIPT), "--asar", str(ASAR)] + args,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if r.returncode != expect_rc:
        print(f"  unexpected rc={r.returncode} (want {expect_rc}) for {args}")
        print("  stdout:", r.stdout.strip())
        print("  stderr:", r.stderr.strip())
    return r


def build_fixture():
    if FX.exists():
        shutil.rmtree(FX)
    css = FX / "out" / "renderer" / "assets"
    css.mkdir(parents=True)
    (css / "styles-AbC123.css").write_text(":root{color:red}\n", encoding="utf-8")
    (FX / "out" / "renderer" / "index.html").write_text(
        "<!doctype html><html><body><div id=root></div></body></html>\n",
        encoding="utf-8",
    )


def pack():
    r = subprocess.run(
        ["cmd", "/c", "npx", "--yes", "asar", "pack", str(FX), str(ASAR)]
        if os.name == "nt"
        else ["npx", "--yes", "asar", "pack", str(FX), str(ASAR)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if r.returncode != 0:
        print(r.stdout, r.stderr)
        sys.exit("asar pack ناموفق بود")


try:
    # --- فاز ۱: نصب تمیز، prepare، وضعیت ---
    build_fixture()
    pack()
    clean_v1_sha = sha(ASAR)
    r = run(["--status"])
    check("status: clean asar reported unpatched", "بدون پچ" in r.stdout)

    run(["--prepare"])
    patched = Path(str(ASAR) + ".rtl-patched")
    check("prepare created patched asar", patched.is_file())
    check("patched asar is bigger than clean", patched.stat().st_size > ASAR.stat().st_size)

    # --- فاز ۲: apply با اپ باز باید رد شود (محیط با اپ باز) یا موفق شود (بدون اپ) ---
    r = run(["--apply"], expect_rc=None)
    if r.returncode == 1 and "ZCode باز است" in (r.stderr + r.stdout):
        check("apply refused while app running", True)
    elif r.returncode == 0:
        check("apply refused while app running (env without app: applied)", True)
        run(["--prepare"])  # فایل پچ‌شده مصرف شد؛ دوباره بساز
    else:
        check("apply probe produced a known outcome", False, f"rc={r.returncode}")

    # --- فاز ۳: apply با force، پشتیبان v1 ---
    run(["--apply", "--force"])
    check("apply swapped patched in", MARKER in ASAR.read_bytes())
    check("patched file consumed", not patched.is_file())
    backup = Path(str(ASAR) + ".pre-rtl-backup")
    check("backup created", backup.is_file() and sha(backup) == clean_v1_sha)

    # --- فاز ۴: محتوای پچ‌شده واقعاً تزریق شده؟ ---
    chk = WORK / "check-extract"
    subprocess.run(
        ["cmd", "/c", "npx", "--yes", "asar", "extract", str(ASAR), str(chk)]
        if os.name == "nt"
        else ["npx", "--yes", "asar", "extract", str(ASAR), str(chk)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    css_files = list((chk / "out" / "renderer" / "assets").glob("styles-*.css"))
    css_text = css_files[0].read_text(encoding="utf-8")
    check("CSS injected into styles-*.css",
          MARKER.decode() in css_text and "unicode-bidi: plaintext" in css_text)
    js_ok = (chk / "out" / "renderer" / "assets" / "rtl-harness-kit.js").is_file()
    html_ok = "rtl-harness-kit.js" in (chk / "out" / "renderer" / "index.html").read_text(encoding="utf-8")
    check("JS normalizer injected + referenced in index.html", js_ok and html_ok)
    shutil.rmtree(chk)

    # --- فاز ۵: شبیه‌سازی آپدیت خودکار اپ (asar تمیزِ تازه) ---
    (FX / "out" / "renderer" / "assets" / "styles-AbC123.css").write_text(
        ":root{color:red}\nbody{margin:0}\n", encoding="utf-8"
    )
    pack()
    clean_v2_sha = sha(ASAR)
    check("update simulation: clean v2 differs from v1", clean_v2_sha != clean_v1_sha)
    r = run(["--status"])
    check("status after update: unpatched + stale backup",
          "بدون پچ" in r.stdout and "نه (اپ آپدیت شده)" in r.stdout)

    # --- فاز ۶: prepare دوباره روی نسخهٔ تازه، سپس apply با تازه‌سازی پشتیبان ---
    run(["--prepare"])
    check("re-prepare on new version", patched.is_file())
    run(["--apply", "--force"])
    check("apply v2 swapped in", MARKER in ASAR.read_bytes())
    check("STALE BACKUP REFRESHED to clean v2", sha(backup) == clean_v2_sha,
          f"backup={sha(backup)[:12]} want={clean_v2_sha[:12]}")

    # --- فاز ۷: apply مجدد روی asarِ همین حالا پچ‌شده؛ پشتیبان نباید خراب شود ---
    run(["--prepare"])
    run(["--apply", "--force"])
    check("re-apply keeps patched state", MARKER in ASAR.read_bytes())
    check("re-apply did NOT overwrite good backup", sha(backup) == clean_v2_sha)

    # --- فاز ۸: restore به نسخهٔ بی‌پچِ همان نسخهٔ نصب؛ قابل تکرار ---
    run(["--restore", "--force"])
    check("restore returned clean v2 (no downgrade)",
          sha(ASAR) == clean_v2_sha and MARKER not in ASAR.read_bytes())
    run(["--restore", "--force"])
    check("restore is repeatable", sha(ASAR) == clean_v2_sha)

    # --- فاز ۹: قفلِ گذرا روی فایل → تعویض باید با تلاش مجدد موفق شود ---
    # (بازسازی سناریوی واقعی ۲۰۲۶-۱۱-۲۳: در فاصلهٔ خروج اپ، فایل چند ثانیه‌ای
    #  دوباره قفل شد و واچرِ بدون retry تسلیم شد)
    locker_src = WORK / "locker.py"
    locker_src.write_text(
        "import ctypes, sys, time\n"
        "path, seconds = sys.argv[1], float(sys.argv[2])\n"
        "GENERIC_READ, OPEN_EXISTING, FILE_SHARE_READ = 0x80000000, 3, 1\n"
        "h = ctypes.windll.kernel32.CreateFileW(path, GENERIC_READ, FILE_SHARE_READ,"
        " None, OPEN_EXISTING, 0, None)\n"
        "time.sleep(seconds)\n"
        "ctypes.windll.kernel32.CloseHandle(h)\n",
        encoding="utf-8",
    )
    if os.name == "nt":
        run(["--prepare"])
        locker = subprocess.Popen(
            [sys.executable, "-I", str(locker_src), str(ASAR), "6"],
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        time.sleep(1.5)  # قفل جا بیفتد
        run(["--apply", "--force", "--retries", "10"])
        locker.wait()
        check("apply succeeds after transient lock released (retry path)",
              MARKER in ASAR.read_bytes())
    else:
        print("SKIP: phase 9 needs Windows (real file lock via CreateFileW)")
    locker_src.unlink(missing_ok=True)

    # --- فاز ۱۰: دکتر — بی‌کاری روی پچ‌شده، آماده+اعمال روی بی‌پچ ---
    # (چرخهٔ خودکار پس از آپدیت اپ: همان که --install-task هر ۱۵ دقیقه اجرا می‌کند)
    doctor_log = WORK / "doctor.log"
    r = run(["--doctor", "--force", "--log", str(doctor_log)])
    check("doctor is a no-op on patched asar",
          "از قبل پچ‌شده" in r.stdout and MARKER in ASAR.read_bytes())
    check("doctor left no stray patched file", not patched.is_file())
    run(["--restore", "--force"])
    r = run(["--doctor", "--force", "--log", str(doctor_log)])
    check("doctor prepared and applied on unpatched asar", MARKER in ASAR.read_bytes())
    check("doctor consumed its patched file", not patched.is_file())
    log_text = doctor_log.read_text(encoding="utf-8")
    check("doctor log records the apply",
          "اعمال پچ" in log_text or "پچ اعمال شد" in log_text)
    check("doctor lock cleaned up", not Path(str(ASAR) + ".doctor-lock").is_file())
finally:
    shutil.rmtree(WORK, ignore_errors=True)

print()
if failures:
    print("FAILED:", failures)
    sys.exit(1)
print("ALL FIXTURE TESTS PASSED")

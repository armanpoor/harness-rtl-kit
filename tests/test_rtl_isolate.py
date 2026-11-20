# -*- coding: utf-8 -*-
"""
آزمون‌های ایزوله‌سازی نویسهٔ کنترلی
==================================

اجرای مستقیم:

    python tests/test_rtl_isolate.py

یا با پای‌تست:

    python -m pytest tests/test_rtl_isolate.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from rtl_isolate import PDI, RLI, isolate, is_isolated, undo  # noqa: E402

SAMPLE = "متن فارسی با پرانتز (AFR) و ضریب 0.375.\n"

DOC = (
    "# تیتر آزمایشی\n"
    "\n"
    "پاراگراف فارسی با نام main.py و ضریب 0.375.\n"
    "\n"
    "- آیتم نخست\n"
    "- آیتم دوم\n"
    "\n"
    "| ستون یک | ستون دو |\n"
    "|---|---|\n"
    "| متن فارسی | latin |\n"
    "\n"
    "```bash\n"
    "echo متن فارسی در کد\n"
    "```\n"
    "\n"
    "English only line (AFR) 0.375.\n"
)


def test_paragraph_is_wrapped() -> None:
    result = isolate(SAMPLE)
    assert result.startswith(RLI), "پاراگراف فارسی باید با RLI آغاز شود"
    assert result.rstrip().endswith(PDI), "پاراگراف فارسی باید با PDI پایان یابد"


def test_is_idempotent() -> None:
    once = isolate(DOC)
    assert isolate(once) == once, "ایزوله‌سازی دوباره نباید لایهٔ تکراری بسازد"


def test_check_separates_wrapped_from_bare() -> None:
    assert is_isolated(isolate(DOC)), "سند ایزوله‌شده باید در بررسی قبول شود"
    assert not is_isolated(DOC), "سند خام باید در بررسی رد شود"


def test_markdown_prefixes_stay_outside_isolate() -> None:
    result = isolate("# تیتر\n\n- آیتم\n")
    lines = result.split("\n")
    assert lines[0].startswith("# " + RLI), "نشانهٔ تیتر باید بیرون جفت بماند"
    assert lines[2].startswith("- " + RLI), "نشانهٔ فهرست باید بیرون جفت بماند"


def test_code_fence_is_untouched() -> None:
    source = "```bash\nexport LANG=fa_IR\nمتن فارسی در کد\n```\n"
    assert isolate(source) == source, "بلوک کد هرگز نباید ایزوله شود"


def test_latin_only_line_is_untouched() -> None:
    source = "English only (AFR) 0.375.\n"
    assert isolate(source) == source, "سطر فقط‌لاتین نباید ایزوله شود"


def test_table_cells_are_wrapped_individually() -> None:
    result = isolate("| ستون یک | latin |\n")
    assert result.count(RLI) == 1 and result.count(PDI) == 1, "فقط خانهٔ فارسی بسته می‌شود"


def test_multiline_paragraph_is_one_isolate() -> None:
    result = isolate("خط نخست جمله است و\nخط دوم ادامه‌اش.\n")
    assert result.count(RLI) == 1 and result.count(PDI) == 1, "پاراگراف دوخطی یک جفت می‌خواهد"


def test_undo_restores_original() -> None:
    assert undo(isolate(SAMPLE)) == SAMPLE, "بازگردانی باید متن خام بدهد"


def main() -> int:
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    failures = 0
    for test in tests:
        try:
            test()
            print(f"OK  {test.__name__}")
        except AssertionError as error:
            failures += 1
            print(f"BAD {test.__name__}: {error}")
    print(f"\n{len(tests) - failures} از {len(tests)} آزمون گذشت")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

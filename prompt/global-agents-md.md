# قانون راست‌چین در سطح کاربر — اعمال یک‌جا در همهٔ پروژه‌ها

این فایل همان متنی است که باید در **فایل دستورِ سطح کاربر** بنشیند تا همهٔ
سشن‌های همهٔ پروژه‌ها قانون را بگیرند، نه فقط یک ریپو:

- در ZCode: `~/.zcode/AGENTS.md` (در ویندوز: `C:\Users\<you>\.zcode\AGENTS.md`)
- این فایل پیش از `AGENTS.md` هر پروژه تزریق می‌شود؛ قانون پروژه‌ای می‌تواند آن را تنگ‌تر کند اما نمی‌تواند نادیده‌اش بگیرد.
- سشن‌های از پیش باز، فایل را نمی‌گیرند؛ فقط سشن‌های تازه. برای سشن باز، متن را یک‌بار در همان چت بفرستید.
- اگر هارنس شما جای دیگری برای دستورهای سطح کاربر دارد، همین بدنه را آنجا بگذارید (رایج‌ترین نام‌ها: `CLAUDE.md`، `AGENTS.md` در ریشهٔ خانه).

محتوای آماده — عیناً از سطر بعد کپی کنید و به فایل سطح کاربر بیفزایید:

---

# RTL (Persian) output rule — every reply that contains Persian/Arabic script

Persian text that is not directionally isolated renders scrambled in this
harness: the paragraph base direction stays LTR, so Latin words, numbers,
parentheses and line breaks jump to wrong positions. Raw HTML such as
`<div dir="rtl">` is NOT a fix here — the chat renderer (Streamdown) strips
HTML tags and shows them as literal text.

**The rule:** wrap every block that contains Persian between the invisible
Unicode bidi isolate characters RLI (U+2067) and PDI (U+2069) — `⁧` at the
start of the block, `⁩` at its end:

```text
## ⁧تیتر فارسی⁩
- ⁧آیتم لیست با واژهٔ latin داخلش⁩
**⁧متن بولد⁩**
| ⁧سلول فارسی⁩ | `code` |
⁧پاراگراف معمولی با پرانتز (مثل AFR) و عدد 42.⁩
```

- The pair goes INSIDE the markdown syntax; markers (`##`, `-`, `**`, `|`, `>`) stay outside it.
- NEVER wrap fenced code blocks, inline code, or Latin-only lines — they must stay LTR.
- Do not start a Persian block with a Latin word/number outside the pair; that text goes inside the pair too.
- RLM alone (U+200F) is not sufficient (verified broken). RLE/PDF (U+202B/U+202C) also works; RLI/PDI is preferred because isolates cannot leak direction into surrounding text.
- Applies to: paragraphs, headings, list items, table cells, blockquotes, bold/italic runs, and any single-line Persian answer.

Reference and per-harness details: https://github.com/armanpoor/harness-rtl-kit
(`prompt/zcode-rtl-law.md`, `docs/harnesses.md`).

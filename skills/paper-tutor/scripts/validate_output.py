#!/usr/bin/env python3
from pathlib import Path
import re, sys

REQUIRED = {
    "1_一页结论卡.md": ["一句话读懂", "Research Gap", "核心方法", "核心发现", "最大局限", "阅读建议"],
    "2_精读笔记.md": ["标题", "团队", "研究背景", "研究逻辑链", "结果与讨论", "实验结果", "实验方法", "结论", "现象与机制链", "不足与思考", "可学习的学术表达", "新科学问题"],
}

LOCATOR = re.compile(r"(?:PDF\s*p\.?\s*\d+|Fig\.?\s*\d+|Figure\s*\d+|Table\s*\d+|Section\s*[\d\.]+)", re.I)

def main():
    if len(sys.argv) != 2:
        print("Usage: validate_output.py <output-directory>")
        return 2
    out = Path(sys.argv[1])
    errors = []
    warnings = []
    texts = {}
    for fn, headings in REQUIRED.items():
        p = out/fn
        if not p.exists():
            errors.append(f"Missing file: {fn}")
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        texts[fn] = text
        for h in headings:
            if h not in text:
                errors.append(f"{fn}: missing required section/phrase: {h}")
        if "{{" in text or "}}" in text:
            warnings.append(f"{fn}: unresolved template placeholders remain")

    joined = "\n".join(texts.values())
    locs = LOCATOR.findall(joined)
    if len(locs) < 3:
        warnings.append("Very few source locators detected; verify that major claims are traceable to the PDF.")
    for label in ["[原文事实]", "[作者解释]"]:
        if label not in joined:
            warnings.append(f"Source-layer label not detected: {label}")

    print("=== paper-tutor structure validation ===")
    if errors:
        print("ERRORS:")
        for x in errors: print("-", x)
    if warnings:
        print("WARNINGS:")
        for x in warnings: print("-", x)
    if not errors and not warnings:
        print("PASS: structure and basic traceability checks passed.")
    elif not errors:
        print("PASS WITH WARNINGS: manually review warnings before delivery.")
    return 1 if errors else 0

if __name__ == "__main__":
    raise SystemExit(main())

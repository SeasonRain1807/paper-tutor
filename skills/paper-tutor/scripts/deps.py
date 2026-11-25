#!/usr/bin/env python3
"""Check — and if asked, install once — the optional Python dependencies.

Why this exists: the bundled DSH Python ships numpy/pandas/python-docx/
python-pptx/openpyxl/Pillow/lxml/XlsxWriter but **not** PyMuPDF or pypdf, so a
paper run that needs them has to install them. Installed ad hoc, that turns into
a fresh 20 MB download for every new paper directory (pip install --target
.pylibs). This script makes the one-time install explicit, idempotent, and always
targeted at *the interpreter that is actually running it* — the only place that
persists across sessions.

Usage:
    python deps.py              # 检查（默认）
    python deps.py --check      # 同上：缺什么就报什么，缺项时退出码 1
    python deps.py --install    # 只装缺的那几个，装进当前解释器

退出码：0 = 依赖齐全；1 = 有缺项（--install 后仍缺）；2 = 用法或安装命令出错。
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys

# import 名与 distribution 名不一致的，版本号按 distribution 查
DIST_NAMES = {"fitz": "pymupdf", "PIL": "Pillow", "docx": "python-docx"}

# (分组, 显示名, 用来 import 的模块名, 满足任一即可, pip 安装名)
DEPENDENCIES = [
    ("文本层", "pypdf", ("pypdf",), "pypdf>=5,<7"),
    ("原图", "PyMuPDF", ("fitz", "pymupdf"), "pymupdf>=1.24,<2"),
    ("原图", "Pillow", ("PIL",), "pillow"),
    ("HTML", "lxml", ("lxml",), "lxml"),
    ("DOCX", "python-docx", ("docx",), "python-docx"),
]


def installed_version(modules: tuple[str, ...]) -> str | None:
    for name in modules:
        try:
            spec = importlib.util.find_spec(name)
        except (ImportError, ValueError):
            continue
        if spec is None:
            continue
        try:
            from importlib.metadata import version

            return version(DIST_NAMES.get(name, name))
        except Exception:  # noqa: BLE001 - 版本号只是显示用
            return "已安装"
    return None


def force_utf8_stdout() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            pass


def collect() -> list[tuple[str, str, str | None, str]]:
    return [
        (group, label, installed_version(modules), spec)
        for group, label, modules, spec in DEPENDENCIES
    ]


def report(rows: list[tuple[str, str, str | None, str]]) -> bool:
    force_utf8_stdout()
    print("解释器：" + sys.executable)
    print("Python  ：" + sys.version.split()[0])
    missing: list[str] = []
    for group, label, found, spec in rows:
        state = "✅ " + found if found else "❌ 缺"
        print("  " + group + "：" + label + " " + state)
        if not found:
            missing.append(spec)
    if not missing:
        print("依赖齐全，不需要装任何东西。")
        return True
    print("缺失 " + str(len(missing)) + " 项。一次装好（装进上面这个解释器，之后所有会话、所有论文目录都不用再装）：")
    print('    "' + sys.executable + '" -m pip install ' + " ".join('"' + s + '"' for s in missing))
    print("不要用 --target .pylibs 之类按目录安装：那样每换一个论文目录就要重新下一遍。")
    print("装完再跑一次 python deps.py 复核。")
    return False


def main(argv: list[str]) -> int:
    force_utf8_stdout()
    if "-h" in argv or "--help" in argv:
        print(__doc__.strip())
        return 0
    args = list(argv)
    unknown = [a for a in args if a not in ("--check", "--install")]
    if unknown:
        print("无法识别的参数：" + " ".join(unknown) + "（用 --help 看用法）", file=sys.stderr)
        return 2
    install = "--install" in args

    rows = collect()
    ok = report(rows)
    if ok or not install:
        return 0 if ok else 1

    specs = [spec for (_, _, found, spec) in rows if not found]
    print()
    print("正在安装到当前解释器（装一次即可，会进入它的 site-packages）……")
    command = [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", *specs]
    result = subprocess.run(command, check=False)
    if result.returncode != 0:
        print("安装失败。常见原因：没有网络、PyPI 访问慢或代理未配置。", file=sys.stderr)
        print("可以手动执行：\n  " + " ".join(command), file=sys.stderr)
        return 2

    print()
    return 0 if report(collect()) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

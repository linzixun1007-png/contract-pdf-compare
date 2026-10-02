# SPDX-License-Identifier: AGPL-3.0-only
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
compare.py —— 合同 PDF 对比工具 · 命令行入口

用法：
    python compare.py 内部定稿.pdf 医院水印版.pdf
    python compare.py 内部定稿.pdf 医院水印版.pdf -H 某某医院 -o report.html
    python compare.py a.pdf b.pdf -H 医院A -H 医院B      # 多个医院名

最简用法（连医院名都不给也行）：
    python compare.py 内部定稿.pdf 医院水印版.pdf

输出：
    - 终端打印结论与差异清单（对非技术用户友好）
    - 生成 HTML 可视化对比页，并尝试自动用浏览器打开
"""
from __future__ import annotations
import argparse
import os
import sys
import traceback
import webbrowser
from pathlib import Path

from pdf_compare import compare_pdfs
from report_html import render_report


# ---------------------------------------------------------------------------
# 彩色输出（Windows 10+ 需开启 ANSI；失败则自动降级为无颜色）
# ---------------------------------------------------------------------------
class C:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    GRAY = "\033[90m"
    BOLD = "\033[1m"
    END = "\033[0m"
    _on = True


def _init_color():
    if os.name == "nt":
        try:
            import ctypes
            k = ctypes.windll.kernel32
            k.SetConsoleMode(k.GetStdHandle(-11), 7)  # 开启 ENABLE_VIRTUAL_TERMINAL
        except Exception:
            C._on = False
    elif not sys.stdout.isatty():
        C._on = False


def c(text: str, color: str) -> str:
    return f"{color}{text}{C.END}" if C._on else text


def _safe_console():
    # A GBK Windows terminal must not prevent saving a UTF-8 report when a
    # contract, filename or decorative symbol contains another Unicode glyph.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="backslashreplace")


# ---------------------------------------------------------------------------
# 友好错误提示
# ---------------------------------------------------------------------------
def _fatal(msg: str, hint: str = "", code: int = 1):
    print(c("\n[ 出错 ] ", C.RED) + msg)
    if hint:
        print(c("         " + hint, C.GRAY))
    print()
    sys.exit(code)


def _validate_pdf(path: str, label: str) -> str:
    """校验文件存在、是 PDF、可被打开。"""
    p = os.path.abspath(path)
    if not os.path.exists(p):
        _fatal(f"{label}找不到文件：{path}",
               "请检查路径是否写对，或把文件直接拖进窗口。")
    if os.path.isdir(p):
        _fatal(f"{label}给的是一个文件夹：{path}", "请指定具体的 .pdf 文件。")
    if not p.lower().endswith(".pdf"):
        _fatal(f"{label}不是 PDF 文件：{path}", "本工具只支持 .pdf 格式。")
    if os.path.getsize(p) == 0:
        _fatal(f"{label}文件是空的：{path}", "文件大小为 0，可能复制/下载不完整。")
    return p


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def build_parser():
    ap = argparse.ArgumentParser(
        prog="合同对比",
        description="对比「内部定稿 PDF」与「医院水印版 PDF」的文字层差异，自动忽略水印。",
        epilog="示例：python compare.py 内部.pdf 医院版.pdf -H 某某医院")
    ap.add_argument("a", help="内部定稿 PDF 路径（基准）")
    ap.add_argument("b", help="医院水印版 PDF 路径（待校验）")
    ap.add_argument("-H", "--hospital", action="append", default=[],
                    help="医院名称，可重复指定；用于识别水印文字（可选）")
    ap.add_argument("-o", "--out", default=None,
                    help="HTML 报告输出路径（默认按待校验文件名自动命名）")
    ap.add_argument("--no-open", action="store_true",
                    help="生成报告后不自动打开浏览器")
    ap.add_argument("--profile", choices=["strict", "regular", "relaxed"], default="strict",
                    help="比较档位：strict 严格（默认），regular 常规，relaxed 宽松")
    ap.add_argument("--ignore-regions", help="从 JSON 文件加载用户指定忽略区域（文件不存在或无效则停止）")
    return ap


def main(argv=None):
    _safe_console()
    _init_color()
    args = build_parser().parse_args(argv)

    a = _validate_pdf(args.a, "内部定稿版")
    b = _validate_pdf(args.b, "医院水印版")

    # 默认输出路径：以医院版文件名命名，放在 output/ 下
    if args.out is None:
        stem = os.path.splitext(os.path.basename(b))[0]
        out = os.path.join("output", f"对比报告_{stem}.html")
    else:
        out = args.out

    # 执行对比
    try:
        from ignore_regions import IgnoreConfig
        rules = IgnoreConfig.load(args.ignore_regions) if args.ignore_regions else IgnoreConfig()
        result = compare_pdfs(a, b, hospital_names=args.hospital, profile=args.profile, ignore_config=rules)
    except Exception as e:  # noqa: BLE001
        print(c("\n[ 比对失败 ] ", C.RED) + f"{type(e).__name__}: {e}")
        print(c("若怀疑是文件损坏或加密，请用 PDF 阅读器确认能正常打开、且可以选中复制文字。",
                C.GRAY))
        if os.environ.get("CONTRACT_DIFF_DEBUG"):
            traceback.print_exc()
        print()
        return 1

    # ---- 终端报告 ----
    line = "=" * 68
    print(line)
    print(f"  内部定稿版：{os.path.basename(a)}")
    print(f"  医院水印版：{os.path.basename(b)}")
    print(line)

    if result.stage == "unavailable":
        print(c("  结论：无法完整比较，请人工核对。", C.YELLOW))
        for reason in result.unavailable_reasons:
            print("  " + reason)
    elif result.passed:
        print(c("  结论：本档位未发现文字差异。", C.GREEN))
    else:
        print(c(f"  结论：发现不一致 ✗  共 {len(result.diffs)} 处，请人工复核。", C.RED))

    print(f"  比对阶段：{result.stage}   （{result.message}）")

    wm_b = result.b_watermarks
    if wm_b:
        print(f"  已自动忽略水印：{len(wm_b)} 行")
        # 合并同类，避免刷屏
        seen = {}
        for w in wm_b:
            key = w.text.strip()
            seen[key] = seen.get(key, 0) + 1
        for text, n in seen.items():
            print(c(f"      · {text!r} × {n}", C.GRAY))
    else:
        print(c("  未检出水印文字（可能水印是图片，或不含文字水印）。", C.GRAY))

    if result.diffs:
        print("-" * 68)
        print(f"  差异清单（共 {len(result.diffs)} 处）：")
        for i, d in enumerate(result.diffs, 1):
            if d.kind == "replace":
                print(f"  {i}. " + c("【改写】", C.YELLOW) + f"第 {d.page+1} 页")
                print("       基准 : " + c(d.old, C.RED))
                print("       医院 : " + c(d.new, C.GREEN))
            elif d.kind == "delete":
                print(f"  {i}. " + c("【删除】", C.RED) +
                      f"第 {d.page+1} 页 · 内部版有、医院版无")
                print("       内容 : " + c(d.old, C.RED))
            else:
                print(f"  {i}. " + c("【新增】", C.GREEN) +
                      f"第 {d.page+1} 页 · 医院版有、内部版无")
                print("       内容 : " + c(d.new, C.GREEN))
    print(line)

    # ---- 生成 HTML 报告 ----
    try:
        out_dir = os.path.dirname(os.path.abspath(out))
        os.makedirs(out_dir, exist_ok=True)
        out = render_report(result, out_path=out)
    except Exception as e:  # noqa: BLE001
        print(c(f"\n[ 警告 ] HTML 报告生成失败：{e}", C.YELLOW))
        print("终端结论仍然有效。\n")
        return 1

    out_abs = os.path.abspath(out)
    print(f"  可视化报告：{out_abs}")
    if not args.no_open:
        try:
            webbrowser.open(Path(out_abs).as_uri())
            print(c("  已尝试用默认浏览器打开报告。", C.GRAY))
        except Exception:
            pass
    print()

    return 3 if result.stage == "unavailable" else 0 if result.passed else 2


if __name__ == "__main__":
    sys.exit(main())

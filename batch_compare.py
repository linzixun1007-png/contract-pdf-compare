# SPDX-License-Identifier: AGPL-3.0-only
# -*- coding: utf-8 -*-
"""
batch_compare.py —— 批量对比

适用场景：业务部门一次积压了几十份合同，想一次性过一遍。
把「内部定稿版」和「医院水印版」按文件名配对，批量比对，输出汇总。

约定两种用法：

用法 1（推荐，文件名相同）：两个文件夹，文件名一致即视为一对
    python batch_compare.py --internal ./内部定稿 --hospital ./医院版 --hospital-name 某某医院
    例：内部定稿/HT-001.pdf  <->  医院版/HT-001.pdf

用法 2（一对一清单）：提供 CSV，两列：内部文件路径, 医院文件路径
    python batch_compare.py --list pairs.csv --hospital-name 某某医院

结果：
    - 终端汇总表：每行一份合同 + 结论
    - 每份生成单独 HTML 报告，放在 --out 目录
    - 生成 汇总.csv，可直接用 Excel 打开留痕
退出码：0 = 本档位均未发现差异；1 = 执行或报告保存失败；
        2 = 存在文字差异；3 = 无法完整比较
"""
from __future__ import annotations
import argparse
import csv
import os
import sys

from pdf_compare import compare_pdfs
from report_html import render_report


def find_pairs_by_folder(internal_dir: str, hospital_dir: str):
    pairs = []
    for fn in sorted(os.listdir(internal_dir)):
        if not fn.lower().endswith(".pdf"):
            continue
        a = os.path.join(internal_dir, fn)
        b = os.path.join(hospital_dir, fn)
        pairs.append((a, b if os.path.exists(b) else None, fn))
    return pairs


def find_pairs_by_list(list_path: str):
    pairs = []
    with open(list_path, "r", encoding="utf-8-sig", newline="") as f:
        r = csv.reader(f)
        for row in r:
            if len(row) < 2 or not row[0].strip():
                continue
            a, b = row[0].strip(), row[1].strip()
            if a.lower() in ("内部路径", "a", "internal"):
                continue  # 跳过表头
            pairs.append((a, b if os.path.exists(b) else None, os.path.basename(a)))
    return pairs


def main():
    from compare import _safe_console
    _safe_console()
    ap = argparse.ArgumentParser(description="批量对比内部定稿 PDF 与医院水印版 PDF")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--internal", help="内部定稿版文件夹")
    g.add_argument("--list", help="配对清单 CSV（列：内部路径, 医院路径）")
    ap.add_argument("--hospital", help="医院水印版文件夹（与 --internal 配合，按同名配对）")
    ap.add_argument("--hospital-name", action="append", default=[],
                    help="医院名称，可重复；用于识别水印文字")
    ap.add_argument("--out", default="output/batch", help="批量报告输出目录")
    ap.add_argument("--profile", choices=["strict", "regular", "relaxed"], default="strict")
    ap.add_argument("--ignore-regions", help="用于各文件对的忽略区域 JSON")
    args = ap.parse_args()
    from ignore_regions import IgnoreConfig
    try:
        rules = IgnoreConfig.load(args.ignore_regions) if args.ignore_regions else IgnoreConfig()
    except (OSError, ValueError, KeyError, TypeError) as error:
        ap.error(f"忽略区域规则无效：{error}")

    if args.internal:
        if not args.hospital:
            sys.exit("使用 --internal 时必须同时提供 --hospital 文件夹")
        pairs = find_pairs_by_folder(args.internal, args.hospital)
    else:
        pairs = find_pairs_by_list(args.list)

    if not pairs:
        sys.exit("没有找到任何可对比的文件对。")

    os.makedirs(args.out, exist_ok=True)
    rows = []
    n_pass = n_fail = n_err = n_unknown = 0

    print(f"共 {len(pairs)} 份合同待比对\n")
    print(f"{'合同':<34}{'结论':<10}差异数")
    print("-" * 60)

    for a, b, name in pairs:
        if b is None or not os.path.exists(a):
            n_err += 1
            print(f"{name[:32]:<34}{'缺失文件':<10}-")
            rows.append([name, "缺失文件", "-", "", ""])
            continue
        try:
            r = compare_pdfs(a, b, hospital_names=args.hospital_name, profile=args.profile, ignore_config=rules)
        except Exception as e:  # noqa: BLE001
            n_err += 1
            print(f"{name[:32]:<34}{'读取失败':<10}-")
            rows.append([name, f"读取失败: {e}", "-", "", ""])
            continue

        stem = os.path.splitext(name)[0]
        try:
            render_report(r, out_path=os.path.join(args.out, f"对比报告_{len(rows)+1:04}_{stem}.html"))
        except Exception as error:
            n_err += 1
            rows.append([name, f"报告保存失败: {error}", len(r.diffs), r.stage, r.message])
            continue

        if r.stage == "unavailable":
            n_unknown += 1
        elif r.passed:
            n_pass += 1
        else:
            n_fail += 1
        verdict = "无法完整比较" if r.stage == "unavailable" else "未发现差异" if r.passed else "不一致"
        print(f"{name[:32]:<34}{verdict:<10}{len(r.diffs)}")
        detail = " | ".join(
            f"p{d.page+1}:{d.old or d.new}"[:60] for d in r.diffs[:5])
        rows.append([name, verdict, len(r.diffs), r.stage, detail])

    print("-" * 60)
    print(f"未发现差异 {n_pass} / 不一致 {n_fail} / 无法比较 {n_unknown} / 异常 {n_err}  （共 {len(pairs)}）")

    summary = os.path.join(args.out, "汇总.csv")
    with open(summary, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["合同文件", "结论", "差异数", "比对阶段", "差异摘要"])
        w.writerows(rows)
    print(f"\n汇总清单：{os.path.abspath(summary)}")
    print(f"逐份报告：{os.path.abspath(args.out)}")

    return 1 if n_err else 3 if n_unknown else 2 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())

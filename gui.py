# SPDX-License-Identifier: AGPL-3.0-only
# -*- coding: utf-8 -*-
"""
gui.py —— 图形界面版（Tkinter，Python 自带，无需额外安装）

相比命令行，业务同学更友好：
  - 拖拽或点选两个 PDF
  - 点一下「开始对比」
  - 结果直接弹浏览器
  - 显示进度与结论

打包成 exe：
    pyinstaller -F -w gui.py --name 合同对比 --collect-all fitz --collect-all pymupdf \
        --add-data "pdf_compare.py:." --add-data "report_html.py:."
"""
from __future__ import annotations
import os
import sys
import threading
import traceback
from pathlib import Path
from datetime import datetime
import argparse
import json

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

# 让打包后也能 import 到同目录模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pdf_compare import compare_pdfs, PROFILES, VERSION          # noqa: E402
from report_html import render_report         # noqa: E402


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title(f"合同 PDF 对比工具 {VERSION}")
        root.geometry("850x800")
        root.minsize(790, 740)

        # 顶部说明
        head = tk.Frame(root, bg="#1f2937")
        head.pack(fill="x")
        tk.Label(head, text="合同 PDF 对比工具", bg="#1f2937", fg="white",
                 font=("Microsoft YaHei UI", 16, "bold")).pack(pady=(14, 2))
        tk.Label(head, text="本地比较文字内容 · 可选择比较档位 · 扫描页会提示人工核对",
                 bg="#1f2937", fg="#9ca3af",
                 font=("Microsoft YaHei UI", 10)).pack(pady=(0, 14))

        body = tk.Frame(root, padx=24, pady=16)
        body.pack(fill="both", expand=True)

        self.var_a = tk.StringVar()
        self.var_b = tk.StringVar()
        self.var_h = tk.StringVar()
        self.var_profile = tk.StringVar(value=PROFILES["strict"][0])
        self.var_policy = tk.StringVar(value=PROFILES["strict"][1])
        app_dir = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent
        self.var_out = tk.StringVar(value=str(app_dir / "对比报告"))

        self._file_row(body, "① 内部定稿版（基准）", self.var_a, 0)
        self._file_row(body, "② 医院水印版（待校验）", self.var_b, 1)

        # 医院名
        tk.Label(body, text="③ 医院名称（严格档建议填写；多个名称用逗号分开）",
                 font=("Microsoft YaHei UI", 10), anchor="w").grid(
            row=4, column=0, columnspan=3, sticky="w", pady=(12, 4))
        tk.Entry(body, textvariable=self.var_h, font=("Microsoft YaHei UI", 10)).grid(
            row=5, column=0, columnspan=3, sticky="ew", ipady=5)
        tk.Label(body, text="④ 比较严格程度", anchor="w",
                 font=("Microsoft YaHei UI", 10)).grid(row=6, column=0, sticky="w", pady=(12, 4))
        profile_box = ttk.Combobox(body, textvariable=self.var_profile, state="readonly",
                                   values=[value[0] for value in PROFILES.values()])
        profile_box.grid(row=7, column=0, columnspan=3, sticky="ew", ipady=3)
        profile_box.bind("<<ComboboxSelected>>", self._profile_changed)
        tk.Label(body, textvariable=self.var_policy, wraplength=730, justify="left",
                 fg="#475569", anchor="w").grid(row=8, column=0, columnspan=3, sticky="w", pady=(4, 8))
        tk.Label(body, text="⑤ 报告保存文件夹", anchor="w").grid(row=9, column=0, sticky="w")
        tk.Entry(body, textvariable=self.var_out).grid(row=10, column=0, columnspan=2, sticky="ew", ipady=4)
        tk.Button(body, text="选择文件夹…", command=self.pick_output).grid(row=10, column=2, padx=(8, 0))

        body.columnconfigure(0, weight=1)

        # 按钮
        btns = tk.Frame(root, padx=24)
        btns.pack(fill="x", pady=6)
        self.about_button = tk.Button(btns, text="关于与开源许可", command=self.show_license)
        self.about_button.pack(side="left")
        self.btn = tk.Button(btns, text="开始对比", command=self.start,
                             bg="#2563eb", fg="white", activebackground="#1d4ed8",
                             font=("Microsoft YaHei UI", 12, "bold"),
                             relief="flat", padx=28, pady=10, cursor="hand2")
        self.btn.pack(side="right")

        # 进度条
        self.pb = ttk.Progressbar(root, mode="indeterminate")

        # 结果区
        self.log = tk.Text(root, height=9, font=("Microsoft YaHei UI", 10),
                           bg="#0f172a", fg="#e5e7eb", relief="flat",
                           padx=12, pady=10, wrap="word")
        self.log.pack(fill="both", expand=True, padx=24, pady=(6, 18))
        self._log("等待选择文件……\n")

    def show_license(self):
        messagebox.showinfo("关于与开源许可",
            f"合同 PDF 对比工具 {VERSION}\n\n"
            "本程序按 GNU AGPL v3 发布，可在许可证条件下使用、修改与分发。\n"
            "程序不提供任何担保；比较结果仍需结合合同原件复核。\n\n"
            "源码与许可证：\n"
            "https://github.com/linzixun1007-png/contract-pdf-compare\n\n"
            "第三方组件的独立许可见发布包的 LICENSE、THIRD_PARTY_NOTICES.md 和 licenses 文件夹。",
            parent=self.root)

    def _file_row(self, parent, label, var, r):
        tk.Label(parent, text=label, font=("Microsoft YaHei UI", 10),
                 anchor="w").grid(row=r * 2, column=0, columnspan=3,
                                  sticky="w", pady=(8, 4))
        tk.Entry(parent, textvariable=var, font=("Microsoft YaHei UI", 10)).grid(
            row=r * 2 + 1, column=0, columnspan=2, sticky="ew", ipady=5)
        tk.Button(parent, text="选择文件…",
                  command=lambda v=var: self.pick(v),
                  font=("Microsoft YaHei UI", 9), relief="flat",
                  bg="#e5e7eb", padx=12, cursor="hand2").grid(
            row=r * 2 + 1, column=2, padx=(8, 0))
        parent.columnconfigure(1, weight=1)

    def pick(self, var):
        f = filedialog.askopenfilename(
            title="选择 PDF 文件",
            filetypes=[("PDF 文件", "*.pdf"), ("所有文件", "*.*")])
        if f:
            var.set(f)

    def profile_key(self):
        return next(key for key, value in PROFILES.items() if value[0] == self.var_profile.get())

    def _profile_changed(self, event=None):
        self.var_policy.set(PROFILES[self.profile_key()][1])

    def pick_output(self):
        folder = filedialog.askdirectory(title="选择报告保存文件夹")
        if folder:
            self.var_out.set(folder)

    def _log(self, text):
        self.log.insert("end", text)
        self.log.see("end")

    def start(self):
        a, b = self.var_a.get().strip(), self.var_b.get().strip()
        if not a or not b:
            messagebox.showwarning("提示", "请先选择两个 PDF 文件。")
            return
        for p in (a, b):
            if not os.path.exists(p):
                messagebox.showerror("文件不存在", p)
                return
        if Path(a).resolve() == Path(b).resolve():
            messagebox.showwarning("选择了同一文件", "两个位置选择的是同一份文件，请确认基准和待校验文件。")
            return
        if not self.var_out.get().strip():
            messagebox.showwarning("提示", "请选择报告保存文件夹。")
            return
        names = [x.strip() for x in self.var_h.get().replace("，", ",").split(",") if x.strip()]
        profile, folder = self.profile_key(), self.var_out.get().strip()
        self.btn.config(state="disabled")
        self.log.delete("1.0", "end")
        self.pb.pack(fill="x", padx=24, pady=(0, 6))
        self.pb.start(12)
        threading.Thread(target=self._run, args=(a, b, names, profile, folder), daemon=True).start()

    def _run(self, a, b, names, profile, folder):
        try:
            self.root.after(0, self._log, "正在提取文字层……\n")
            result = compare_pdfs(a, b, hospital_names=names, profile=profile)

            self.root.after(0, self._log, "正在生成报告……\n")
            Path(folder).mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            out = str(Path(folder) / f"对比报告_{Path(b).stem}_{stamp}.html")
            out = render_report(result, out_path=out)

            # 展示结论
            self.root.after(0, self._show, result, out)
        except Exception as e:  # noqa: BLE001
            err = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
            self.root.after(0, self._fail, err)

    def _show(self, result, out):
        self.pb.stop()
        self.pb.pack_forget()
        self.btn.config(state="normal")

        self._log(f"比较档位：{PROFILES[result.profile][0]}\n")
        if result.stage == "unavailable":
            self._log("⚠ 无法完整比较，请人工核对：\n")
            for reason in result.unavailable_reasons:
                self._log("  " + reason + "\n")
        elif result.passed:
            self._log("✓ 本档位未发现文字差异。请留意报告中的比较范围。\n")
        else:
            self._log(f"❌ 发现 {len(result.diffs)} 处不一致，请人工复核：\n\n")
            for i, d in enumerate(result.diffs, 1):
                if d.kind == "replace":
                    self._log(f"{i}. 【改写】第{d.page+1}页\n")
                    self._log(f"   基准：{d.old}\n")
                    self._log(f"   医院：{d.new}\n\n")
                elif d.kind == "delete":
                    self._log(f"{i}. 【删除】第{d.page+1}页（内部版有、医院版无）\n")
                    self._log(f"   内容：{d.old}\n\n")
                else:
                    self._log(f"{i}. 【新增】第{d.page+1}页（医院版有、内部版无）\n")
                    self._log(f"   内容：{d.new}\n\n")
        self._log(f"水印已忽略：{len(result.b_watermarks)} 行\n")
        for warning in result.warnings:
            self._log(warning + "\n")
        self._log(f"\n报告已生成：{out}\n")

        import webbrowser
        try:
            webbrowser.open(Path(out).resolve().as_uri())
        except Exception:
            pass

    def _fail(self, err):
        self.pb.stop()
        self.pb.pack_forget()
        self.btn.config(state="normal")
        self._log("比对失败：\n" + err)
        messagebox.showerror("出错", "比对失败，详见下方信息。")


def main():
    parser = argparse.ArgumentParser(description="合同 PDF 对比工具")
    parser.add_argument("--self-test", action="store_true", help="运行内置功能验收，不打开窗口")
    parser.add_argument("--result", help="验收结果 JSON 的保存路径")
    parser.add_argument("--gui-check", action="store_true", help="检查三个档位及界面组件后退出")
    args = parser.parse_args()
    if args.self_test:
        from self_test import run_self_test
        result = run_self_test()
        if args.result:
            Path(args.result).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return 0 if result["passed"] else 1
    root = tk.Tk()
    if args.gui_check:
        root.withdraw()
        app = App(root)
        assert app.about_button.cget("text") == "关于与开源许可"
        for value in PROFILES.values():
            app.var_profile.set(value[0])
            app._profile_changed()
            assert app.var_policy.get() == value[1]
        root.update_idletasks()
        root.destroy()
        if args.result:
            Path(args.result).write_text(json.dumps({"passed": True, "profiles": list(PROFILES),
                                                     "version": VERSION}), encoding="utf-8")
        return 0
    App(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())

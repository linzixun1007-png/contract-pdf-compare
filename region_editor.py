# SPDX-License-Identifier: AGPL-3.0-only
"""Local PDF preview and rectangle editor; no cloud or extra GUI dependency."""
from __future__ import annotations
import base64
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from ignore_regions import IgnoreConfig, IgnoreRegion, margin_preset, parse_pages
from pdf_compare import fitz

class RegionEditor:
    def __init__(self, parent, a_path, b_path, config, on_apply):
        self.parent, self.on_apply = parent, on_apply
        self.config = IgnoreConfig(list(config.regions))
        self.docs, self.canvases, self.images, self.frames = {}, {}, {}, {}
        self.page_vars, self.page_sizes = {}, {}
        self.resize_tasks = {}
        self.drag = None
        self.closed = False
        try:
            for side, path in (("A", a_path), ("B", b_path)):
                self.docs[side] = fitz.open(path)
            if any(d.needs_pass or not len(d) for d in self.docs.values()):
                raise ValueError("预览需要可直接打开且包含页面的 PDF")
        except Exception:
            for doc in self.docs.values(): doc.close()
            raise
        self.window = tk.Toplevel(parent)
        self.window.title("用户指定忽略区域 · 拖动框选")
        width = min(1280, max(1000, parent.winfo_screenwidth()-100))
        height = min(900, max(740, parent.winfo_screenheight()-100))
        self.window.geometry(f"{width}x{height}")
        self.window.minsize(900, 680)
        self.window.transient(parent)
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.window.grab_set()
        self.name = tk.StringVar(value="自定义区域")
        self.side = tk.StringVar(value="两份文件")
        self.scope = tk.StringVar(value="全部页")
        self.pages = tk.StringVar()
        self.info = tk.StringVar(value="尚未设置区域。拖动页面框选；黄色框内完全包含的字符不参与比较。")
        controls = tk.Frame(self.window, padx=12, pady=8)
        controls.pack(fill="x")
        tk.Label(controls, text="区域名称").grid(row=0, column=0)
        tk.Entry(controls, textvariable=self.name, width=16).grid(row=0, column=1, padx=4)
        ttk.Combobox(controls, textvariable=self.side, state="readonly", width=11,
                     values=["两份文件", "仅 A", "仅 B"]).grid(row=0, column=2, padx=4)
        ttk.Combobox(controls, textvariable=self.scope, state="readonly", width=9,
                     values=["全部页", "当前页", "指定页"]).grid(row=0, column=3, padx=4)
        tk.Entry(controls, textvariable=self.pages, width=14).grid(row=0, column=4, padx=4)
        tk.Label(controls, text="指定页示例：1,3-5").grid(row=0, column=5, padx=4)
        actions = tk.Frame(self.window, padx=12)
        actions.pack(fill="x")
        for label, command in (("页眉 / 页脚预设", self.add_margins), ("导入规则", self.load),
                               ("导出规则", self.save), ("删除选中", self.remove_selected),
                               ("清空区域", self.clear)):
            tk.Button(actions, text=label, command=command).pack(side="left", padx=(0, 6), pady=3)
        tk.Label(self.window, text="预设为页顶 10% 和页底 8%，请翻页检查是否覆盖正文。两份文件可单独设置，页码按 PDF 实际页序。",
                 anchor="w", padx=12, fg="#92400e").pack(fill="x", pady=4)
        preview = tk.Frame(self.window, padx=10)
        preview.pack(fill="both", expand=True)
        for column, side in enumerate(("A", "B")):
            holder = tk.Frame(preview)
            holder.grid(row=0, column=column, sticky="nsew", padx=3)
            preview.columnconfigure(column, weight=1)
            bar = tk.Frame(holder)
            bar.pack(fill="x")
            tk.Label(bar, text=f"{side}（{'基准' if side=='A' else '待校验'}）").pack(side="left")
            var = tk.IntVar(value=1)
            self.page_vars[side] = var
            tk.Button(bar, text="上一页", command=lambda s=side:self.turn(s,-1)).pack(side="left", padx=4)
            spin = tk.Spinbox(bar, from_=1, to=len(self.docs[side]), width=5, textvariable=var,
                             command=lambda s=side:self.render(s))
            spin.pack(side="left")
            spin.bind("<Return>", lambda e,s=side:self.render(s))
            tk.Label(bar, text=f"/ {len(self.docs[side])}").pack(side="left")
            tk.Button(bar, text="下一页", command=lambda s=side:self.turn(s,1)).pack(side="left", padx=4)
            canvas = tk.Canvas(holder, bg="#e5e7eb", highlightthickness=0, cursor="crosshair")
            canvas.pack(fill="both", expand=True)
            self.canvases[side] = canvas
            canvas.bind("<ButtonPress-1>", lambda e,s=side:self.begin_drag(s,e))
            canvas.bind("<B1-Motion>", lambda e,s=side:self.move_drag(s,e))
            canvas.bind("<ButtonRelease-1>", lambda e,s=side:self.end_drag(s,e))
            canvas.bind("<Configure>", lambda e,s=side:self.schedule_render(s))
        preview.rowconfigure(0, weight=1)
        self.listbox = tk.Listbox(self.window, height=4, exportselection=False)
        self.listbox.pack(fill="x", padx=12, pady=(6, 2))
        tk.Label(self.window, textvariable=self.info, anchor="w", padx=12, fg="#334155").pack(fill="x")
        bottom = tk.Frame(self.window, padx=12, pady=8)
        bottom.pack(fill="x")
        tk.Button(bottom, text="取消", command=self.close).pack(side="right", padx=6)
        tk.Button(bottom, text="使用这些规则", command=self.apply, bg="#2563eb", fg="white").pack(side="right")
        self.window.update_idletasks()
        self.refresh()

    def schedule_render(self, side):
        if self.closed or self.drag: return
        if side in self.resize_tasks:
            self.window.after_cancel(self.resize_tasks[side])
        self.resize_tasks[side] = self.window.after(120, lambda:self.render(side))

    def turn(self, side, delta):
        try:
            page = self.page_vars[side].get()
        except tk.TclError:
            page = 1
        self.page_vars[side].set(max(1, min(len(self.docs[side]), page+delta)))
        self.render(side)

    def render(self, side):
        if self.closed: return
        try:
            number = self.page_vars[side].get()
            if not 1 <= number <= len(self.docs[side]): raise ValueError("页码超出范围")
            page = self.docs[side][number-1]
            canvas = self.canvases[side]
            width, height = max(300, canvas.winfo_width()), max(300, canvas.winfo_height())
            scale = min((width-16)/page.rect.width, (height-16)/page.rect.height)
            pix = page.get_pixmap(matrix=fitz.Matrix(scale,scale), alpha=False)
            photo = tk.PhotoImage(data=base64.b64encode(pix.tobytes("png")).decode("ascii"))
            self.images[side] = photo
            x, y = (width-pix.width)//2, (height-pix.height)//2
            self.frames[side] = (x, y, pix.width, pix.height)
            self.page_sizes[side] = (page.rect.width, page.rect.height)
            canvas.delete("all")
            canvas.create_image(x, y, image=photo, anchor="nw", tags="page")
            for region in self.config.matching(side, number-1):
                x0,y0,x1,y1 = region.rect
                canvas.create_rectangle(x+x0*pix.width,y+y0*pix.height,x+x1*pix.width,y+y1*pix.height,
                                        outline="#b45309", width=2, fill="#facc15", stipple="gray25", tags="mask")
                canvas.create_text(x+x0*pix.width+3,y+y0*pix.height+3,text=region.name,anchor="nw",
                                   fill="#78350f", tags="mask")
        except (ValueError, tk.TclError) as error:
            self.info.set(f"预览：{error}")

    def fraction(self, side, x, y):
        px,py,width,height = self.frames[side]
        return max(0,min(1,(x-px)/width)), max(0,min(1,(y-py)/height))

    def begin_drag(self, side, event):
        px,py,width,height = self.frames[side]
        if not (px <= event.x <= px+width and py <= event.y <= py+height): return
        self.drag = (side, *self.fraction(side,event.x,event.y))
        self.canvases[side].delete("selection")

    def move_drag(self, side, event):
        if not self.drag or self.drag[0] != side: return
        _, x0, y0 = self.drag
        x1,y1 = self.fraction(side,event.x,event.y)
        px,py,width,height = self.frames[side]
        canvas = self.canvases[side]
        canvas.delete("selection")
        canvas.create_rectangle(px+x0*width,py+y0*height,px+x1*width,py+y1*height,
                                outline="#2563eb",width=2,tags="selection")

    def end_drag(self, side, event):
        if not self.drag or self.drag[0] != side: return
        _, x0, y0 = self.drag
        self.drag = None
        x1,y1 = self.fraction(side,event.x,event.y)
        self.canvases[side].delete("selection")
        x0,x1 = sorted((x0,x1)); y0,y1 = sorted((y0,y1))
        if (x1-x0)*self.frames[side][2]<3 or (y1-y0)*self.frames[side][3]<3: return
        try:
            applies = {"两份文件":"both","仅 A":"A","仅 B":"B"}[self.side.get()]
            pages = (() if self.scope.get()=="全部页" else
                     (self.page_vars[side].get(),) if self.scope.get()=="当前页" else parse_pages(self.pages.get()))
            if self.scope.get()=="指定页" and not pages: raise ValueError("请填写指定页码")
            region = IgnoreRegion(self.name.get().strip() or f"区域{len(self.config.regions)+1}",
                                  (x0,y0,x1,y1), applies, pages)
            updated = IgnoreConfig(self.config.regions + [region])
            updated.validate_pages({s:len(d) for s,d in self.docs.items()})
            self.config = updated
            self.refresh()
        except (ValueError, KeyError) as error:
            messagebox.showerror("无法添加区域", str(error), parent=self.window)

    def refresh(self):
        self.listbox.delete(0, "end")
        for region in self.config.regions:
            page_label = ",".join(map(str,region.pages)) if region.pages else "全部页"
            self.listbox.insert("end", f"{region.name} | {region.side} | {page_label} | "
                                + ", ".join(f"{n*100:.1f}%" for n in region.rect))
        self.info.set(f"已设置 {len(self.config.regions)} 个区域。结论只覆盖框外文字；框内文字会列在报告中。")
        for side in self.docs: self.render(side)

    def add_margins(self):
        side = {"两份文件":"both","仅 A":"A","仅 B":"B"}[self.side.get()]
        self.config.regions.extend(margin_preset(side=side).regions)
        self.refresh()

    def remove_selected(self):
        for index in reversed(self.listbox.curselection()):
            del self.config.regions[index]
        self.refresh()

    def clear(self):
        self.config = IgnoreConfig()
        self.refresh()

    def load(self):
        path = filedialog.askopenfilename(parent=self.window, filetypes=[("区域规则 JSON","*.json")])
        if not path: return
        try:
            config = IgnoreConfig.load(path)
            config.validate_pages({s:len(d) for s,d in self.docs.items()})
            self.config = config
            self.refresh()
        except (OSError, ValueError, KeyError, TypeError) as error:
            messagebox.showerror("导入失败",str(error),parent=self.window)

    def save(self):
        path = filedialog.asksaveasfilename(parent=self.window, defaultextension=".json",
                                          filetypes=[("区域规则 JSON","*.json")],initialfile="忽略区域.json")
        if path:
            try: self.config.save(path)
            except OSError as error: messagebox.showerror("导出失败",str(error),parent=self.window)

    def apply(self):
        try:
            self.config.validate_pages({s:len(d) for s,d in self.docs.items()})
            self.on_apply(IgnoreConfig(list(self.config.regions)))
            self.close()
        except ValueError as error:
            messagebox.showerror("规则无效",str(error),parent=self.window)

    def close(self):
        if self.closed: return
        self.closed = True
        for task in self.resize_tasks.values():
            self.window.after_cancel(task)
        for doc in self.docs.values(): doc.close()
        self.window.destroy()

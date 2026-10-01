# SPDX-License-Identifier: AGPL-3.0-only
# -*- coding: utf-8 -*-
"""
make_samples2.py —— 第二批测试样例：表格 / 二维码 / 图片水印

覆盖真实合同里最容易出问题的形态：
  T1. 设备清单表（多行多列，含数字与型号）
  T2. 价款明细表（金额、税额、合计）
  T3. 表格版改数字（表格里一个数量从 3 改成 5）—— 应定位
  T4. 表格版行序重排（同样内容，行顺序不同）—— 应报告行序变化
  Q1. 右上角真实二维码（二维码本身不含文字层，但要确认不干扰）
  Q2. 右上角医院名以「图片」形式嵌入 —— 确认不进文字层
  Q3. 二维码图片里藏有文字对象（极端情况）

用 PyMuPDF 生成，中文用内嵌 Noto Sans CJK SC。
"""
from __future__ import annotations
import os
import fitz

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLES = os.path.join(HERE, "samples")
FONT_PATH = os.path.join(HERE, "NotoSansCJKsc.otf")
os.makedirs(SAMPLES, exist_ok=True)


def _ensure_font():
    """同 make_samples.py：优先用子集化小字体，减小样例体积。"""
    if os.path.exists(FONT_PATH):
        return
    subset = os.path.join(HERE, "打包", "fonts", "sample-subset.ttf")
    if os.path.exists(subset):
        import shutil
        shutil.copy(subset, FONT_PATH)
        return
    from fontTools.ttLib import TTCollection
    coll = TTCollection("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")
    coll.fonts[2].save(FONT_PATH)


_ensure_font()

PAGE_W, PAGE_H = fitz.paper_size("a4")
HOSPITAL = "某某医院"


def txt(page, x, y, s, size=10.5, color=(0, 0, 0)):
    page.insert_text((x, y), s, fontsize=size, fontname="cjk",
                     fontfile=FONT_PATH, color=color)


def center(page, y, s, size=16, color=(0, 0, 0)):
    est = sum(size if ord(c) > 127 else size * 0.5 for c in s)
    txt(page, (PAGE_W - est) / 2, y, s, size=size, color=color)


def grid(page, x, y, col_widths, row_h=24):
    """画表格网格线，返回每行的 y 坐标列表。"""
    total_w = sum(col_widths)
    shape = page.new_shape()
    # 横线
    for i in range(len(col_widths) + 1):
        yy = y + i * row_h
        shape.draw_line(fitz.Point(x, yy), fitz.Point(x + total_w, yy))
    # 竖线
    cx = x
    shape.draw_line(fitz.Point(cx, y), fitz.Point(cx, y + row_h * (len(col_widths) + 1)))
    for w in col_widths:
        cx += w
        shape.draw_line(fitz.Point(cx, y), fitz.Point(cx, y + row_h * (len(col_widths) + 1)))
    shape.finish(color=(0.4, 0.4, 0.4), width=0.6)
    shape.commit()


def table(page, x, y, headers, rows, col_widths, row_h=24, size=9.5):
    """绘制一个简单表格：表头 + 数据行，每格内容居中偏左。"""
    grid(page, x, y, col_widths, row_h)
    # 表头
    cy = y + row_h - 8
    cx = x
    for h, w in zip(headers, col_widths):
        txt(page, cx + 6, cy, h, size=size)
        cx += w
    # 数据
    for r, row in enumerate(rows, 1):
        cy = y + r * row_h + row_h - 8
        cx = x
        for cell, w in zip(row, col_widths):
            txt(page, cx + 6, cy, str(cell), size=size)
            cx += w
    return y + (len(rows) + 1) * row_h


def qr_image_matrix(text, size=33):
    """
    生成一个"看起来像二维码"的位图（纯像素矩阵，用于嵌入成图片）。
    不依赖 qrcode 库；只要能被当作图片对象嵌入即可。
    返回 (pixmap_bytes, w, h)。
    """
    import random
    random.seed(hash(text) & 0xffff)
    n = size
    # 生成 0/1 矩阵
    grid_m = [[0] * n for _ in range(n)]

    def finder(r0, c0):
        for i in range(7):
            for j in range(7):
                on = (i in (0, 6) or j in (0, 6) or (2 <= i <= 4 and 2 <= j <= 4))
                grid_m[r0 + i][c0 + j] = 1 if on else 0

    finder(0, 0); finder(0, n - 7); finder(n - 7, 0)
    for i in range(n):
        for j in range(n):
            if grid_m[i][j] == 0 and random.random() > 0.5:
                grid_m[i][j] = 1

    # 转成 pixmap（RGB）
    scale = 4
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, n * scale, n * scale))
    pix.set_rect(pix.irect, (255, 255, 255))
    for i in range(n):
        for j in range(n):
            if grid_m[i][j]:
                for di in range(scale):
                    for dj in range(scale):
                        pix.set_pixel(j * scale + dj, i * scale + di, (0, 0, 0))
    return pix


def insert_qr(page, x, y, text, box=52):
    pix = qr_image_matrix(text)
    rect = fitz.Rect(x, y, x + box, y + box)
    page.insert_image(rect, pixmap=pix)


def hospital_name_as_image(page, x, y, name):
    """把医院名渲染成一张图片再贴上去（模拟"医院名是图片水印"）。"""
    # 先画到临时页，再截取为图片
    tmp = fitz.open()
    tp = tmp.new_page(width=200, height=40)
    tp.insert_text((6, 28), name, fontsize=16, fontname="cjk", fontfile=FONT_PATH,
                   color=(0.45, 0.45, 0.45))
    mat = fitz.Matrix(3, 3)
    pix = tp.get_pixmap(matrix=mat)
    tmp.close()
    page.insert_image(fitz.Rect(x, y, x + 200, y + 40), pixmap=pix)


# ---------------------------------------------------------------------------
# 表格样例内容
# ---------------------------------------------------------------------------
TABLE_HEADERS = ["序号", "设备名称", "型号", "单位", "数量", "单价(元)", "金额(元)"]
TABLE_ROWS = [
    ["1", "彩色多普勒超声诊断仪", "XQ-800", "台", "3", "250000.00", "750000.00"],
    ["2", "便携式监护仪", "PM-200", "台", "10", "18000.00", "180000.00"],
    ["3", "输液泵", "IP-50", "台", "20", "4500.00", "90000.00"],
    ["4", "除颤监护仪", "DF-300", "台", "2", "68000.00", "136000.00"],
    ["5", "心电图机", "ECG-12", "台", "4", "22000.00", "88000.00"],
]
TABLE_WIDTHS = [40, 130, 70, 40, 40, 80, 85]
TABLE_TOTAL = ["合计", "", "", "", "", "", "1,244,000.00"]


def make_table_doc(path, rows=None, headers=None, total=None,
                   extra_shift=0, wm_text=None, wm_qr=False,
                   wm_name_image=False, wm_name_text=False):
    rows = rows if rows is not None else TABLE_ROWS
    headers = headers or TABLE_HEADERS
    total = total if total is not None else TABLE_TOTAL

    doc = fitz.open()
    p = doc.new_page(width=PAGE_W, height=PAGE_H)

    # 背景文字水印
    if wm_text:
        mat = fitz.Matrix(1, 1).prerotate(45)
        p.insert_text((170, 480), wm_text, fontsize=42, fontname="cjk",
                      fontfile=FONT_PATH, color=(0.85, 0.85, 0.85),
                      morph=(fitz.Point(170, 480), mat), overlay=False)

    center(p, 70, "医疗设备采购合同", size=16)
    txt(p, 60, 100, "合同编号：HT-2026-0912", size=10.5)
    txt(p, 60, 122, f"甲方（采购方）：{HOSPITAL}", size=10.5)
    txt(p, 60, 144, "乙方（供应方）：某某医疗科技有限公司", size=10.5)
    txt(p, 60, 176, "第一条 设备清单及价款", size=11)

    y_end = table(p, 60, 190 + extra_shift, headers, rows, TABLE_WIDTHS)
    # 合计行
    txt(p, 60 + 6, y_end + 16, total[0], size=9.5)
    txt(p, 60 + sum(TABLE_WIDTHS) - 85 + 6, y_end + 16, total[-1], size=9.5)

    txt(p, 60, y_end + 60, "第二条 上述价款已包含运输、安装及调试费用。", size=10.5)
    txt(p, 60, y_end + 82, "第三条 乙方应于合同生效之日起 45 日内完成交付。", size=10.5)

    # ---- 右上角水印 ----
    if wm_qr:
        insert_qr(p, PAGE_W - 78, 24, "HT-2026-0912")
    if wm_name_text:
        txt(p, PAGE_W - 150, 92, HOSPITAL, size=9, color=(0.5, 0.5, 0.5))
    if wm_name_image:
        hospital_name_as_image(p, PAGE_W - 190, 60, HOSPITAL)

    doc.save(path)
    doc.close()
    return path


def main():
    # 基准：纯表格，无水印
    make_table_doc(os.path.join(SAMPLES, "table_base.pdf"))
    # T3：表格里数量 3 改成 5，单价也改一个
    rows_mod = [r[:] for r in TABLE_ROWS]
    rows_mod[0][4] = "5"
    rows_mod[0][6] = "1,250,000.00"
    make_table_doc(os.path.join(SAMPLES, "table_num_changed.pdf"),
                   rows=rows_mod, total=["合计", "", "", "", "", "", "1,744,000.00"])
    # T4：行序重排（内容相同，只是行顺序不同）—— 期望：这个应当被视为差异还是通过？
    rows_reorder = [TABLE_ROWS[2], TABLE_ROWS[0], TABLE_ROWS[4],
                    TABLE_ROWS[1], TABLE_ROWS[3]]
    make_table_doc(os.path.join(SAMPLES, "table_reordered.pdf"), rows=rows_reorder)

    # Q1：表格 + 右上角二维码 + 医院名文字水印
    make_table_doc(os.path.join(SAMPLES, "table_qr_textwm.pdf"),
                   wm_qr=True, wm_name_text=True)
    # Q1b：同上但内容不变（应与 table_base 通过）
    # Q2：表格 + 医院名图片水印 + 二维码
    make_table_doc(os.path.join(SAMPLES, "table_qr_imgwm.pdf"),
                   wm_qr=True, wm_name_image=True)
    # Q3：表格 + 背景文字水印 + 二维码 + 图片医院名（全叠加）
    make_table_doc(os.path.join(SAMPLES, "table_all_wm.pdf"),
                   wm_qr=True, wm_name_text=True, wm_name_image=True,
                   wm_text=HOSPITAL + "  内部资料")

    print("已生成表格类样例：")
    for n in ["table_base.pdf", "table_num_changed.pdf", "table_reordered.pdf",
              "table_qr_textwm.pdf", "table_qr_imgwm.pdf", "table_all_wm.pdf"]:
        p = os.path.join(SAMPLES, n)
        print("  ", n, os.path.getsize(p))


if __name__ == "__main__":
    main()

# SPDX-License-Identifier: AGPL-3.0-only
# -*- coding: utf-8 -*-
"""
合成测试样例：模拟"公司内部定稿 PDF" 与 "医院回传的水印版 PDF"。

生成 5 份文件：
  1. internal_draft.pdf        —— 内部定稿版（基准）
  2. hospital_A_shift.pdf      —— 加水印 + 正文整体错行，内容不变     → 期望 PASS
  3. hospital_B_amount.pdf     —— 在 A 基础上改掉一个金额             → 当前字形映射异常，预期无法完整比较
  4. hospital_C_textwm.pdf     —— 水印被"写成文字对象"画进 PDF        → 当前字形映射异常，预期无法完整比较
  5. hospital_D_deleted.pdf    —— 删掉一整条条款                     → 当前字形映射异常，预期无法完整比较

用 PyMuPDF(fitz) 生成，中文用 Noto Sans CJK SC。
"""
import os
import random
import fitz  # PyMuPDF

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLES = os.path.join(HERE, "samples")
FONT_PATH = os.path.join(HERE, "NotoSansCJKsc.otf")
os.makedirs(SAMPLES, exist_ok=True)


def _ensure_font():
    """
    确保内嵌用的中文字体存在。
    优先使用【已子集化的小字体】（约 88KB），否则从系统 TTC 提取完整 SC 字体（约 16MB）。
    子集字体只含样例用到的字，能显著减小样例 PDF 体积，便于分发。
    """
    if os.path.exists(FONT_PATH):
        return
    subset = os.path.join(HERE, "打包", "fonts", "sample-subset.ttf")
    if os.path.exists(subset):
        import shutil
        shutil.copy(subset, FONT_PATH)
        return
    from fontTools.ttLib import TTCollection
    coll = TTCollection("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")
    coll.fonts[2].save(FONT_PATH)  # index 2 = Noto Sans CJK SC


_ensure_font()

PAGE_W, PAGE_H = fitz.paper_size("a4")  # 595 x 842

# ---------------------------------------------------------------------------
# 合同正文内容（分页组织）
# ---------------------------------------------------------------------------
PAGE1_LINES = [
    "医疗设备采购合同",
    "",
    "合同编号：HT-2026-0912",
    "甲方（采购方）：某某医院",
    "乙方（供应方）：某某医疗科技有限公司",
    "",
    "第一条 合同标的",
    "1.1 乙方向甲方提供彩色多普勒超声诊断仪，型号 XQ-800，数量 3 台。",
    "1.2 设备应满足国家医疗器械相关标准，并具备有效的注册证。",
    "",
    "第二条 合同金额",
    "2.1 本合同总金额为人民币壹佰贰拾万元整（￥1,200,000.00）。",
    "2.2 上述金额已包含设备价款、运输、安装及调试费用。",
    "",
    "第三条 交付与验收",
    "3.1 乙方应于合同生效之日起 45 日内完成交付。",
    "3.2 甲方应在设备到货后 10 个工作日内完成验收。",
    "",
    "第四条 付款方式",
    "4.1 验收合格后 30 日内，甲方支付合同总金额的 90%。",
    "4.2 质保金为合同总金额的 10%，质保期满后无息退还。",
]
PAGE2_LINES = [
    "第五条 质量保证",
    "5.1 乙方对提供的设备提供 24 个月免费质保。",
    "5.2 质保期内非人为损坏，乙方负责免费维修或更换。",
    "",
    "第六条 违约责任",
    "6.1 任何一方违约，应向守约方支付合同总金额 5% 的违约金。",
    "6.2 因不可抗力导致无法履行的，双方可协商解除合同。",
    "",
    "第七条 争议解决",
    "7.1 双方因履行本合同发生争议，应友好协商解决。",
    "7.2 协商不成的，提交甲方所在地人民法院诉讼解决。",
    "",
    "第八条 其他约定",
    "8.1 本合同一式肆份，甲乙双方各执贰份，具有同等法律效力。",
    "8.2 本合同自双方签字盖章之日起生效。",
    "",
    "甲方（盖章）：某某医院",
    "乙方（盖章）：某某医疗科技有限公司",
    "签订日期：2026 年 9 月 12 日",
]

HOSPITAL_NAME = "某某医院"


def new_doc():
    return fitz.open()


def insert_cjk(page, point, text, size=10.5, color=(0, 0, 0), rotate=0):
    """在 page 的 point 处插入文本，使用内嵌的 CJK 字体。"""
    page.insert_text(point, text, fontsize=size, fontname="cjk",
                     fontfile=FONT_PATH, color=color, rotate=rotate)


def insert_centered(page, y, text, size=18, color=(0, 0, 0)):
    w = fitz.get_text_length(text, fontname="helv", fontsize=size)  # 粗略
    # 用 CJK 估算：中文按 size 宽
    est = sum(size if ord(ch) > 127 else size * 0.5 for ch in text)
    x = (PAGE_W - est) / 2
    page.insert_text((x, y), text, fontsize=size, fontname="cjk",
                     fontfile=FONT_PATH, color=color)


def draw_lines(page, lines, x=60, top=780, leading=22, size=10.5, shift=0):
    y = top + shift
    for ln in lines:
        if ln.strip():
            insert_cjk(page, (x, y), ln, size=size)
        y -= leading


def draw_qr(page, x, y, size=52):
    """矢量二维码（图形层）。"""
    shape = page.new_shape()
    shape.draw_rect(fitz.Rect(x, y + size - 14, x + 14, y + size))
    shape.draw_rect(fitz.Rect(x + size - 14, y + size - 14, x + size, y + size))
    shape.draw_rect(fitz.Rect(x, y, x + 14, y + 14))
    random.seed(42)
    for i in range(7):
        for j in range(7):
            if random.random() > 0.5:
                shape.draw_rect(fitz.Rect(x + 18 + i * 4.5, y + 18 + j * 4.5,
                                          x + 22 + i * 4.5, y + 22 + j * 4.5))
    shape.finish(color=None, fill=(0.2, 0.2, 0.2))
    shape.commit()


def draw_barcode(page, x, y, w=110, h=26):
    shape = page.new_shape()
    random.seed(7)
    cx = x
    while cx < x + w:
        bw = random.choice([1, 1, 2, 3])
        shape.draw_rect(fitz.Rect(cx, y, cx + bw, y + h))
        cx += bw + random.choice([1, 2, 3])
    shape.finish(color=None, fill=(0, 0, 0))
    shape.commit()


def add_hospital_header_graphic(page):
    """右上角图形水印：二维码 + 医院名 + 条形码（二维码/条码为图形层）。"""
    draw_qr(page, PAGE_W - 80, PAGE_H - 78)
    insert_cjk(page, (PAGE_W - 150, PAGE_H - 90), HOSPITAL_NAME, size=9,
               color=(0.5, 0.5, 0.5))
    draw_barcode(page, PAGE_W - 170, PAGE_H - 120)


# ---------------------------------------------------------------------------
# 1. 内部定稿版
# ---------------------------------------------------------------------------
def make_internal():
    path = os.path.join(SAMPLES, "internal_draft.pdf")
    doc = new_doc()
    p1 = doc.new_page(width=PAGE_W, height=PAGE_H)
    insert_centered(p1, 800, PAGE1_LINES[0], size=18)
    draw_lines(p1, PAGE1_LINES[1:], top=760)
    p2 = doc.new_page(width=PAGE_W, height=PAGE_H)
    draw_lines(p2, PAGE2_LINES, top=780)
    doc.save(path)
    doc.close()
    return path


# ---------------------------------------------------------------------------
# 2. 医院 A 版：图形水印 + 正文整体下移错行（内容不变）
# ---------------------------------------------------------------------------
def make_hospital_A():
    path = os.path.join(SAMPLES, "hospital_A_shift.pdf")
    doc = new_doc()
    p1 = doc.new_page(width=PAGE_W, height=PAGE_H)
    insert_centered(p1, 782, PAGE1_LINES[0], size=18)   # 标题下移
    draw_lines(p1, PAGE1_LINES[1:], top=742, shift=0)   # 正文下移 18pt
    add_hospital_header_graphic(p1)
    p2 = doc.new_page(width=PAGE_W, height=PAGE_H)
    draw_lines(p2, PAGE2_LINES, top=762)
    add_hospital_header_graphic(p2)
    doc.save(path)
    doc.close()
    return path


# ---------------------------------------------------------------------------
# 3. 医院 B 版：在 A 基础上把金额 1,200,000 改成 1,500,000
# ---------------------------------------------------------------------------
def make_hospital_B():
    path = os.path.join(SAMPLES, "hospital_B_amount.pdf")
    page1 = [ln.replace("1,200,000.00", "1,500,000.00")
               .replace("壹佰贰拾万元", "壹佰伍拾万元") for ln in PAGE1_LINES]
    doc = new_doc()
    p1 = doc.new_page(width=PAGE_W, height=PAGE_H)
    insert_centered(p1, 782, page1[0], size=18)
    draw_lines(p1, page1[1:], top=742)
    add_hospital_header_graphic(p1)
    p2 = doc.new_page(width=PAGE_W, height=PAGE_H)
    draw_lines(p2, PAGE2_LINES, top=762)
    add_hospital_header_graphic(p2)
    doc.save(path)
    doc.close()
    return path


# ---------------------------------------------------------------------------
# 4. 医院 C 版：水印被写成"文字对象"（会混进文字层！）
# ---------------------------------------------------------------------------
def make_hospital_C():
    path = os.path.join(SAMPLES, "hospital_C_textwm.pdf")
    doc = new_doc()

    def bg_watermark(page):
        # 45° 旋转的灰色文字，画在正文之下（用旋转矩阵实现任意角度）
        import math
        angle = math.radians(45)
        mat = fitz.Matrix(1, 1).prerotate(45)
        page.insert_text((170, 480), HOSPITAL_NAME + "  内部资料",
                         fontsize=42, fontname="cjk", fontfile=FONT_PATH,
                         color=(0.85, 0.85, 0.85), morph=(fitz.Point(170, 480), mat),
                         overlay=False)

    p1 = doc.new_page(width=PAGE_W, height=PAGE_H)
    bg_watermark(p1)
    insert_centered(p1, 782, PAGE1_LINES[0], size=18)
    draw_lines(p1, PAGE1_LINES[1:], top=742)
    add_hospital_header_graphic(p1)

    p2 = doc.new_page(width=PAGE_W, height=PAGE_H)
    bg_watermark(p2)
    draw_lines(p2, PAGE2_LINES, top=762)
    add_hospital_header_graphic(p2)

    doc.save(path)
    doc.close()
    return path


# ---------------------------------------------------------------------------
# 5. 医院 D 版：删掉一整条"第六条 违约责任"
# ---------------------------------------------------------------------------
def make_hospital_D():
    path = os.path.join(SAMPLES, "hospital_D_deleted.pdf")
    p2 = [ln for ln in PAGE2_LINES
          if not (ln.startswith("第六条") or ln.startswith("6.1") or ln.startswith("6.2"))]
    doc = new_doc()
    p1 = doc.new_page(width=PAGE_W, height=PAGE_H)
    insert_centered(p1, 782, PAGE1_LINES[0], size=18)
    draw_lines(p1, PAGE1_LINES[1:], top=742)
    add_hospital_header_graphic(p1)
    p2p = doc.new_page(width=PAGE_W, height=PAGE_H)
    draw_lines(p2p, p2, top=762)
    add_hospital_header_graphic(p2p)
    doc.save(path)
    doc.close()
    return path


# ---------------------------------------------------------------------------
# 6. 医院 E 版：页面可用宽度变窄 → 正文提前换行（同一句话被切断在不同位置）
#    这是"逐行比对"最容易误报的场景：内容一字未改，行边界全变了。
# ---------------------------------------------------------------------------
def _wrap_cjk(text, size, max_width):
    """按可用宽度把一段文字折成多行（中文按字宽≈size 估算，英文按 0.5）。"""
    lines, cur, w = [], "", 0.0
    for ch in text:
        cw = size if ord(ch) > 127 else size * 0.5
        if w + cw > max_width and cur:
            lines.append(cur)
            cur, w = ch, cw
        else:
            cur += ch
            w += cw
    if cur:
        lines.append(cur)
    return lines


def make_hospital_E():
    path = os.path.join(SAMPLES, "hospital_E_narrow.pdf")
    doc = new_doc()
    # 正文可用宽度从正常的 ~475pt 收窄到 ~260pt（模拟页面变窄/边距变大）
    narrow_w = 260
    x = 60

    def render(page, lines, title=None):
        y = 742
        if title:
            insert_centered(page, 782, title, size=18)
        for ln in lines:
            if not ln.strip():
                y -= 22
                continue
            for seg in _wrap_cjk(ln, 10.5, narrow_w):
                insert_cjk(page, (x, y), seg, size=10.5)
                y -= 22

    p1 = doc.new_page(width=PAGE_W, height=PAGE_H)
    render(p1, PAGE1_LINES[1:], title=PAGE1_LINES[0])
    add_hospital_header_graphic(p1)
    p2 = doc.new_page(width=PAGE_W, height=PAGE_H)
    render(p2, PAGE2_LINES)
    add_hospital_header_graphic(p2)
    doc.save(path)
    doc.close()
    return path


def make_hospital_F():
    """变窄换行 + 改金额（假阳性压力测试：真正差异只有 1 处）。"""
    path = os.path.join(SAMPLES, "hospital_F_narrow_amount.pdf")
    doc = new_doc()
    narrow_w = 260
    x = 60
    page1 = [ln.replace("1,200,000.00", "1,500,000.00")
               .replace("壹佰贰拾万元", "壹佰伍拾万元") for ln in PAGE1_LINES]

    def render(page, lines, title=None):
        y = 742
        if title:
            insert_centered(page, 782, title, size=18)
        for ln in lines:
            if not ln.strip():
                y -= 22
                continue
            for seg in _wrap_cjk(ln, 10.5, narrow_w):
                insert_cjk(page, (x, y), seg, size=10.5)
                y -= 22

    p1 = doc.new_page(width=PAGE_W, height=PAGE_H)
    render(p1, page1[1:], title=page1[0])
    add_hospital_header_graphic(p1)
    p2 = doc.new_page(width=PAGE_W, height=PAGE_H)
    render(p2, PAGE2_LINES)
    add_hospital_header_graphic(p2)
    doc.save(path)
    doc.close()
    return path


if __name__ == "__main__":
    print("内部定稿版:", make_internal())
    print("医院A(水印+错行):", make_hospital_A())
    print("医院B(改金额):", make_hospital_B())
    print("医院C(文字层水印):", make_hospital_C())
    print("医院D(删条款):", make_hospital_D())
    print("医院E(变窄换行):", make_hospital_E())
    print("医院F(变窄+改金额):", make_hospital_F())

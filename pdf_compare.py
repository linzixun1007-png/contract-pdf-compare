# SPDX-License-Identifier: AGPL-3.0-only
# -*- coding: utf-8 -*-
"""
pdf_compare.py —— 合同 PDF 文字层对比引擎（去水印 → 归一化 → 快判 → 精确定位）

设计要点（对应业务需求）：
  1. 只比"文字层"，不比格式 —— 但坐标用于【识别水印】，不用于【对齐正文】。
  2. 水印只识别独立完整名称／限定标签，并结合所选档位的样式条件；
     位置、旋转或字号不能单独作为删除任意正文的依据。
  3. 正文按文字序列与单元边界比较；复杂表格及 PDF 阅读顺序不同仍可能误报。
  4. 无文字、疑似扫描页、缺字或结果矛盾时，返回无法完整比较。

对外主入口：
    compare_pdfs(a_path, b_path, hospital_names=None, profile="strict") -> CompareResult
"""
from __future__ import annotations

import re
import sys
import hashlib
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Iterable

VERSION = "1.1.0"
PROFILES = {
    "strict": ("严格复核", "保留字符和词间空格差异；只清理明确指定的医院水印。"),
    "regular": ("常规合同", "忽略排版空白、全半角和兼容字形；清理具有明确特征的医院水印。"),
    "relaxed": ("宽松排版", "在常规档基础上，放宽独立医院名及常见水印标签的识别。"),
}

# PyMuPDF：新版本推荐 `import pymupdf`，旧版本为 `import fitz`（已废弃但仍在）。
# 这里做兼容：优先用新 API，失败则回退，避免未来版本移除 fitz 后崩溃。
try:
    import pymupdf as fitz          # noqa: N811  新 API（>=1.24）
except ImportError:                 # pragma: no cover
    try:
        import fitz                 # 回退旧 API
    except ImportError:
        sys.stderr.write(
            "\n[缺少依赖] 未找到 PyMuPDF。\n"
            "请先执行以下任一命令安装后再运行：\n"
            "    pip install pymupdf\n"
            "    pip3 install pymupdf\n"
            "（若公司内网，请参考交付包 03 的离线安装脚本和 06 的 IT 部署说明）\n\n"
        )
        raise


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------
@dataclass
class TextLine:
    """一行文字（已含所在页、坐标、字号、方向等元信息）。"""
    page: int          # 从 0 开始
    text: str          # 原始文本
    norm: str          # 归一化文本
    x0: float
    y0: float
    x1: float
    y1: float
    size: float
    direction: tuple   # (dx, dy)
    is_watermark: bool = False
    wm_reason: str = ""
    _cells: list = field(default_factory=list)   # 表格行的各单元格（重建后填充）
    page_w: float = 595.0
    page_h: float = 842.0


@dataclass
class DiffItem:
    """一处差异。"""
    kind: str          # 'replace' | 'delete' | 'insert'
    page: int
    old: str = ""
    new: str = ""
    similarity: float = 1.0
    note: str = ""


@dataclass
class CompareResult:
    a_path: str
    b_path: str
    passed: bool
    a_lines: list = field(default_factory=list)      # 非水印行
    b_lines: list = field(default_factory=list)
    a_watermarks: list = field(default_factory=list)
    b_watermarks: list = field(default_factory=list)
    diffs: list = field(default_factory=list)
    a_hash: str = ""
    b_hash: str = ""
    stage: str = ""    # 'hash-pass' | 'aligned' | 'unavailable'
    message: str = ""
    profile: str = "strict"
    unavailable_reasons: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    source_a_hash: str = ""
    source_b_hash: str = ""


# ---------------------------------------------------------------------------
# 1. 文本归一化
# ---------------------------------------------------------------------------
# 常见"同形异码"字符映射，PDF 提取时常因字体子集把字映射成兼容字符，
# 导致同一内容出现"数量/數量"这类假差异。这里做统一。
CHAR_FIX = {
    "\u00a0": " ",        # NBSP -> 普通空格
    "\u2011": "-",        # 非断行连字符
    "\u2013": "-",        # en dash
    "\u2014": "-",        # em dash
    "\uff0d": "-",        # 全角减号
    "\u2212": "-",        # 减号
    "\u2018": "'", "\u2019": "'",
    "\u201c": '"', "\u201d": '"',
    "\uff08": "(", "\uff09": ")",
    "\uff0c": ",", "\uff1a": ":",
    "\uff1b": ";", "\uff01": "!",
    "\uff1f": "?",
}

# 易被替换的兼容字形（CJK Compatibility / 异体映射）
VARIANT_MAP = {
    "量": "量", "更": "更", "勒": "勒", "器": "器", "不": "不", "力": "力",
    "行": "行", "律": "律", "年": "年", "履": "履", "料": "料", "不": "不",
    "更": "更", "數": "数", "列": "列", "利": "利", "度": "度", "見": "见",
    "說": "说", "若": "若", "類": "类", "例": "例", "行": "行", "參": "参",
}

# 归一化时要去掉的空白
_WS_RE = re.compile(r"\s+")


def normalize_text(s: str, drop_ws: bool = True, profile: str = "regular") -> str:
    """把一行文本归一化成"可比对"的形式。"""
    s = unicodedata.normalize("NFC" if profile == "strict" else "NFKC", s)
    out = []
    for ch in s:
        ch = (CHAR_FIX.get(ch, ch) if profile != "strict" else
              {"\u00a0": " ", "\u2011": "-"}.get(ch, ch))
        ch = VARIANT_MAP.get(ch, ch)
        out.append(ch)
    s = "".join(out)
    if drop_ws:
        if profile == "strict":
            s = _WS_RE.sub(" ", s)
            # Preserve ASCII word/number boundaries, discard Chinese layout spaces.
            s = re.sub(r"(?<![A-Za-z0-9]) +| +(?![A-Za-z0-9])", "", s)
        else:
            s = _WS_RE.sub("", s)
    return s.strip()


def content_fingerprint(lines: Iterable[str], profile: str = "regular") -> str:
    """把若干行拼成整段、归一化后求哈希。"""
    joined = "".join(normalize_text(l, profile=profile) for l in lines)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# 2. 提取带属性的文字行
# ---------------------------------------------------------------------------
def extract_lines(pdf_path: str, profile: str = "regular") -> list[TextLine]:
    doc = fitz.open(pdf_path)
    lines: list[TextLine] = []
    for pno in range(doc.page_count):
        page = doc[pno]
        d = page.get_text("dict", flags=fitz.TEXTFLAGS_TEXT)
        for blk in d.get("blocks", []):
            if blk.get("type") != 0:
                continue
            for ln in blk.get("lines", []):
                direction = tuple(round(v, 3) for v in ln.get("dir", (1.0, 0.0)))
                text = "".join(sp.get("text", "") for sp in ln.get("spans", []))
                if not text.strip():
                    continue
                size = max((sp.get("size", 0) for sp in ln.get("spans", [])), default=0)
                bbox = ln.get("bbox", (0, 0, 0, 0))
                lines.append(TextLine(
                    page=pno, text=text, norm=normalize_text(text, profile=profile),
                    x0=bbox[0], y0=bbox[1], x1=bbox[2], y1=bbox[3],
                    size=size, direction=direction,
                    page_w=page.rect.width, page_h=page.rect.height,
                ))
    doc.close()
    return lines


# ---------------------------------------------------------------------------
# 2.5 表格行重建（关键！）
# ---------------------------------------------------------------------------
#
# PDF 里表格的每个单元格都是独立的"行"对象，且 get_text 的默认阅读顺序
# 常把整列读在一起（"序号/设备名称/型号…" 再 "1/彩色多普勒…/XQ-800…"）。
# 若直接按这些碎块比对：
#   - 数字之间没有标点，会被"按句切分"粘成超长单元（"台3250000.00…"）；
#   - 差异定位会糊成一坨，人类无法复核。
#
# 解法：用坐标把"同一水平线上"的碎块合并成一条真正的表格行。
#   - 按 y 坐标（行基线）聚类，容差 row_tol；
#   - 同类内按 x 坐标升序拼接；
#   - 单元格之间插入分隔符 " ｜ "，避免数字彼此粘连。
#
# 此步提供展示／定位的单元边界，快判也核对重建后的比较单元。
# 连续字符流一致而单元边界不同，不能仅凭全局哈希直接通过。

def reconstruct_table_rows(lines: list[TextLine],
                           row_tol: float = 3.0) -> list[TextLine]:
    """
    把同一页内 y 坐标相近的碎块合并为一条表格行。

    ⚠️ 关键约束：**只合并"同一水平行内的相邻碎块"，绝不改变行的先后顺序。**
    原始提取顺序就是阅读顺序；一旦按 y 坐标全局重排，窄页版与原版的
    阅读顺序会不同，反而制造出大量假差异（这正是"坐标不可用于对齐"原则）。
    因此这里只在【原顺序上做相邻合并】。
    """
    horiz_flags = [not _direction_is_rotated(l.direction) for l in lines]
    n = len(lines)
    used = [False] * n
    result: list[TextLine] = []

    for i in range(n):
        if used[i]:
            continue
        ln = lines[i]
        if not horiz_flags[i]:
            result.append(ln)
            used[i] = True
            continue
        # 向后看，收集与当前行 y 相近、且中间没有"非表格行"打断的碎块
        group = [ln]
        used[i] = True
        j = i + 1
        while j < n and not used[j] and horiz_flags[j]:
            if lines[j].page == ln.page and abs(lines[j].y0 - ln.y0) <= row_tol:
                # 只有"同一行被切成多块"才合并：
                # 要求 x 单调递增（从左到右），避免把上下行误并
                if lines[j].x0 >= group[-1].x1 - 2:
                    group.append(lines[j])
                    used[j] = True
                    j += 1
                    continue
            break
        if len(group) == 1:
            result.append(ln)
        else:
            group.sort(key=lambda l: l.x0)
            text = " ｜ ".join(x.text.strip() for x in group if x.text.strip())
            norm_cells = [x.norm for x in group if x.norm]
            result.append(TextLine(
                page=ln.page,
                text=text,
                norm="｜".join(norm_cells),
                x0=min(x.x0 for x in group),
                y0=min(x.y0 for x in group),
                x1=max(x.x1 for x in group),
                y1=max(x.y1 for x in group),
                size=max(x.size for x in group),
                direction=(1.0, 0.0),
                _cells=[x.text.strip() for x in group if x.text.strip()],
                page_w=ln.page_w, page_h=ln.page_h,
            ))
    return result


# ---------------------------------------------------------------------------
# 3. 水印识别与剔除
# ---------------------------------------------------------------------------
@dataclass
class WatermarkConfig:
    page_w: float = 595.0
    page_h: float = 842.0
    # 右上角区域（比例）
    corner_x_ratio: float = 0.68    # x0 大于该比例页宽 → 右
    corner_y_ratio: float = 0.85    # y0 大于该比例页高 → 上（PDF 原点在左上，fitz 坐标系 y 向下）
    big_font: float = 20.0          # 超大字号阈值
    min_repeat_pages: int = 2       # 同一文本在这么多页重复 → 疑似背景水印
    hospital_names: list = field(default_factory=list)
    profile: str = "strict"
    protected_norms: set = field(default_factory=set)


def _direction_is_rotated(direction: tuple, tol: float = 0.05) -> bool:
    dx, dy = direction
    return abs(dy) > tol  # 非水平 → 旋转


def detect_watermarks(lines: list[TextLine],
                      cfg: WatermarkConfig) -> tuple[list[TextLine], list[TextLine]]:
    """Recognize standalone watermarks; font/position alone never remove text."""
    from collections import defaultdict
    page_of: dict[str, set] = defaultdict(set)
    for ln in lines:
        page_of[normalize_text(ln.text)].add(ln.page)

    clean, wm = [], []
    for ln in lines:
        norm = normalize_text(ln.text)
        reasons = []
        protected = norm in cfg.protected_norms
        # A watermark must be the entire standalone line, never a substring.
        labels = ("内部资料", "内部文件", "仅供内部使用", "仅供阅览", "仅供合同核验", "复印件")
        names = [normalize_text(h) for h in cfg.hospital_names if normalize_text(h)]
        named = any(norm == hn or any(norm == hn + label or norm == label + hn
                                      for label in labels) for hn in names)
        stripped = norm
        for label in labels:
            stripped = stripped.replace(label, "")
        inferred = bool(re.fullmatch(r"[\u3400-\u9fffA-Za-z0-9·()（）]{2,32}医院", stripped))
        label_only = norm in labels
        pw, ph = ln.page_w, ln.page_h
        margin = 0.20 if cfg.profile == "relaxed" else 0.15
        right = ln.x0 >= pw * (0.60 if cfg.profile == "relaxed" else 0.68)
        corner = right and (ln.y0 <= ph * margin or ln.y0 >= ph * (1 - margin))
        rotated = _direction_is_rotated(ln.direction)
        big = ln.size >= cfg.big_font
        repeated = len(page_of[norm]) >= cfg.min_repeat_pages
        if cfg.profile == "strict":
            accept = named and ((corner and ln.size <= 14) or (rotated and big))
        elif cfg.profile == "regular":
            accept = (named or inferred) and (corner or rotated or big)
        else:
            accept = ((named or inferred) and (corner or rotated or big or repeated))
            accept = accept or (label_only and (rotated or ln.size >= 30))
        if accept and not protected:
            reasons.append("独立医院名/水印标签")
            if corner:
                reasons.append("该页右侧角落")
            if rotated:
                reasons.append("旋转")
            if big:
                reasons.append("大字号")
            if repeated and cfg.profile == "relaxed":
                reasons.append("跨页重复")
            ln.is_watermark = True
            ln.wm_reason = "; ".join(dict.fromkeys(reasons))
            wm.append(ln)
        else:
            clean.append(ln)
    return clean, wm


# ---------------------------------------------------------------------------
# 4. 对齐与差异定位（换行/错行 双重免疫）
# ---------------------------------------------------------------------------
#
# 关键设计：**不按"行"比对，按"字符流"比对。**
#
# 为什么？换行位置是排版产物，不是内容产物。医院版页面变窄后，同一句话会被
# 提前折断（"…XQ-8 / 00…"），逐行比对必然把一句话判成"改写+新增"两处。
# 解法：把每页归一化后的所有行【无缝拼接】成一条连续字符流（丢掉换行符），
# 在这个字符流上做差分；差异定位后，再根据字符偏移反查它落在原页面的哪一行。
#
# 为让输出对人类可读，我们把连续流重新按"句子边界"（。！？；及条款号）切成
# 语义单元，以"句"为展示粒度——句子不会因页面变窄而被拆开。

_SENT_SPLIT = re.compile(r"(?<=[。！？；;!?])")
_TABLE_SEP = "\u2502"   # 表格单元格分隔符（与 reconstruct_table_rows 一致）


def _is_table_row(ln: TextLine) -> bool:
    """判断是否为重建出来的表格行（含多个单元格）。"""
    return len(getattr(ln, "_cells", []) or []) >= 3


def _build_units(lines: list[TextLine], profile: str = "regular") -> list[dict]:
    """
    把行序列拼成连续字符流，再按句切分成语义单元。

    表格行特殊处理：一行表格 = 一个原子单元（不再按标点切），
    且表格行【前后强制断开】，避免与相邻正文粘成一个超长单元。
    """
    # 为每行生成"参与比对的归一化文本"：
    #   表格行 → 单元格用 ｜ 相连（保留分隔，避免数字粘连）
    #   普通行 → 原有的 norm
    row_norms: list[str] = []
    is_table: list[bool] = []
    for ln in lines:
        tb = _is_table_row(ln)
        is_table.append(tb)
        if tb:
            row_norms.append(_TABLE_SEP.join(
                normalize_text(c, profile=profile) for c in ln._cells))
        else:
            row_norms.append(ln.norm)

    # 拼接连续字符流，维护"字符偏移 → 源行下标"
    stream_chars: list[str] = []
    offset_line: list[int] = []
    for idx, rn in enumerate(row_norms):
        for ch in rn:
            stream_chars.append(ch)
            offset_line.append(idx)
    stream = "".join(stream_chars)
    if not stream:
        return []

    n = len(stream)

    # 预先算出每个表格行的字符区间
    line_start: list[int] = []
    cursor = 0
    for rn in row_norms:
        line_start.append(cursor)
        cursor += len(rn)

    table_ranges: list[tuple[int, int]] = []
    for idx, tb in enumerate(is_table):
        if tb:
            s = line_start[idx]
            table_ranges.append((s, s + len(row_norms[idx])))

    def table_range_at(pos: int):
        for s, e in table_ranges:
            if s <= pos < e:
                return (s, e)
        return None

    # 分两阶段：
    # 阶段 A：把流切成"段落"——表格行各自成段，非表格区间按普通段落
    # 阶段 B：每个非表格段落内部再按句号切分成单元
    # 这样彻底避免不同切点来源互相干扰导致的错位。
    segments: list[tuple[int, int, bool]] = []   # (start, end, is_table)
    pos = 0
    table_ranges_sorted = sorted(table_ranges)
    for s, e in table_ranges_sorted:
        if pos < s:
            segments.append((pos, s, False))
        segments.append((s, e, True))
        pos = e
    if pos < n:
        segments.append((pos, n, False))

    units: list[dict] = []
    for s, e, is_tb in segments:
        if is_tb:
            if e > s:
                units.append(_make_unit(stream[s:e], s, e, lines, offset_line))
        else:
            # 段内按句切
            sub = stream[s:e]
            local_pos = 0
            for m in _SENT_SPLIT.finditer(sub):
                end = m.end()
                if end > local_pos:
                    units.append(_make_unit(sub[local_pos:end], s + local_pos,
                                            s + end, lines, offset_line))
                    local_pos = end
            if local_pos < len(sub):
                units.append(_make_unit(sub[local_pos:], s + local_pos,
                                        s + len(sub), lines, offset_line))
    return units


def _make_unit(seg, start, end, lines, offset_line):
    lidx = offset_line[start] if start < len(offset_line) else 0
    return {
        "text": seg,
        "page": lines[lidx].page if lines else 0,
        "start": start,
        "end": end,
        "lines": lines,
        "offset_line": offset_line,
    }


def _unit_original_text(unit) -> str:
    """取该单元对应的原始（未归一化）文字，用于人类阅读。"""
    ol = unit["offset_line"]
    lines = unit["lines"]
    if not ol:
        return ""
    i0 = ol[unit["start"]] if unit["start"] < len(ol) else 0
    i1 = ol[min(unit["end"] - 1, len(ol) - 1)] if ol else 0
    parts = []
    for i in range(i0, i1 + 1):
        parts.append(lines[i].text.strip())
    return " ".join(p for p in parts if p)


def align_diff(a_lines: list[TextLine], b_lines: list[TextLine],
               sim_threshold: float = 0.6, profile: str = "regular") -> list[DiffItem]:
    """
    在"句子单元"层面做对齐。因为句子的边界由标点决定、与页面宽度无关，
    所以页面变窄导致的换行差异不会产生任何假阳性。
    """
    a_units = _build_units(a_lines, profile=profile)
    b_units = _build_units(b_lines, profile=profile)

    a_txt = [u["text"] for u in a_units]
    b_txt = [u["text"] for u in b_units]
    sm = SequenceMatcher(a=a_txt, b=b_txt, autojunk=False)
    diffs: list[DiffItem] = []

    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        elif tag == "replace":
            a_seg, b_seg = a_units[i1:i2], b_units[j1:j2]
            used_b = set()
            for ua in a_seg:
                best_j, best_r = -1, 0.0
                for ib, ub in enumerate(b_seg):
                    if ib in used_b:
                        continue
                    r = SequenceMatcher(None, ua["text"], ub["text"]).ratio()
                    if r > best_r:
                        best_r, best_j = r, ib
                if best_j >= 0 and best_r >= sim_threshold:
                    used_b.add(best_j)
                    ub = b_seg[best_j]
                    diffs.append(DiffItem(
                        kind="replace", page=ua["page"],
                        old=_unit_original_text(ua), new=_unit_original_text(ub),
                        similarity=round(best_r, 3),
                        note="内容被改写",
                    ))
                else:
                    diffs.append(DiffItem(
                        kind="delete", page=ua["page"],
                        old=_unit_original_text(ua),
                        note="左有右无（疑似删改）",
                    ))
            for ib, ub in enumerate(b_seg):
                if ib not in used_b:
                    diffs.append(DiffItem(
                        kind="insert", page=ub["page"],
                        new=_unit_original_text(ub),
                        note="右有左无（疑似新增）",
                    ))
        elif tag == "delete":
            for ua in a_units[i1:i2]:
                diffs.append(DiffItem(kind="delete", page=ua["page"],
                                      old=_unit_original_text(ua),
                                      note="左有右无（疑似删改）"))
        elif tag == "insert":
            for ub in b_units[j1:j2]:
                diffs.append(DiffItem(kind="insert", page=ub["page"],
                                      new=_unit_original_text(ub),
                                      note="右有左无（疑似新增）"))
    return diffs


# ---------------------------------------------------------------------------
# 5. 主入口
# ---------------------------------------------------------------------------
def compare_pdfs(a_path: str, b_path: str,
                  hospital_names: list[str] | None = None,
                  profile: str = "strict") -> CompareResult:
    if profile not in PROFILES:
        raise ValueError("未知比较档位")
    a_raw = extract_lines(a_path, profile=profile)
    b_raw = extract_lines(b_path, profile=profile)
    # Keep this compatible with Python 3.10 and close both input files explicitly.
    def file_hash(path):
        digest = hashlib.sha256()
        with open(path, "rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    res = CompareResult(a_path=a_path, b_path=b_path, passed=False,
                        profile=profile, source_a_hash=file_hash(a_path),
                        source_b_hash=file_hash(b_path))
    for side, path, raw in (("A", a_path, a_raw), ("B", b_path, b_raw)):
        by_page = {}
        for line in raw:
            by_page.setdefault(line.page, []).append(line.text)
        with fitz.open(path) as doc:
            for index, page in enumerate(doc):
                chars = len("".join(by_page.get(index, [])).strip())
                image_area = 0.0
                for image in page.get_images(full=True):
                    for rect in page.get_image_rects(image[0]):
                        image_area += max(0.0, (rect & page.rect).get_area())
                coverage = image_area / max(page.rect.get_area(), 1.0)
                if chars == 0 or (chars < 30 and coverage >= 0.50):
                    res.unavailable_reasons.append(
                        f"{side} 第 {index + 1} 页：未提取到正文或疑似扫描页，需人工核对。")
    if res.unavailable_reasons:
        res.a_lines, res.b_lines = a_raw, b_raw
        res.stage = "unavailable"
        res.message = "无法完整比较：存在无文字或疑似扫描页面。本版本不包含 OCR。"
        return res
    cfg = WatermarkConfig(hospital_names=list(hospital_names or []), profile=profile,
                          protected_norms={normalize_text(line.text) for line in a_raw})
    # The approved baseline is retained; only added candidate watermarks are filtered.
    a_clean, a_wm = a_raw, []
    b_clean, b_wm = detect_watermarks(b_raw, cfg)
    for side, rows in (("A", a_clean), ("B", b_clean)):
        for line in rows:
            if "\x00" in line.text or "\ufffd" in line.text:
                note = f"{side} 第 {line.page + 1} 页：文字层含无法解码字符，需人工核对。"
                if note not in res.unavailable_reasons:
                    res.unavailable_reasons.append(note)
    if res.unavailable_reasons:
        res.a_lines, res.b_lines = a_clean, b_clean
        res.a_watermarks, res.b_watermarks = a_wm, b_wm
        res.stage = "unavailable"
        res.message = "文字提取不完整，无法确认全部正文。本版本不包含 OCR。"
        return res

    # 表格行重建：把同一水平线上的单元格碎块合并成完整表格行，
    # 仅影响"展示与定位"，不改变内容一致性判定。
    a_view = reconstruct_table_rows(a_clean)
    b_view = reconstruct_table_rows(b_clean)

    # 兜底：把两份都出现的水印行也纳入参考（若医院名未传）
    res.a_lines, res.b_lines = a_view, b_view
    res.a_watermarks, res.b_watermarks = a_wm, b_wm
    if profile == "strict" and not hospital_names:
        res.warnings.append("严格档未填写医院名；水印文字会保留供人工核对。")

    # --- 阶段一：全局哈希快判 ---
    # 哈希用"归一化连续流"，对换行/表格重排完全免疫
    res.a_hash = content_fingerprint([l.norm for l in a_clean], profile=profile)
    res.b_hash = content_fingerprint([l.norm for l in b_clean], profile=profile)
    a_units = [u["text"] for u in _build_units(a_view, profile=profile)]
    b_units = [u["text"] for u in _build_units(b_view, profile=profile)]
    if res.a_hash == res.b_hash and a_units == b_units:
        res.passed = True
        res.stage = "hash-pass"
        res.message = "在本档位成功提取并纳入比较的文字范围内，未发现差异。"
        return res

    # --- 阶段二：序列对齐精确比对 ---
    diffs = align_diff(a_view, b_view, profile=profile)
    res.diffs = diffs
    if not diffs:
        # 哈希不同却没有单元级差异：通常是字符级归一化遗漏，兜底通过并提示
        res.passed = False
        res.stage = "unavailable"
        res.message = "规范化文字指纹与结构比较结果不一致，需人工复核。"
        res.unavailable_reasons.append(res.message)
    else:
        res.passed = False
        res.stage = "aligned"
        res.message = f"发现 {len(diffs)} 处文字不一致，请人工复核。"
    return res


# ---------------------------------------------------------------------------
# CLI 调试
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("用法: python pdf_compare.py A.pdf B.pdf [医院名,逗号分隔]")
        sys.exit(1)
    names = sys.argv[3].split(",") if len(sys.argv) > 3 else []
    r = compare_pdfs(sys.argv[1], sys.argv[2], names)
    print(f"结果: {'✅ 通过' if r.passed else '❌ 不一致'}")
    print(f"阶段: {r.stage}")
    print(f"说明: {r.message}")
    print(f"水印剔除: A={len(r.a_watermarks)}行  B={len(r.b_watermarks)}行")
    for d in r.diffs:
        print(f"  [{d.kind}] p{d.page+1} {d.old!r} -> {d.new!r} ({d.note})")

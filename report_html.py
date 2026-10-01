# SPDX-License-Identifier: AGPL-3.0-only
# -*- coding: utf-8 -*-
"""
report_html.py —— 把 CompareResult 渲染成一份可视化 HTML 对比报告。

特点：
  - 左右双栏：左=内部定稿版，右=医院水印版。
  - 差异行高亮（改写/删除/新增用不同颜色）。
  - 顶部给出结论横幅 + 统计 + 水印剔除明细。
  - 生成字符级 diff（<ins>/<del>）标出具体改了哪个字。
"""
from __future__ import annotations
import html as _html
from difflib import SequenceMatcher
from pathlib import Path
from datetime import datetime


def _char_diff(old: str, new: str) -> tuple[str, str]:
    """返回 (old_html, new_html)，用 <del>/<ins> 标出字符差异。"""
    sm = SequenceMatcher(None, old, new, autojunk=False)
    o, n = [], []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            o.append(_html.escape(old[i1:i2]))
            n.append(_html.escape(new[j1:j2]))
        else:
            if tag in ("replace", "delete"):
                o.append(f'<del>{_html.escape(old[i1:i2])}</del>')
            if tag in ("replace", "insert"):
                n.append(f'<ins>{_html.escape(new[j1:j2])}</ins>')
    return "".join(o), "".join(n)


def render_report(result, title_a="内部定稿版", title_b="医院水印版",
                  out_path="report.html") -> str:
    from pdf_compare import _build_units, _unit_original_text

    # 与引擎保持一致：按「句子单元」而非「行」对齐展示，
    # 这样页面变窄导致的换行差异不会在图里显示成一堆假差异。
    a_units = _build_units(result.a_lines, profile=result.profile)
    b_units = _build_units(result.b_lines, profile=result.profile)
    rows_html = []

    a_txt = [u["text"] for u in a_units]
    b_txt = [u["text"] for u in b_units]
    sm = SequenceMatcher(a=a_txt, b=b_txt, autojunk=False)

    def unit_cell(unit, cls=""):
        if unit is None:
            return '<td class="cell empty"></td>'
        pg = f'<span class="pg">P{unit["page"]+1}</span>'
        return f'<td class="cell {cls}">{pg}{_html.escape(_unit_original_text(unit))}</td>'

    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                rows_html.append(
                    "<tr>" + unit_cell(a_units[i1 + k]) + unit_cell(b_units[j1 + k]) + "</tr>")
        elif tag == "replace":
            a_seg, b_seg = a_units[i1:i2], b_units[j1:j2]
            used_b = set()
            pairs = []
            for ua in a_seg:
                best_j, best_r = -1, 0.0
                for ib, ub in enumerate(b_seg):
                    if ib in used_b:
                        continue
                    r = SequenceMatcher(None, ua["text"], ub["text"]).ratio()
                    if r > best_r:
                        best_r, best_j = r, ib
                if best_j >= 0 and best_r >= 0.6:
                    used_b.add(best_j)
                    pairs.append((ua, b_seg[best_j]))
                else:
                    pairs.append((ua, None))
            for ib, ub in enumerate(b_seg):
                if ib not in used_b:
                    pairs.append((None, ub))
            for ua, ub in pairs:
                if ua is not None and ub is not None:
                    oh, nh = _char_diff(_unit_original_text(ua), _unit_original_text(ub))
                    pg_a = f'<span class="pg">P{ua["page"]+1}</span>'
                    pg_b = f'<span class="pg">P{ub["page"]+1}</span>'
                    rows_html.append(
                        f'<tr class="row-mod">'
                        f'<td class="cell mod">{pg_a}{oh}</td>'
                        f'<td class="cell mod">{pg_b}{nh}</td></tr>')
                elif ua is not None:
                    rows_html.append(
                        f'<tr class="row-del">{unit_cell(ua, "del")}<td class="cell empty"></td></tr>')
                else:
                    rows_html.append(
                        f'<tr class="row-ins"><td class="cell empty"></td>{unit_cell(ub, "ins")}</tr>')
        elif tag == "delete":
            for ua in a_units[i1:i2]:
                rows_html.append(
                    f'<tr class="row-del">{unit_cell(ua, "del")}<td class="cell empty"></td></tr>')
        elif tag == "insert":
            for ub in b_units[j1:j2]:
                rows_html.append(
                    f'<tr class="row-ins"><td class="cell empty"></td>{unit_cell(ub, "ins")}</tr>')

    # 水印明细
    def wm_list(items):
        if not items:
            return '<li class="none">（无）</li>'
        return "".join(
            f'<li><code>{_html.escape(w.text.strip())}</code>'
            f'<span class="why"> · {_html.escape(w.wm_reason)} · P{w.page+1}</span></li>'
            for w in items)

    from pdf_compare import PROFILES, VERSION
    unavailable = result.stage == "unavailable"
    verdict = ("⚠ 无法完整比较，请人工核对" if unavailable else
               "✓ 本档位未发现文字差异" if result.passed else "发现文字差异，请人工复核")
    verdict_cls = "unknown" if unavailable else "pass" if result.passed else "fail"
    notes = "".join(f"<li>{_html.escape(s)}</li>" for s in
                    result.unavailable_reasons + result.warnings)
    if not notes:
        notes = "<li>文字比较不覆盖图像、印章、签名及排版。</li>"

    html_doc = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>合同 PDF 文字层对比报告</title>
<style>
  :root {{
    --pass:#0a7d34; --pass-bg:#e7f7ec;
    --fail:#b42318; --fail-bg:#fdecea;
    --mod:#b54708; --mod-bg:#fff4e5;
    --del:#b42318; --del-bg:#fdecea;
    --ins:#0a7d34; --ins-bg:#e7f7ec;
    --line:#e5e7eb; --muted:#6b7280; --head:#111827;
  }}
  * {{ box-sizing: border-box; }}
  body {{ margin:0; font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;
         color:#111827; background:#f6f7f9; line-height:1.6; }}
  .wrap {{ max-width:1200px; margin:0 auto; padding:24px 20px 60px; }}
  h1 {{ font-size:22px; margin:8px 0 4px; }}
  .sub {{ color:var(--muted); font-size:13px; margin-bottom:18px; }}
  .banner {{ border-radius:12px; padding:16px 20px; margin-bottom:18px;
             display:flex; align-items:center; gap:14px; font-weight:600; font-size:17px; }}
  .banner.pass {{ background:var(--pass-bg); color:var(--pass); border:1px solid #b7e4c7; }}
  .banner.fail {{ background:var(--fail-bg); color:var(--fail); border:1px solid #f5c2c0; }}
  .banner.unknown {{ background:#fff4e5; color:#92400e; border:1px solid #fbbf24; }}
  .stats {{ display:flex; gap:12px; flex-wrap:wrap; margin-bottom:18px; }}
  .stat {{ background:#fff; border:1px solid var(--line); border-radius:10px;
           padding:10px 16px; font-size:13px; }}
  .stat b {{ display:block; font-size:20px; color:var(--head); }}
  .card {{ background:#fff; border:1px solid var(--line); border-radius:12px;
           padding:16px 18px; margin-bottom:18px; }}
  .card h2 {{ font-size:15px; margin:0 0 10px; }}
  table {{ width:100%; border-collapse:collapse; table-layout:fixed; }}
  th {{ text-align:left; font-size:13px; color:#fff; padding:8px 10px; }}
  th.a {{ background:#334155; border-radius:8px 0 0 0; }}
  th.b {{ background:#4b5563; border-radius:0 8px 0 0; }}
  td.cell {{ vertical-align:top; padding:6px 10px; border-bottom:1px solid var(--line);
             font-size:13px; word-break:break-word; white-space:pre-wrap; }}
  td.cell.empty {{ background:#fafafa; }}
  .pg {{ display:inline-block; font-size:10px; color:var(--muted); border:1px solid var(--line);
         border-radius:4px; padding:0 4px; margin-right:6px; }}
  tr.row-mod td.mod {{ background:var(--mod-bg); }}
  tr.row-del td.del {{ background:var(--del-bg); }}
  tr.row-ins td.ins {{ background:var(--ins-bg); }}
  del {{ background:#f5c2c0; color:#7a1c16; text-decoration:line-through; border-radius:3px; padding:0 2px; }}
  ins {{ background:#b7e4c7; color:#08572a; text-decoration:none; border-radius:3px; padding:0 2px; }}
  ul {{ margin:0; padding-left:18px; font-size:13px; }}
  ul li {{ margin:4px 0; }}
  .why {{ color:var(--muted); }}
  .none {{ color:var(--muted); list-style:none; margin-left:-18px; }}
  .legend {{ font-size:12px; color:var(--muted); margin-top:10px; }}
  .sw {{ display:inline-block; width:10px; height:10px; border-radius:2px; vertical-align:middle; margin-right:4px; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>合同 PDF 文字层对比报告</h1>
  <div class="sub">
    A（基准）：{_html.escape(Path(result.a_path).name)} &nbsp;·&nbsp;
    B（待校验）：{_html.escape(Path(result.b_path).name)}<br>
    比较档位：{_html.escape(PROFILES[result.profile][0])} · 版本 {VERSION} ·
    生成时间：{datetime.now().astimezone().isoformat(timespec='seconds')}
  </div>

  <div class="banner {verdict_cls}">{verdict}</div>
  <div class="card"><h2>本次比较范围</h2>
    <p>{_html.escape(PROFILES[result.profile][1])}</p><ul>{notes}</ul>
    <p>{_html.escape(result.message)}</p>
    <details><summary>原文件校验值（SHA-256）</summary>
    <div>A: <code>{result.source_a_hash}</code></div>
    <div>B: <code>{result.source_b_hash}</code></div></details>
  </div>

  <div class="stats">
    <div class="stat"><b>{len(result.diffs)}</b>差异处数</div>
    <div class="stat"><b>{len(result.a_watermarks)}</b>A 剔除水印行</div>
    <div class="stat"><b>{len(result.b_watermarks)}</b>B 剔除水印行</div>
    <div class="stat"><b>{len(result.a_lines)}</b>A 有效正文行</div>
    <div class="stat"><b>{len(result.b_lines)}</b>B 有效正文行</div>
  </div>

  <div class="card">
    <h2>水印剔除明细（医院水印版）</h2>
    <ul>{wm_list(result.b_watermarks)}</ul>
  </div>

  <div class="card">
    <h2>文字对照（请结合原 PDF 复核）</h2>
    <table>
      <colgroup><col style="width:50%"><col style="width:50%"></colgroup>
      <thead><tr><th class="a">{_html.escape(title_a)}</th><th class="b">{_html.escape(title_b)}</th></tr></thead>
      <tbody>
        {''.join(rows_html)}
      </tbody>
    </table>
    <div class="legend">
      <span class="sw" style="background:var(--mod-bg)"></span>改写
      <span class="sw" style="background:var(--del-bg); margin-left:12px"></span>删除（左有右无）
      <span class="sw" style="background:var(--ins-bg); margin-left:12px"></span>新增（右有左无）
      &nbsp;|&nbsp; <del>红底</del> / <ins>绿底</ins> 为字符级差异
    </div>
  </div>
</div>
</body>
</html>"""
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html_doc)
    return out_path

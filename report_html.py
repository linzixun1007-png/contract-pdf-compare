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


def _char_diff(old: str, new: str, profile="regular") -> tuple[str, str]:
    """返回 (old_html, new_html)，用 <del>/<ins> 标出字符差异。"""
    from pdf_compare import normalize_text, normalization_offsets
    normalized_old = normalize_text(old, profile=profile)
    normalized_new = normalize_text(new, profile=profile)
    maps = (normalization_offsets(old, normalized_old), normalization_offsets(new, normalized_new))
    masks = ([False]*len(old), [False]*len(new))
    sm = SequenceMatcher(None, normalized_old, normalized_new, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        for side, first, last, changed in ((0, i1, i2, tag in ("replace", "delete")),
                                           (1, j1, j2, tag in ("replace", "insert"))):
            if changed:
                for begin, end in maps[side][first:last]:
                    for position in range(begin, end):
                        masks[side][position] = True
    def markup(text, mask, tag):
        if not text: return ""
        parts, begin = [], 0
        for end in range(1, len(text)+1):
            if end == len(text) or mask[end] != mask[begin]:
                value = _html.escape(text[begin:end])
                parts.append(f"<{tag}>{value}</{tag}>" if mask[begin] else value)
                begin = end
        return "".join(parts)
    return markup(old, masks[0], "del"), markup(new, masks[1], "ins")


def render_report(result, title_a="内部定稿版", title_b="医院水印版",
                  out_path="report.html") -> str:
    from pdf_compare import _build_units, _unit_original_text, align_units

    # 与引擎保持一致：按「句子单元」而非「行」对齐展示，
    # 这样页面变窄导致的换行差异不会在图里显示成一堆假差异。
    a_units = _build_units(result.a_lines, profile=result.profile)
    b_units = _build_units(result.b_lines, profile=result.profile)
    rows_html = []

    def unit_cell(unit, cls=""):
        if unit is None:
            return '<td class="cell empty"></td>'
        pg = f'<span class="pg">P{unit["page"]+1}</span>'
        return f'<td class="cell {cls}">{pg}{_html.escape(_unit_original_text(unit))}</td>'

    for kind,ua,ub in align_units(a_units,b_units):
        if kind == "equal":
            rows_html.append("<tr>"+unit_cell(ua)+unit_cell(ub)+"</tr>")
        elif kind == "replace":
            oh,nh=_char_diff(_unit_original_text(ua),_unit_original_text(ub),result.profile)
            pg_a=f'<span class="pg">P{ua["page"]+1}</span>'
            pg_b=f'<span class="pg">P{ub["page"]+1}</span>'
            rows_html.append(f'<tr class="row-mod"><td class="cell mod">{pg_a}{oh}</td>'
                             f'<td class="cell mod">{pg_b}{nh}</td></tr>')
        elif kind == "delete":
            rows_html.append(f'<tr class="row-del">{unit_cell(ua,"del")}<td class="cell empty"></td></tr>')
        else:
            rows_html.append(f'<tr class="row-ins"><td class="cell empty"></td>{unit_cell(ub,"ins")}</tr>')

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
    if result.ignore_rules and result.passed:
        verdict = "✓ 指定忽略区域以外，未发现文字差异"
    def excluded_list(items):
        if not items:
            return "<li>（无）</li>"
        return "".join(f'<li>P{line.page+1} · {_html.escape(line.wm_reason)}：'
                       f'<code>{_html.escape(line.text)}</code></li>' for line in items)
    rule_rows = "".join(f'<li>{_html.escape(rule["name"])} · '
                        f'{_html.escape(rule["side"])} · '
                        f'页码：{_html.escape(str(rule["pages"] or "全部"))} · '
                        f'矩形（页面比例）：{_html.escape(str(rule["rect"]))}</li>' for rule in result.ignore_rules)
    scope_card = ""
    if result.ignore_rules:
        scope_card = f"""<div class="card">
          <h2>用户指定忽略区域</h2><ul>{rule_rows}</ul>
          <p>仅排除完全落入框内的文字字符，擦边正文会保留。页码是 PDF 实际页序。
          被排除的内容不参与一致性结论；请核对下方清单及区域预览。</p>
          <p>忽略区域中的文字差异：{"有（单独复核）" if result.excluded_differences else "未检出"}</p>
          <details><summary>A 排除文字（{len(result.a_ignored)} 段）</summary><ul>{excluded_list(result.a_ignored)}</ul></details>
          <details><summary>B 排除文字（{len(result.b_ignored)} 段）</summary><ul>{excluded_list(result.b_ignored)}</ul></details>
        </div>"""

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
  {scope_card}

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

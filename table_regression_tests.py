# SPDX-License-Identifier: AGPL-3.0-only
from pathlib import Path
from tempfile import TemporaryDirectory
from pdf_compare import (compare_pdfs, PROFILES, TextLine, normalize_text,
                         reconstruct_table_rows, _build_units, _unit_original_text, align_units)
from report_html import render_report

def run_table_checks(samples):
    root=Path(samples)/'table_regression_v12'
    checks=[]
    cases=[('grid_A','grid_stream_B',True),('grid_A','grid_wrap_B',True),
           ('grid_A','grid_wholeline_B',True),('grid_A','grid_amount_B',False),
           ('grid_A','grid_merged_B',False),('grid_A','grid_reordered_B',False),
           ('grid_A','grid_blank_B',False),('paragraph_A','paragraph_B',True),
           ('wordspace_A','wordspace_B',False),('numberspace_A','numberspace_B',False)]
    def compare(a,b,profile='regular'):
        return compare_pdfs(str(root/(a+'.pdf')),str(root/(b+'.pdf')),profile=profile)
    for profile in PROFILES:
        for a,b,expected in cases:
            result=compare(a,b,profile)
            checks.append({'case':b,'profile':profile,'ok':result.passed==expected
                           and result.stage!='unavailable','passed':result.passed,'diff_count':len(result.diffs)})
    result=compare('grid_A','grid_stream_B')
    labels=[line._cells[0] for line in result.b_lines if line._table_id]
    expected=['Label','Sample','Service','Tax','Subtotal','Pending','Support fee','Support tax','All-in total']
    checks.append({'case':'physical_grid_order_ignores_object_stream_order','ok':labels==expected})
    units=_build_units(result.b_lines)
    checks.append({'case':'merged_two_cell_rows_are_atomic','ok':all(
        not ('Support' in _unit_original_text(u) and 'Appendix' in _unit_original_text(u)) for u in units)
        and sum(bool(line._table_id) and len(line._cells)==2 for line in result.b_lines)==3})
    result=compare('grid_A','grid_merged_B')
    checks.append({'case':'merged_cell_edit_remains_separate_from_appendix','ok':bool(result.diffs)
                   and all('Appendix' not in d.old+d.new for d in result.diffs)})
    aa=[{'text':t,'index':i} for i,t in enumerate(['Tax 8.40','Subtotal 128.40','Appendix details;'])]
    bb=[{'text':t,'index':i} for i,t in enumerate(['Tax 9.40','New fee 1.00','Subtotal 129.40','Appendix details;'])]
    pairs=align_units(aa,bb)
    checks.append({'case':'alignment_preserves_both_document_orders','ok':
        [a['index'] for _,a,_ in pairs if a is not None]==list(range(len(aa))) and
        [b['index'] for _,_,b in pairs if b is not None]==list(range(len(bb)))})
    result=compare('paragraph_A','paragraph_B','relaxed')
    with TemporaryDirectory(prefix='contract-table-check-') as temp:
        report=Path(temp)/'report.html'
        render_report(result,out_path=str(report))
        html=report.read_text(encoding='utf-8')
        checks.append({'case':'layout_only_has_no_modified_rows','ok':result.passed
                       and '<tr class="row-mod">' not in html and '<tr class="row-del">' not in html
                       and '<tr class="row-ins">' not in html})
    def line(text, x0, x1):
        return TextLine(0,text,normalize_text(text),x0,120,x1,134,11,(1,0))
    fragments = reconstruct_table_rows([line('1.',40,50),line('按照条款开展研究；',70,230)])
    whole = [line('1. 按照条款开展研究；',40,230)]
    checks.append({'case':'clause_number_and_prose_are_not_a_two_cell_table','ok':
                   not fragments[0]._cells and all(
                       [u['text'] for u in _build_units(fragments,profile)] ==
                       [u['text'] for u in _build_units(whole,profile)] for profile in PROFILES)})
    return checks

# SPDX-License-Identifier: AGPL-3.0-only
"""Entirely invented table, font-fragment and layout fixtures; no input PDF."""
from pathlib import Path
from pdf_compare import fitz

ROOT=Path(__file__).parent/'samples/table_regression_v12'
ROWS=[['Label','Group A','Group B','Total'],['Sample','100','60','160'],
      ['Service','20','10','30'],['Tax','8.40','4.20','12.60'],
      ['Subtotal','128.40','74.20','202.60'],['Pending','25','','25'],
      ['Support fee','10'],['Support tax','0.50'],['All-in total','213.10']]
X=[40,190,295,400,510]
Y,H=130,26

def table(name,variant='normal'):
    doc=fitz.open(); page=doc.new_page()
    page.insert_text((40,75),'Invented fee schedule - acceptance fixture',fontsize=11)
    for y in [Y+i*H for i in range(len(ROWS)+1)]:
        page.draw_line((X[0],y),(X[-1],y),width=.7)
    for i,x in enumerate(X):
        end=Y+H*(6 if i in (2,3) else len(ROWS))
        page.draw_line((x,Y),(x,end),width=.7)
    rows=[list(row) for row in ROWS]
    if variant=='amount': rows[4][1]='928.40'
    if variant=='merged': rows[6][1]='90'
    if variant=='reordered': rows[3],rows[4]=rows[4],rows[3]
    if variant=='blank': rows[5][1],rows[5][2]='','25'
    def write_row(ri):
        row=rows[ri]
        baseline=Y+ri*H+17
        if variant=='wholeline' and len(row)==4:
            start=49; text=row[0]
            for ci,value in enumerate(row[1:],1):
                desired=int(round((X[ci]+15-start)/6))
                text+=' '*max(1,desired-len(text))+value
            page.insert_text((start,baseline),text,fontname='cour',fontsize=10)
            return
        for ci,value in enumerate(row):
            if not value: continue
            x=X[ci]+9 if ci==0 else (X[ci]+(X[-1] if len(row)==2 else X[ci+1]))/2-len(value)*3
            if variant=='wrap' and ri==0 and ci in (1,2):
                first,last=value.split()
                page.insert_text((x,baseline-7),first,fontname='cour',fontsize=10)
                page.insert_text((x,baseline+3),last,fontname='cour',fontsize=10)
            elif variant=='wrap' and ri==4 and ci==1:
                page.insert_text((x,baseline),value[:4],fontname='cour',fontsize=10)
                page.insert_text((x+24,baseline),value[4:],fontname='cobo',fontsize=10)
            else: page.insert_text((x,baseline),value,fontname='cour',fontsize=10)
    late=variant=='stream'
    for ri in range(len(rows)):
        if not late or ri not in (3,4): write_row(ri)
    page.insert_text((40,415),'Appendix B - equipment; Device count 1; Terms remain unchanged;',fontsize=10)
    if late:
        write_row(4);write_row(3)
    doc.set_metadata({'title':'Invented acceptance fixture','author':'Synthetic table generator'})
    doc.save(ROOT/(name+'.pdf'),garbage=4,deflate=True);doc.close()

def paragraph(name,alternate=False):
    doc=fitz.open(); page=doc.new_page()
    prefix='The study follows this '
    page.insert_text((40,120),prefix,fontname='helv',fontsize=11)
    x=40+fitz.get_text_length(prefix,fontsize=11)
    if alternate:
        page.insert_text((x,120),'proto',fontname='helv',fontsize=11)
        page.insert_text((x+fitz.get_text_length('proto',fontsize=11),120),'col;',fontname='hebo',fontsize=11)
        page.insert_text((40,170),'(b)  按照合同条款开展研',fontname='china-s',fontsize=11)
        page.insert_text((40,188),'究；',fontname='china-s',fontsize=11)
    else:
        page.insert_text((x,120),'protocol;',fontname='helv',fontsize=11)
        page.insert_text((40,170),'(b) 按照合同条款开展研究；',fontname='china-s',fontsize=11)
    doc.save(ROOT/(name+'.pdf'),garbage=4,deflate=True);doc.close()

def words(name,text):
    doc=fitz.open();page=doc.new_page()
    page.insert_text((40,120),text,fontsize=11)
    doc.save(ROOT/(name+'.pdf'),garbage=4,deflate=True);doc.close()

def main():
    ROOT.mkdir(parents=True,exist_ok=True)
    table('grid_A')
    for variant in ('stream','wrap','wholeline','amount','merged','reordered','blank'):
        table('grid_'+variant+'_B',variant)
    paragraph('paragraph_A');paragraph('paragraph_B',True)
    words('wordspace_A','Code AB C;');words('wordspace_B','Code A BC;')
    words('numberspace_A','Amount USD 100;');words('numberspace_B','Amount USD 1 00;')
    print('Created 14 entirely invented PDF fixtures.')

if __name__=='__main__':main()

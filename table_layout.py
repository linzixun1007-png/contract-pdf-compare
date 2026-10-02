# SPDX-License-Identifier: AGPL-3.0-only
"""Rebuild proven vector-grid tables without sorting the surrounding prose."""
from dataclasses import replace
from pdf_compare import fitz, TextLine, normalize_text

def _box(pieces):
    box = fitz.Rect(pieces[0][1])
    for _, rectangle in pieces[1:]:
        box |= fitz.Rect(rectangle)
    return box

def _join_fragments(fragments):
    # Font changes can split one cell into multiple text objects. Group their
    # baselines, then follow physical left-to-right order within each baseline.
    bands=[]
    for fragment in sorted(fragments,key=lambda f:(f[1].y0,f[1].x0)):
        band=next((b for b in bands if abs(b[0][1].y0-fragment[1].y0)<=3),None)
        if band is None: bands.append([fragment])
        else: band.append(fragment)
    text=""
    for band in bands:
        band.sort(key=lambda f:f[1].x0)
        part=band[0][0].strip()
        for previous,current in zip(band,band[1:]):
            part+=(" " if current[1].x0-previous[1].x1>=1 else "")+current[0].strip()
        text+=(" " if text else "")+part
    return text

def rebuild_bordered_tables(path, lines, profile):
    if not lines: return lines,[]
    plans,warnings=[],[]
    with fitz.open(path) as doc:
        for pno,page in enumerate(doc):
            if not any(line.page==pno for line in lines): continue
            rotation=page.rotation
            try:
                # Character coordinates always use the unrotated page frame.
                if rotation: page.set_rotation(0)
                paths=page.get_drawings()
                if len(paths)<4: continue
                finder=page.find_tables(strategy="lines_strict",paths=paths)
                accepted=[]
                for index,table in enumerate(finder.tables):
                    if table.row_count<2 or table.col_count<2: continue
                    bbox=fitz.Rect(table.bbox)
                    if any((bbox & other).get_area()>1 for other in accepted):
                        warnings.append(f"第 {pno+1} 页有重叠表格边框，保留原提取结果供人工复核。")
                        continue
                    rows=[[tuple(cell) for cell in row.cells if cell is not None] for row in table.rows]
                    # Horizontal merged cells are represented once. A vertical
                    # merge is ambiguous across rows, so keep the original data.
                    unique=[cell for row in rows for cell in row]
                    vertical_merge=any(row and (max(c[3] for c in row)-min(c[3] for c in row)>1
                                               or max(c[1] for c in row)-min(c[1] for c in row)>1) for row in rows)
                    if vertical_merge or len(set(unique))!=len(unique) or any(
                        (fitz.Rect(a)&fitz.Rect(b)).get_area()>1
                        for i,a in enumerate(unique) for b in unique[i+1:]):
                        warnings.append(f"第 {pno+1} 页含跨行合并单元格，保留原提取结果供人工复核。")
                        continue
                    accepted.append(bbox)
                    plans.append({"page":pno,"id":f"{pno}:{index}","bbox":bbox,"rows":rows,
                                  "data":[[[] for cell in row] for row in rows],"indices":set()})
            except Exception as error:
                warnings.append(f"第 {pno+1} 页表格边框识别失败，保留原提取结果（{type(error).__name__}）。")
            finally:
                if rotation: page.set_rotation(rotation)
    if not plans: return lines,warnings

    leftovers={}
    for index,line in enumerate(lines):
        candidates=[plan for plan in plans if plan["page"]==line.page]
        if not candidates or not line._glyphs or abs(line.direction[1])>.05: continue
        pieces_by_cell={}
        outside=[]
        for glyph in line._glyphs:
            _,raw=glyph
            x,y=(raw[0]+raw[2])/2,(raw[1]+raw[3])/2
            match=None
            for pi,plan in enumerate(candidates):
                if not plan["bbox"].contains(fitz.Point(x,y)): continue
                for ri,row in enumerate(plan["rows"]):
                    for ci,cell in enumerate(row):
                        if cell[0]-.01<=x<cell[2] and cell[1]-.01<=y<cell[3]:
                            match=(pi,ri,ci)
                            break
                    if match: break
                if match: break
            if match: pieces_by_cell.setdefault(match,[]).append(glyph)
            else: outside.append(glyph)
        if not pieces_by_cell: continue
        for (pi,ri,ci),pieces in pieces_by_cell.items():
            plan=candidates[pi]
            plan["indices"].add(index)
            text="".join(ch for ch,_ in pieces)
            if text.strip():
                plan["data"][ri][ci].append((text,_box(pieces),line.size,line.direction))
        if outside and "".join(c for c,_ in outside).strip():
            text="".join(c for c,_ in outside)
            box=_box(outside)
            leftovers[index]=replace(line,text=text,norm=normalize_text(text,profile=profile),
                                     x0=box.x0,y0=box.y0,x1=box.x1,y1=box.y1,_glyphs=outside)
        else: leftovers[index]=None

    insertions={}
    for plan in plans:
        if not plan["indices"]: continue
        rebuilt=[]
        for row,cells in zip(plan["rows"],plan["data"]):
            values=[_join_fragments(parts) if parts else "" for parts in cells]
            if not any(values): continue
            rectangles=[fitz.Rect(cell) for cell in row]
            bbox=rectangles[0]
            for rectangle in rectangles[1:]: bbox |= rectangle
            size=max((fragment[2] for cell in cells for fragment in cell),default=10)
            original=lines[min(plan["indices"])]
            text=" ｜ ".join(values)
            rebuilt.append(TextLine(plan["page"],text,normalize_text(text,profile=profile),
                                    *bbox,size,(1,0),_cells=values,page_w=original.page_w,
                                    page_h=original.page_h,_table_id=plan["id"]))
        insertions.setdefault(min(plan["indices"]),[]).extend(rebuilt)
    result=[]
    for index,line in enumerate(lines):
        result.extend(insertions.get(index,[]))
        if index not in leftovers: result.append(line)
        elif leftovers[index] is not None: result.append(leftovers[index])
    return result,warnings

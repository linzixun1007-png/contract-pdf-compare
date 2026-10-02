# SPDX-License-Identifier: AGPL-3.0-only
"""Generate only invented ASCII PDFs for region and report acceptance checks."""
from pathlib import Path
from pdf_compare import fitz

ROOT = Path(__file__).parent / "samples" / "regression_v12"
BODY = ["The parties agree to perform the study with care;",
        "Payments remain USD 100;", "The institution keeps complete records;"]

def document(name, pages, footer="Page {page}", header="Synthetic template",
             early_footer=False, size=(595, 842), rotation=0):
    doc = fitz.open()
    for number, rows in enumerate(pages, 1):
        page = doc.new_page(width=size[0], height=size[1])
        if header:
            page.insert_text((40, 35), header, fontsize=11)
        if early_footer and footer:
            page.insert_text((40, size[1]-25), footer.format(page=number), fontsize=11)
        for index, row in enumerate(rows):
            page.insert_text((40, 120+index*24), row, fontsize=11)
        if footer and not early_footer:
            page.insert_text((40, size[1]-25), footer.format(page=number), fontsize=11)
        page.set_rotation(rotation)
    doc.set_metadata({"title": "Invented acceptance fixture", "author": "Synthetic test generator"})
    doc.save(ROOT / (name + ".pdf"), garbage=4, deflate=True)
    doc.close()

def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    document("reflow_A", [BODY[:2], BODY[2:]])
    flow = [["The parties agree to perform"], ["the study with care;", BODY[1]], BODY[2:]]
    document("reflow_B", flow, early_footer=True)
    document("body_change_B", [flow[0], [flow[1][0], "Payments remain USD 900;"], flow[2]], early_footer=True)
    document("excluded_A", [BODY], footer="Approved reference")
    document("excluded_B", [BODY], footer="Changed reference")
    document("page_scope_A", [[BODY[0]], BODY[1:]], footer="Approved reference")
    document("page_scope_B", [[BODY[0]], BODY[1:]], footer="Changed reference")
    document("side_A", [BODY], header="Extra reference label", footer="")
    document("side_B", [BODY], header="", footer="")
    document("rotated_A", [["Stamp ABC", *BODY]], header="", footer="", rotation=90)
    document("rotated_B", [["Stamp XYZ", *BODY]], header="", footer="", rotation=90)
    document("glyph_A", [["Stamp ABC; Pay USD 100;", BODY[2]]], header="", footer="")
    document("glyph_B", [["Stamp XYZ; Pay USD 100;", BODY[2]]], header="", footer="")
    document("sizes_A", [BODY], footer="Approved reference", size=(612, 792))
    document("sizes_B", [BODY], footer="Changed reference", size=(595, 842))
    document("scan_mask_A", [BODY], footer="", header="")
    doc = fitz.open()
    page = doc.new_page()
    pix = fitz.Pixmap(fitz.csRGB, (0, 0, 50, 50), False)
    pix.clear_with(255)
    page.insert_image(page.rect, stream=pix.tobytes("png"))
    doc.set_metadata({"title": "Invented image-only acceptance fixture"})
    doc.save(ROOT / "scan_mask_B.pdf", garbage=4, deflate=True)
    doc.close()
    print("Created 17 entirely invented PDF fixtures.")

if __name__ == "__main__":
    main()

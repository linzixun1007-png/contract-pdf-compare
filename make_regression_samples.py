# SPDX-License-Identifier: AGPL-3.0-only
from pathlib import Path
from PIL import Image, ImageDraw
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.lib.utils import ImageReader
FIXTURES = Path(__file__).resolve().parent / "samples/regression"
FIXTURES.mkdir(parents=True, exist_ok=True)
pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
def fixture(name, pages):
    path = FIXTURES / (name + '.pdf')
    pdf = canvas.Canvas(str(path), pagesize=(595, 842), pageCompression=0)
    for draws in pages:
        for draw in draws:
            if draw[0] == 'text':
                _, text, x, y, size, font = draw
                pdf.setFont(font, size)
                pdf.drawString(x, y, text)
            elif draw[0] == 'rotated':
                _, text, x, y = draw
                pdf.saveState()
                pdf.translate(x, y)
                pdf.rotate(90)
                pdf.setFont('Helvetica', 11)
                pdf.drawString(0, 0, text)
                pdf.restoreState()
            elif draw[0] == 'scan':
                img = Image.new('RGB', (595, 842), 'white')
                ImageDraw.Draw(img).text((60, 210), draw[1], fill='black', font_size=25)
                pdf.drawImage(ImageReader(img), 0, 0, width=595, height=842)
        pdf.showPage()
    pdf.save()
    return path


def text(s, x=60, y=580, size=11, font='Helvetica'):
    return ('text', s, x, y, size, font)



def check(name, a_pages, b_pages, **ignored):
    fixture(name + "_A", a_pages)
    fixture(name + "_B", b_pages)
BODY = text('Delivery within 45 days;')
check('scan_only_changed', [[('scan', 'Amount: 1000')]], [[('scan', 'Amount: 9000')]])
check('mixed_scan_changed', [[BODY], [('scan', 'Amount: 1000')]],
      [[BODY], [('scan', 'Amount: 9000')]])
check('top_right_contract_id', [[text('Contract: A001', x=430, y=780), BODY]],
      [[text('Contract: A009', x=430, y=780), BODY]])
check('large_font_amount', [[text('Amount: 1000', y=700, size=22), BODY]],
      [[text('Amount: 9000', y=700, size=22), BODY]])
check('short_hospital_party', [[text('甲方：某某医院', y=700, font='STSong-Light'), BODY]],
      [[text('甲方：某某医院分院', y=700, font='STSong-Light'), BODY]], names=['某某医院'])
check('rotated_amount', [[('rotated', 'Amount: 1000', 100, 700), BODY]],
      [[('rotated', 'Amount: 9000', 100, 700), BODY]])
header = [text('Item', x=60, y=680), text('Quantity', x=220, y=680),
          text('Unit price', x=380, y=680)]
check('table_cell_boundary_changed', [header + [text('A', x=60, y=650),
      text('12', x=220, y=650), text('3', x=380, y=650)]],
      [header + [text('A', x=60, y=650), text('1', x=220, y=650), text('23', x=380, y=650)]])
check('english_word_boundary', [[text('Model: AB C;'), BODY]], [[text('Model: A BC;'), BODY]])
check('unicode_superscript', [[text('Unit: m²;'), BODY]], [[text('Unit: m2;'), BODY]])
page_content = [text('Contract: A001;', y=700), text('Amount: 1000;', y=670), BODY]
check('same_visual_different_object_order', [page_content], [list(reversed(page_content))], expected_pass=True)

# A scan attached on only one side must not be silently ignored.
check('added_scan_page', [[BODY]], [[BODY], [('scan', 'Additional payment: 9000')]])

a = FIXTURES / 'page_size_A.pdf'
b = FIXTURES / 'page_size_B.pdf'
pdf = canvas.Canvas(str(a), pagesize=(595, 842))
pdf.setFont('Helvetica', 11)
pdf.drawString(60, 580, 'Delivery within 45 days;')
pdf.save()
pdf = canvas.Canvas(str(b), pagesize=(300, 500))
pdf.setFont('Helvetica', 11)
pdf.drawString(60, 238, 'Delivery within 45 days;')
pdf.drawString(220, 470, 'WATERMARK')
pdf.save()

print("Generated 24 fictional regression PDFs.")

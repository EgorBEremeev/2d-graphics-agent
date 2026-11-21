"""Полный рисунок SVG → векторный PDF-постер в заданной ширине.

Inkscape экспортирует видимые границы рисунка, PyMuPDF масштабирует и делит
его на листы. Все размеры задаются через CLI в мм. DPI относится к эффектам
Inkscape и контрольным PNG; векторные контуры не растрируются.
Ошибки входа/экспорта/проверки прерывают выпуск. Существующие файлы не затираются.
"""
import argparse
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys

import pymupdf as pdf
from PIL import Image, ImageOps, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.inkscape.runtime import temporary_environment

PT = 72 / 25.4


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--width-mm', type=float, required=True)
    p.add_argument('--page-mm', nargs=2, type=float, default=[297, 210])
    p.add_argument('--margin-mm', type=float, default=10)
    p.add_argument('--footer-mm', type=float, default=6)
    p.add_argument('--dpi', type=int, default=300)
    p.add_argument('--font-file', type=Path, required=True)
    p.add_argument('--pdf-name', help='Имя итогового PDF внутри каталога выпуска')
    args = p.parse_args()
    source = args.source.resolve()
    filename = args.pdf_name or f'{source.stem}-{args.width_mm:g}mm-{args.dpi}dpi.pdf'
    if Path(filename).name != filename or Path(filename).suffix.lower() != '.pdf':
        p.error('--pdf-name должен быть именем файла с расширением .pdf')
    pw, ph = args.page_mm
    m, footer = args.margin_mm, args.footer_mm
    cw, ch = pw - 2*m, ph - 2*m - footer
    if not all(math.isfinite(v) for v in [pw, ph, m, footer, args.width_mm]):
        p.error('Размеры должны быть конечными числами')
    if min(cw, ch, args.width_mm, args.dpi) <= 0 or min(m, footer) < 0:
        p.error('Неположительная область печати/ширина/DPI либо отрицательные поля')
    if not args.source.is_file() or not args.font_file.is_file():
        p.error('Отсутствует SVG или файл шрифта')
    out = args.output.resolve()
    if out.exists():
        p.error('Каталог результата уже существует: выберите новый')
    out.mkdir(parents=True)
    source = args.source.resolve()
    shutil.copyfile(source, out/'source.svg')
    records = []
    with temporary_environment() as env:
        native_path = Path(env['TEMP'])/'drawing.pdf'
        command = [str(ROOT/'.tools-graphics/inkscape/bin/inkscape.com'), str(source),
                   '--export-area-drawing', '--export-type=pdf',
                   f'--export-dpi={args.dpi}', '--export-filename='+str(native_path)]
        result = subprocess.run(command, env=env, capture_output=True, text=True,
                                encoding='utf-8', check=True)
        with pdf.open(native_path) as native:
            if len(native) != 1:
                raise ValueError('Ожидался один рисунок после экспорта Inkscape')
            original = native[0].rect
            width = args.width_mm
            height = width * original.height / original.width
            cols, rows = math.ceil(width/cw), math.ceil(height/ch)
            scaled = pdf.open()
            master = scaled.new_page(width=width*PT, height=height*PT)
            master.show_pdf_page(master.rect, native, 0)
            doc = pdf.open()
            for row in range(rows):
                for col in range(cols):
                    x, y = col*cw, row*ch
                    w, h = min(cw, width-x), min(ch, height-y)
                    clip = pdf.Rect(x*PT, y*PT, (x+w)*PT, (y+h)*PT)
                    dest = pdf.Rect(m*PT, m*PT, (m+w)*PT, (m+h)*PT)
                    page = doc.new_page(width=pw*PT, height=ph*PT)
                    page.show_pdf_page(dest, scaled, 0, clip=clip, keep_proportion=False)
                    page.insert_font(fontname='label', fontfile=str(args.font_file))
                    label = (f'{row+1}-{col+1} | ряд {row+1}/{rows}, столбец {col+1}/{cols}'
                             f' | 100% | {width:g} x {height:.2f} мм')
                    page.insert_text((m*PT, (ph-m-1)*PT), label,
                                     fontname='label', fontsize=7, color=(0, 0, 0))
                    # Линейка в отведённой полосе подписи, внутри полей.
                    if cw >= 180 and footer >= 5:
                        x0, yy = (pw-m-100.5)*PT, (ph-m-2)*PT
                        page.draw_line((x0, yy), (x0+100*PT, yy), width=0.35)
                        for xx in [x0, x0+100*PT]:
                            page.draw_line((xx, yy-PT), (xx, yy+PT), width=0.35)
                    records.append(dict(page=len(doc), row=row+1, column=col+1,
                        source_clip_mm=[x, y, x+w, y+h],
                        destination_mm=[m, m, m+w, m+h], scale=[1, 1]))
            doc.set_metadata(dict(title=f'{source.stem} - {width:g} mm - {pw:g} x {ph:g} mm',
                creator='Inkscape + PyMuPDF; tools/printing/svg_poster_pdf.py'))
            doc.xref_set_key(doc.pdf_catalog(), 'ViewerPreferences', '<</PrintScaling /None>>')
            doc.set_toc([[1, f'{r["row"]}-{r["column"]}', r['page']] for r in records])
            doc.save(out/filename, garbage=4, deflate=True)
            doc.close()
            # Сверка всех страниц с независимым рендером исходного master.
            reference = master.get_pixmap(dpi=args.dpi, colorspace=pdf.csGRAY)
            reference.save(out/f'artwork-preview-{args.dpi}dpi.png')
            native_extent = [original.width/PT, original.height/PT]
            scaled.close()
    thumbs = []
    with pdf.open(out/filename) as saved:
        if len(saved) != rows*cols:
            raise AssertionError('Неверное число страниц')
        for page, record in zip(saved, records):
            assert abs(page.rect.width/PT-pw) < 0.001
            assert abs(page.rect.height/PT-ph) < 0.001
            assert not page.get_images(), 'Обнаружен растровый объект: проверьте исходник'
            pix = page.get_pixmap(dpi=args.dpi, colorspace=pdf.csGRAY)
            path = out/f'page-{page.number+1:02d}-{args.dpi}dpi.png'
            pix.save(path)
            im = Image.open(path).convert('L')
            ink = ImageOps.invert(im).getbbox()
            margin_px = m*args.dpi/25.4
            assert ink and min(ink[0], ink[1], im.width-ink[2], im.height-ink[3]) >= margin_px-2
            record['ink_bbox_px'] = list(ink)
            record['render_pixels'] = list(im.size)
            thumb = im.convert('RGB')
            thumb.thumbnail((690, 490))
            thumbs.append(thumb)
    overview = Image.new('RGB', (cols*710, rows*525), '#dddddd')
    draw = ImageDraw.Draw(overview)
    for i, thumb in enumerate(thumbs):
        xx, yy = (i%cols)*710+10, (i//cols)*525+25
        overview.paste(thumb, (xx, yy))
        draw.text((xx, yy-17), f'{i+1}: row {i//cols+1}, col {i%cols+1}', fill='black')
    overview.save(out/'page-map.png')
    manifest = dict(schema_version='1.0', coordinate_domain='P',
        source=dict(path=str(source), preserved_copy='source.svg'),
        provenance=dict(producer='tools/printing/svg_poster_pdf.py', version='1.0',
                        native_export='Inkscape', composition_render='PyMuPDF'),
        parameters=dict(width_mm=width, height_mm=height, page_mm=[pw, ph],
                        margin_mm=m, footer_mm=footer, tile_mm=[cw, ch],
                        grid=[cols, rows], overlap_mm=0, dpi=args.dpi,
                        bounds='Весь рисунок, включая объекты вне холста',
                        native_drawing_extent_mm=native_extent),
        objects=records, pdf=filename, status='PASS',
        qa_ref='Проверены размеры страниц, отсутствие растров, поля по рендеру всех страниц; page-map.png',
        warnings=['Печатать 100%, без подгонки; физический принтер не проверялся.'])
    (out/'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(dict(pdf=str(out/filename), size_mm=[width, height], grid=[cols, rows], pages=len(records)), ensure_ascii=False))


if __name__ == '__main__':
    main()

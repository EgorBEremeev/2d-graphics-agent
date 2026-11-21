"""Разместить страницы SVG с физическими размерами в PDF без масштабирования."""
import argparse
import json
import math
from pathlib import Path
import re
import subprocess
import sys

from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException
import pymupdf as pdf

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.inkscape.native import export, find_inkscape
from tools.inkscape.runtime import temporary_environment

PT = 72 / 25.4
MM_PER_UNIT = {"mm": 1, "cm": 10, "in": 25.4, "pt": 25.4 / 72, "pc": 25.4 / 6}
SIZE_TOLERANCE_MM = 0.01


def physical_size(svg):
    root = ElementTree.parse(svg).getroot()
    if root.tag != "{http://www.w3.org/2000/svg}svg":
        raise ValueError(f"{svg}: ожидался SVG")
    size = []
    for axis in ("width", "height"):
        match = re.fullmatch(r"([+]?(?:\d+(?:\.\d*)?|\.\d+))\s*(mm|cm|in|pt|pc)",
                             root.get(axis, "").strip())
        if not match:
            raise ValueError(f"{svg}: нужен явный физический размер {axis} (mm/cm/in/pt/pc)")
        mm = float(match[1]) * MM_PER_UNIT[match[2]]
        if not math.isfinite(mm) or mm <= 0:
            raise ValueError(f"{svg}: {axis} должен быть положительным конечным числом")
        size.append(mm)
    return size


def center_rect(width, height, outer_width, outer_height):
    left = (outer_width - width) / 2
    top = (outer_height - height) / 2
    return pdf.Rect(left, top, left + width, top + height)


def compose(args, inkscape):
    width, height = args.page_mm
    printable = [(length - 2 * args.margin_mm) * PT for length in args.page_mm]
    objects = []
    with pdf.open() as doc, temporary_environment() as env:
        for index, source in enumerate(args.sources, 1):
            expected = physical_size(source)
            exported = Path(env["TEMP"]) / f"source-{index}.pdf"
            export(inkscape, source, exported, "--export-area-page", "--export-type=pdf", env=env)
            with pdf.open(stream=exported.read_bytes(), filetype="pdf") as native:
                if len(native) != 1:
                    raise ValueError(f"{source}: ожидалась одна страница от Inkscape")
                media = native[0].rect
                actual = [media.width / PT, media.height / PT]
                if any(abs(a - b) > SIZE_TOLERANCE_MM for a, b in zip(actual, expected)):
                    raise ValueError(f"{source}: размеры native PDF {actual} мм, ожидались {expected} мм")
                if native[0].get_image_info():
                    raise ValueError(f"{source}: в native PDF присутствует растр")
                cropped = media.width > printable[0] or media.height > printable[1]
                if cropped and not args.crop:
                    raise ValueError(f"{source}: страница не помещается 1:1; задайте больший лист или --crop")
                clip_width = min(printable[0], media.width)
                clip_height = min(printable[1], media.height)
                clip = center_rect(clip_width, clip_height, media.width, media.height)
                destination = center_rect(clip_width, clip_height, width * PT, height * PT)
                page = doc.new_page(width=width * PT, height=height * PT)
                page.show_pdf_page(destination, native, 0, clip=clip)
                objects.append(dict(page=index, source=str(source), source_extent_mm=actual,
                                    clip_source_pt=list(clip), destination_page_pt=list(destination),
                                    scale=[1, 1], cropped=cropped))
        doc.set_metadata(dict(title=args.title or args.output.stem, creator="Inkscape + PyMuPDF"))
        doc.xref_set_key(doc.pdf_catalog(), "ViewerPreferences", "<</PrintScaling /None>>")
        payload = doc.tobytes(garbage=4, deflate=True)
    with pdf.open(stream=payload, filetype="pdf") as saved:
        if len(saved) != len(objects):
            raise ValueError("Число сохранённых страниц расходится с числом исходников")
        for page in saved:
            if (abs(page.rect.width / PT - width) > SIZE_TOLERANCE_MM
                    or abs(page.rect.height / PT - height) > SIZE_TOLERANCE_MM
                    or page.get_image_info()):
                raise ValueError(f"Страница {page.number + 1}: неверный размер или присутствует растр")
    with args.output.open("xb") as output:
        output.write(payload)
    return objects


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sources", nargs="+", type=Path, help="Один SVG на страницу PDF")
    parser.add_argument("--output", required=True, type=Path, help="Путь к новому PDF")
    parser.add_argument("--page-mm", required=True, type=float, nargs=2, metavar=("WIDTH", "HEIGHT"))
    parser.add_argument("--margin-mm", required=True, type=float)
    parser.add_argument("--crop", action="store_true", help="Разрешить центральную обрезку при 1:1")
    parser.add_argument("--title", help="Название в метаданных PDF")
    parser.add_argument("--inkscape", help="Исполняемый файл Inkscape")
    args = parser.parse_args()
    if any(not math.isfinite(v) for v in [*args.page_mm, args.margin_mm]):
        parser.error("Размеры должны быть конечными числами")
    if args.margin_mm < 0 or min(args.page_mm) <= 2 * args.margin_mm:
        parser.error("Нужна положительная рабочая область страницы и неотрицательное поле")
    if args.output.suffix.lower() != ".pdf" or args.output.exists():
        parser.error("--output должен указывать на новый файл PDF")
    try:
        records = compose(args, find_inkscape(args.inkscape))
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError,
            ElementTree.ParseError, DefusedXmlException) as exc:
        parser.exit(1, f"Выпуск PDF прерван. {exc}\n")
    print(json.dumps(dict(coordinate_domain="P", output=str(args.output), page_mm=args.page_mm,
                          margin_mm=args.margin_mm, objects=records), ensure_ascii=False))


if __name__ == "__main__":
    main()

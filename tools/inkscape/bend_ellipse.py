"""Изгиб SVG по верхней полуэллиптической дуге штатным PatternAlongPath.

Вход: простые замкнутые SVG-пути без clip/mask/use. Выход: контурный SVG,
прямой контурный вариант и manifest. Параметры заданы через CLI.
Семантика: верх bounding box идёт по дуге, высота — внутрь по нормали;
равномерный масштаб до деформации сохраняет пропорции исходной полосы.
"""
import argparse
import bisect
import copy
import json
import math
import statistics
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / '.tools-graphics/inkscape/share/inkscape/extensions'))
import inkex
from inkex.bezier import beziersplitatt
from patternalongpath import PatternAlongPath


def subdivide(sub, maximum):
    """Деление готовым алгоритмом Безье, без изменения исходной кривой."""
    result = [copy.deepcopy(sub[0])]
    for left, right in zip(sub, sub[1:]):
        pending = [(left[1], left[2], right[0], right[1])]
        while pending:
            curve = pending.pop()
            length = sum(math.dist(a, b) for a, b in zip(curve, curve[1:]))
            if length > maximum:
                first, second = beziersplitatt(curve, 0.5)
                pending.extend([second, first])
            else:
                result[-1][2] = list(curve[1])
                result.append([list(curve[2]), list(curve[3]), list(curve[3])])
    return result


class IndexedPattern(PatternAlongPath):
    """Тот же native kernel; индекс поиска заменяет линейный поиск сегмента."""
    def lengthtotime(self, distance, lengths, isclosed):
        index = min(max(bisect.bisect_right(self.cumulative, distance) - 1, 0),
                    len(lengths) - 1)
        return index, (distance - self.cumulative[index]) / lengths[index]


def write_svg(root, path):
    from lxml import etree
    path.write_text(etree.tostring(root, encoding='unicode'), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--straight-output', required=True, type=Path)
    parser.add_argument('--manifest', required=True, type=Path)
    parser.add_argument('--axis-x-mm', type=float, required=True)
    parser.add_argument('--axis-y-mm', type=float, required=True)
    parser.add_argument('--stroke-mm', type=float, default=0.35)
    parser.add_argument('--max-segment-mm', type=float, default=2)
    parser.add_argument('--tile-width-mm', type=float,
                        help='Медианная ширина bounding box исходных объектов до изгиба, мм; '
                             'одна полоса центрируется на верхней дуге')
    args = parser.parse_args()
    values = [args.axis_x_mm, args.axis_y_mm, args.stroke_mm, args.max_segment_mm]
    if args.tile_width_mm is not None:
        values.append(args.tile_width_mm)
    if any(not math.isfinite(v) or v <= 0 for v in values):
        parser.error('Размеры и допуски должны быть положительными конечными числами')
    root = inkex.load_svg(str(args.source)).getroot()
    if root.xpath('//svg:use | //svg:clipPath | //svg:mask | //svg:image | //svg:style'):
        parser.error('Вход требует нормализации: use/clip/mask/image/stylesheet')
    paths = list(root.xpath('//svg:path'))
    if not paths or any(not all(s[-1].letter in 'zZ' for s in p.path.break_apart()) for p in paths):
        parser.error('Требуются непустые замкнутые пути')
    bounds = sum((p.bounding_box(p.composed_transform()) for p in paths), None)
    a, b, margin = args.axis_x_mm / 2, args.axis_y_mm / 2, 5
    count = 16384
    skeleton = [[margin + a - a * math.cos(math.pi * i / count),
                 margin + b - b * math.sin(math.pi * i / count)] for i in range(count + 1)]
    lengths = [math.dist(x, y) for x, y in zip(skeleton, skeleton[1:])]
    cumulative = [0]
    for length in lengths:
        cumulative.append(cumulative[-1] + length)
    characteristic = statistics.median(p.bounding_box(p.composed_transform()).width for p in paths)
    scale = (args.tile_width_mm / characteristic if args.tile_width_mm is not None
             else cumulative[-1] / bounds.width)
    band_length = bounds.width * scale
    if band_length > cumulative[-1] + 1e-8:
        parser.error('Полоса выбранного масштаба не помещается на верхней половине эллипса')
    arc_offset = (cumulative[-1] - band_length) / 2
    height = bounds.height * scale
    min_radius = min(a*a/b, b*b/a)
    if height >= min_radius:
        parser.error('Высота полосы достигает радиуса кривизны: возможны складки')
    native = IndexedPattern()
    native.options = SimpleNamespace(wave=False)
    native.cumulative = cumulative
    straight = copy.deepcopy(root)
    for node in straight.xpath('//svg:path'):
        node.set('fill', 'none')
        node.set('stroke', '#000000')
        node.set('stroke-width', str(args.stroke_mm / scale))
        node.set('style', 'fill:none;stroke:#000000;stroke-width:' + str(args.stroke_mm / scale))
    straight.set('width', f'{band_length + 2*margin}mm')
    straight.set('height', f'{height + 2*margin}mm')
    straight.set('viewBox', f'{bounds.left-margin/scale} {bounds.top-margin/scale} '
                 f'{bounds.width+2*margin/scale} {bounds.height+2*margin/scale}')
    write_svg(straight, args.straight_output)
    group = inkex.Group(id='ornament-contours')
    root.append(group)
    for node in paths:
        csp = node.path.transform(node.composed_transform()).to_superpath()
        for sub in csp:
            for control in sub:
                for point in control:
                    point[0] = (point[0] - bounds.left) * scale + skeleton[0][0] + arc_offset
                    point[1] = (point[1] - bounds.top) * scale + skeleton[0][1]
        csp = inkex.paths.CubicSuperPath([subdivide(sub, args.max_segment_mm) for sub in csp])
        for sub in csp:
            for control in sub:
                native.apply_diffeomorphism(control[1], skeleton, lengths, False,
                                            (control[0], control[2]))
        node.path = csp
        node.attrib.pop('transform', None)
        node.attrib.pop('style', None)
        node.set('fill', 'none')
        node.set('stroke', '#000000')
        node.set('stroke-width', str(args.stroke_mm))
        node.set('stroke-linejoin', 'round')
        group.append(node)
    root.set('width', f'{args.axis_x_mm + 2*margin}mm')
    root.set('height', f'{b + 2*margin}mm')
    root.set('viewBox', f'0 0 {args.axis_x_mm + 2*margin} {b + 2*margin}')
    guide = inkex.Group(id='ellipse-guide')
    guide.set(inkex.addNS('groupmode', 'inkscape'), 'layer')
    guide.set(inkex.addNS('label', 'inkscape'), 'Направляющая — эллипс, верхняя половина')
    guide.set('style', 'display:none')
    guide.append(inkex.PathElement(id='upper-ellipse-arc',
        d=f'M {margin},{margin+b} A {a},{b} 0 0 1 {margin+2*a},{margin+b}',
        style='fill:none;stroke:#0099cc;stroke-width:0.35'))
    root.append(guide)
    write_svg(root, args.output)
    manifest = dict(schema_version='1.0', source=str(args.source), coordinate_domain='A',
        viewBox=[0, 0, args.axis_x_mm + 2*margin, b + 2*margin],
        objects=[dict(id=p.get('id'), source_id=p.get('id')) for p in paths],
        provenance=dict(producer='tools/inkscape/bend_ellipse.py', version='1.1',
            deformation='Inkscape PatternAlongPath.apply_diffeomorphism (GPL-2.0-or-later)',
            adaptation='Подготовка масштаба/узлов; индекс поиска длины; исходный kernel сохранён'),
        parameters=dict(axis_x_mm=args.axis_x_mm, axis_y_mm=args.axis_y_mm,
            guide='Верхняя половина; слева направо; верх bounding box на дуге',
            arc_length_mm=cumulative[-1], uniform_scale_mm_per_source_unit=scale,
            characteristic_definition='Медиана ширины bounding box исходных объектов до изгиба',
            characteristic_source_units=characteristic,
            characteristic_width_mm=characteristic*scale,
            band_arc_length_mm=band_length, arc_start_mm=arc_offset,
            arc_end_mm=arc_offset+band_length,
            band_height_mm=height, stroke_mm=args.stroke_mm,
            max_segment_mm=args.max_segment_mm, guide_segments=count,
            min_curvature_radius_mm=min_radius),
        warnings=['Художественный изгиб; это не раскладка физических камней и не печатная пагинация.'],
        outputs=[str(args.output), str(args.straight_output)], qa_ref='qa.json')
    args.manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(manifest['parameters'], ensure_ascii=False))


if __name__ == '__main__':
    main()

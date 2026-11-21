"""Собрать редактируемый художественный лист из SVG и стабильной палитры."""
import argparse
import copy
import json
import math
from pathlib import Path
import re
import sys
import textwrap

from lxml import etree as ET

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.inkscape.runtime import temporary_environment

NS = 'http://www.w3.org/2000/svg'
VERSION = '1.0'


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def number(value, name, positive=True):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f'{name}: требуется конечное число')
    if positive and value <= 0:
        raise ValueError(f'{name}: требуется значение > 0')
    return value


def validate_layout(layout):
    if layout.get('schema_version') != VERSION:
        raise ValueError('layout.schema_version должен быть 1.0')
    allowed = {'schema_version', 'page', 'artwork_panel', 'legend', 'title', 'notes', 'print_profile'}
    if set(layout) - allowed:
        raise ValueError('Неизвестные поля layout: ' + ', '.join(set(layout) - allowed))
    page = layout['page']
    if page.get('unit') != 'px':
        raise ValueError('Поддержаны page units px; физический print profile UNPROVEN')
    for key in ('width', 'height'):
        number(page[key], 'page.' + key)
    margin = number(page['margin'], 'page.margin', False)
    if margin < 0:
        raise ValueError('Отрицательное поле страницы')
    panels = []
    for key in ('artwork_panel', 'legend'):
        panel = layout[key]
        for field in ('x', 'y', 'width', 'height'):
            number(panel[field], key + '.' + field, field in ('width', 'height'))
        x, y, w, h = [panel[f] for f in ('x', 'y', 'width', 'height')]
        if x < margin or y < margin or x + w > page['width'] - margin or y + h > page['height'] - margin:
            raise ValueError(key + ' выходит за поля страницы')
        panels.append((x, y, x+w, y+h))
    a, b = panels
    if min(a[2], b[2]) > max(a[0], b[0]) and min(a[3], b[3]) > max(a[1], b[1]):
        raise ValueError('Панели artwork и legend пересекаются')
    if layout['artwork_panel'].get('fit', 'contain') != 'contain' or layout['artwork_panel'].get('allow_distortion', False):
        raise ValueError('Поддержан только contain без деформации')
    legend = layout['legend']
    if type(legend['columns']) is not int or legend['columns'] < 1:
        raise ValueError('legend.columns: требуется целое > 0')
    for key in ('font_size', 'swatch_size', 'gap'):
        number(legend[key], 'legend.' + key)
    if legend.get('overflow', 'new_page') != 'new_page':
        raise ValueError('legend.overflow: поддержан new_page')
    if not isinstance(legend['font_family'], str) or not legend['font_family'].strip():
        raise ValueError('Требуется font_family')
    if layout.get('print_profile', {}).get('physical_1_to_1', False):
        raise ValueError('B→P 1:1 не входит в принятый интерфейс')
    if not isinstance(layout.get('title', ''), str) or not isinstance(layout.get('notes', ''), str):
        raise ValueError('title и notes должны быть строками')


def read_artwork(path):
    data = path.read_bytes()
    if b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():
        raise ValueError('UNSUPPORTED_SVG_FEATURE: DTD/entities')
    root = ET.fromstring(data, ET.XMLParser(resolve_entities=False, no_network=True))
    if root.tag != f'{{{NS}}}svg':
        raise ValueError('Требуется SVG root')
    vb = [float(x) for x in re.split(r'[\s,]+', root.get('viewBox', '').strip()) if x]
    if len(vb) != 4 or not all(math.isfinite(x) for x in vb) or min(vb[2:]) <= 0:
        raise ValueError('Требуется конечный viewBox с положительными размерами')
    ids = [n.get('id') for n in root.iter() if n.get('id')]
    if len(ids) != len(set(ids)):
        raise ValueError('Дубликат SVG ID')
    # Узкий импорт: inline/inherited styles и локальные defs остаются нативным SVG.
    # Stylesheets не изолированы вложенным viewport, поэтому требуется нормализация.
    for node in root.iter():
        if not isinstance(node.tag, str):
            continue
        tag = ET.QName(node).localname
        if tag in ('script', 'foreignObject', 'style', 'image', 'animate', 'animateTransform', 'set', 'filter'):
            raise ValueError(f'UNSUPPORTED_SVG_FEATURE: {tag}, id={node.get("id", "")}')
        for key, value in node.attrib.items():
            local = ET.QName(key).localname
            if local.lower().startswith('on'):
                raise ValueError('UNSUPPORTED_SVG_FEATURE: event handler')
            if local == 'href' and (not value.startswith('#') or value[1:] not in ids):
                raise ValueError('UNSUPPORTED_SVG_FEATURE: внешняя/неразрешённая ссылка')
            for ref in re.findall(r'url\(\s*[\"\x27]?([^\)\"\x27]+)', value):
                if not ref.startswith('#') or ref[1:] not in ids:
                    raise ValueError('UNSUPPORTED_SVG_FEATURE: неразрешённый url')
    return root, vb, set(ids)


def palette_rows(palette, ids):
    colors = palette.get('colors', {})
    if not colors or any(not re.fullmatch(r'#[0-9a-fA-F]{6}', c) for c in colors):
        raise ValueError('palette.colors: требуется непустая HEX-карта')
    if any(type(n) is not int or n < 1 for n in colors.values()) or len(set(colors.values())) != len(colors):
        raise ValueError('Номера палитры должны быть положительными и уникальными')
    seen = set()
    for zone in palette.get('zones', []):
        zid = zone['zone_id']
        if zid in seen or zid not in ids or not zone.get('color_id'):
            raise ValueError('Неверный/дублированный zone_id или отсутствующий color_id: ' + zid)
        seen.add(zid)
        if zone['color'] not in colors or zone['number'] != colors[zone['color']]:
            raise ValueError('Несогласованная палитра зоны: ' + zid)
    if not seen:
        raise ValueError('palette.zones: нужны явные связи с artwork')
    labels = palette.get('labels', {})
    if set(labels) - set(colors):
        raise ValueError('Название для отсутствующего цвета')
    if any(not isinstance(label, str) for label in labels.values()):
        raise ValueError('Названия цветов должны быть строками')
    return [(c, n, labels.get(c, c.upper())) for c, n in sorted(colors.items(), key=lambda item: item[1])]


def add(parent, tag, attrs, text=None):
    node = ET.SubElement(parent, f'{{{NS}}}{tag}', {k: str(v) for k, v in attrs.items()})
    node.text = text
    return node


def assemble(args):
    layout = load(args.layout)
    if args.title is not None:
        layout['title'] = args.title
    for key, value in [('columns', args.cols), ('swatch_size', args.swatch_size)]:
        if value is not None:
            layout['legend'][key] = value
    validate_layout(layout)
    art, vb, ids = read_artwork(args.artwork)
    rows = palette_rows(load(args.palette), ids)
    if args.tiles_manifest:
        raise ValueError('B→P tiles-manifest ещё не принят; требуется отдельный print workflow')
    outputs = [p.resolve() for p in (args.out_svg, args.out_png, args.out_pdf) if p]
    inputs = {p.resolve() for p in (args.artwork, args.palette, args.layout)}
    if len(outputs) != len(set(outputs)) or set(outputs) & inputs:
        raise ValueError('Выходы должны различаться и не совпадать со входами')
    if args.export_width < 1:
        raise ValueError('export-width должен быть > 0')
    ink = str(args.inkscape.resolve())
    page, panel, legend = layout['page'], layout['artwork_panel'], layout['legend']
    width, height = page['width'], page['height']
    font, fs, sw, gap = [legend[k] for k in ('font_family', 'font_size', 'swatch_size', 'gap')]
    columns = legend['columns']
    column_width = legend['width'] / columns
    text_width = column_width - sw - 3 * gap
    if text_width < fs * 3:
        raise ValueError('Колонки слишком узкие для легенды')
    # Первичное разбиение консервативно; итоговые bbox измеряет настоящий renderer.
    chars = max(3, int(text_width / fs))
    entries = []
    for color, num, label in rows:
        lines = textwrap.wrap(f'{num}  {label}', width=chars, break_long_words=True) or [str(num)]
        entries.append((color, lines, max(sw, len(lines)*fs*1.4) + gap))
    sections = []
    for text in [layout.get('title', ''), layout.get('notes', '')]:
        if text:
            lines = textwrap.wrap(text, width=chars, break_long_words=True)
            sections.append((None, lines, len(lines)*fs*1.4 + gap))
    queue = sections + entries
    pages, text_boxes, swatches = [], [], []
    prefix = '__assembly_'
    while any(i.startswith(prefix) for i in ids):
        prefix = '_' + prefix
    scale = min(panel['width']/vb[2], panel['height']/vb[3])
    tx = panel['x'] + (panel['width']-vb[2]*scale)/2 - vb[0]*scale
    ty = panel['y'] + (panel['height']-vb[3]*scale)/2 - vb[1]*scale
    while queue:
        pi = len(pages)
        root = ET.Element(f'{{{NS}}}svg', nsmap={None: NS}, width=str(width), height=str(height), viewBox=f'0 0 {width} {height}')
        add(root, 'rect', dict(x=0, y=0, width=width, height=height, fill='white'))
        if pi == 0:
            group = add(root, 'g', {'id': prefix+'artwork', 'transform': f'matrix({scale} 0 0 {scale} {tx} {ty})'})
            nested = copy.deepcopy(art)
            for key, value in zip(('x', 'y', 'width', 'height'), vb):
                nested.set(key, str(value))
            nested.set('preserveAspectRatio', 'none')
            group.append(nested)
        placed = 0
        for col in range(columns):
            y = legend['y']
            while queue and y + queue[0][2] <= legend['y'] + legend['height']:
                color, lines, row_height = queue.pop(0)
                x = legend['x'] + col * column_width + gap
                if color:
                    sid = prefix+f'swatch_{pi}_{placed}'
                    add(root, 'rect', dict(id=sid, x=x, y=y, width=sw, height=sw, fill=color, stroke='#999', **{'stroke-width': 0.5}))
                    swatches.append(dict(page=pi+1, color=color, id=sid))
                for line in lines:
                    tid = prefix+f'text_{pi}_{len(text_boxes)}'
                    add(root, 'text', {'id':tid, 'x':x+sw+gap, 'y':y+fs, 'font-size':fs, 'font-family':font, 'fill':'#222'}, line)
                    text_boxes.append(dict(page=pi+1, id=tid, box=[x+sw+gap, y, text_width, fs*1.4], text=line))
                    y += fs*1.4
                y += row_height - len(lines)*fs*1.4
                placed += 1
        if not placed:
            raise ValueError('Элемент легенды выше доступной панели; увеличьте панель или уменьшите шрифт')
        pages.append(root)
    # Измерение и экспорт во временной среде; пользовательские outputs появляются после успешного render.
    manifest_path = args.out_svg.with_suffix('.manifest.json')
    if manifest_path.resolve() in inputs:
        raise ValueError('Manifest совпадает со входом')
    manifest = dict(schema_version=VERSION, source=[str(args.artwork),str(args.palette)], coordinate_domain='P',
                    viewBox=[0,0,width,height], objects=[dict(id=prefix+'artwork', source_viewBox=vb, matrix=[scale,0,0,scale,tx,ty])],
                    provenance=dict(producer='tools/coloring/package_coloring.py', version=VERSION, renderer='native Inkscape'),
                    parameters=layout, warnings=['A→P presentation; физический масштаб изделия не заявлен'],
                    qa_ref='text_bounds в этом manifest; preview требует визуального осмотра', fonts=[font], pages=[], text_bounds=[], swatches=swatches)
    from subprocess import run
    with temporary_environment() as env:
        work = Path(env['TEMP'])
        staged = []
        for i, root in enumerate(pages):
            svg = work / f'page-{i+1}.svg'
            ET.ElementTree(root).write(str(svg), encoding='utf-8', xml_declaration=True)
            query = run([ink,str(svg),'--query-all'], env=env, capture_output=True, encoding='utf-8', timeout=60, check=True)
            bounds = {}
            for line in query.stdout.splitlines():
                parts = line.rsplit(',',4)
                if len(parts) == 5:
                    try:
                        bounds[parts[0]] = [float(v) for v in parts[1:]]
                    except ValueError:
                        pass
            for text in [t for t in text_boxes if t['page'] == i+1]:
                bbox = bounds.get(text['id'])
                x,y,w,h = text['box']
                if bbox is None or bbox[0] < x-1 or bbox[1] < y-1 or bbox[0]+bbox[2] > x+w+1 or bbox[1]+bbox[3] > y+h+1:
                    raise ValueError('Текст не укладывается в колонку: '+text['text'])
                manifest['text_bounds'].append(dict(id=text['id'], page=i+1, bbox=bbox))
            def destination(base):
                return base if i == 0 else base.with_name(base.stem+f'-p{i+1}'+base.suffix)
            svg_dest = destination(args.out_svg)
            staged.append((svg,svg_dest))
            exports = {}
            for kind, target in [('png',args.out_png),('pdf',args.out_pdf)]:
                if target:
                    local = work / f'page-{i+1}.{kind}'
                    cmd = [ink,str(svg),'--export-filename='+str(local)]
                    if kind == 'png':
                        cmd += ['--export-width='+str(args.export_width)]
                    run(cmd, env=env, capture_output=True, encoding='utf-8', timeout=60, check=True)
                    if not local.is_file() or not local.stat().st_size:
                        raise ValueError('Renderer не создал '+kind)
                    dest = destination(target)
                    staged.append((local,dest)); exports[kind]=str(dest)
            manifest['pages'].append(dict(svg=str(svg_dest), exports=exports))
        destinations = [d.resolve() for _,d in staged] + [manifest_path.resolve()]
        if len(set(destinations)) != len(destinations) or set(destinations) & inputs:
            raise ValueError('Коллизия имён выходных страниц/входов')
        for local,dest in staged:
            dest.parent.mkdir(parents=True,exist_ok=True)
            dest.write_bytes(local.read_bytes())
        manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(status='PASS',pages=len(pages),manifest=str(manifest_path)),ensure_ascii=False))


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ('artwork','palette','layout','out-svg'):
        parser.add_argument('--'+option, type=Path, required=True)
    parser.add_argument('--tiles-manifest',type=Path,help='Зарезервировано B→P; текущая версия отклоняет')
    parser.add_argument('--out-png',type=Path)
    parser.add_argument('--out-pdf',type=Path,help='Presentation PDF; физическое 1:1 не заявляется')
    parser.add_argument('--title',help='Заголовок легенды, заменяет layout.title')
    parser.add_argument('--cols',type=int,help='Колонки легенды')
    parser.add_argument('--swatch-size',type=float,help='Размер образца в page units px, не размер тайла')
    parser.add_argument('--export-width',type=int,default=1600,help='Ширина PNG в пикселях, default 1600; геометрию SVG не меняет')
    parser.add_argument('--inkscape',type=Path,default=ROOT/'.tools-graphics/inkscape/bin/inkscape.com',help='Native renderer')
    args = parser.parse_args()
    try:
        assemble(args)
    except (ValueError,KeyError,TypeError,OSError,ET.XMLSyntaxError) as exc:
        parser.exit(2,f'Ошибка компоновки: {exc}\n')


if __name__ == '__main__':
    main()

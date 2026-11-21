"""Развитие mng/Drafts/mosaic_labeler.py: inkex + готовые Shapely/polylabel.

Геометрия и SVG читаются готовыми API. Собственных SVG/Bezier/placement engines нет.
"""
from pathlib import Path
import copy
import hashlib
import json
import math
import os
import subprocess
import sys

ROOT=Path(os.environ.get('MOSAIC_PROJECT_ROOT',Path(__file__).resolve().parents[2]))
sys.path.insert(0,str(ROOT))
from tools.inkscape.runtime import temporary_environment
PY=ROOT/'.venv-graphics/Scripts/python.exe'
if Path(sys.executable).resolve()!=PY.resolve():
    raise SystemExit(subprocess.call([str(PY),str(Path(__file__).resolve()),*sys.argv[1:]],env=dict(os.environ,MOSAIC_PROJECT_ROOT=str(ROOT))))
sys.path.insert(0,str(ROOT/'.tools-graphics/inkscape/share/inkscape/extensions'))
import inkex
import numpy as np
from inkex import bezier
from shapely.geometry import Polygon,LineString,box
from shapely.ops import polygonize,unary_union,polylabel
from shapely import get_parts

INK=ROOT/'.tools-graphics/inkscape/bin/inkscape.com'
GEOMETRY_ATTRIBUTES=('d','x','y','width','height','cx','cy','rx','ry','r','points','transform')

def fingerprint(node):
    return dict(tag=node.tag,geometry={k:node.attrib.get(k) for k in GEOMETRY_ATTRIBUTES},
                ancestors=[p.attrib.get('transform') for p in node.iterancestors()])

def geometry(node,flatness):
    path=node.path.transform(node.composed_transform())
    if not all(p[-1].letter in 'zZ' for p in path.break_apart()):
        raise inkex.AbortExtension('Открытая залитая область: '+str(node.get('id')))
    csp=copy.deepcopy(path.to_superpath());rings=[]
    for sub in csp:
        one=[sub];bezier.cspsubdiv(one,flatness)
        points=[tuple(s[1]) for s in one[0]]
        if len(points)<3:continue
        poly=Polygon(points)
        if not poly.is_valid:raise inkex.AbortExtension('Самопересечение области '+str(node.get('id')))
        if poly.area:rings.append(poly)
    if not rings:raise inkex.AbortExtension('Пустая область '+str(node.get('id')))
    rule=node.specified_style().get('fill-rule','nonzero')
    faces=list(polygonize(unary_union([r.boundary for r in rings])))
    chosen=[]
    for face in faces:
        pt=face.representative_point();inside=[r for r in rings if r.covers(pt)]
        winding=sum(1 if r.exterior.is_ccw else -1 for r in inside)
        if (len(inside)%2 if rule=='evenodd' else winding!=0):chosen.append(face)
    result=unary_union(chosen)
    if result.is_empty or not result.is_valid:raise inkex.AbortExtension('Некорректная топология '+str(node.get('id')))
    return result

def path_from_geometry(geom):
    result=inkex.Path()
    for poly in get_parts(geom):
        for ring in [poly.exterior,*poly.interiors]:
            points=list(ring.coords)
            result.append(inkex.paths.Move(*points[0]))
            for pt in points[1:]:result.append(inkex.paths.Line(*pt))
            result.append(inkex.paths.ZoneClose())
    return result

class MosaicLabeler(inkex.EffectExtension):
    def __init__(self):
        super().__init__()
        for name,default in [('min_area',15.0),('min_width',0.0),('font_size',7.0),('min_font_size',2.0),('stroke_width',0.3),('flatness',0.005)]:
            self.arg_parser.add_argument('--'+name,type=float,default=default)
        self.arg_parser.add_argument('--output_dir',default='')
        self.arg_parser.add_argument('--palette_map',default='')
        self.arg_parser.add_argument('--artwork_manifest',default='')
        self.arg_parser.add_argument('--micro_policy',choices=['keep','flag','merge'],default='flag')
        self.arg_parser.add_argument('--allow_geometry_change',type=inkex.Boolean,default=False)

    def effect(self):
        with temporary_environment() as env:
            self._effect(env)

    def _effect(self,env):
        o=self.options
        # inkex лениво нормализует wrapped transform даже при чтении.
        originals={n:{k:n.attrib.get(k) for k in GEOMETRY_ATTRIBUTES} for n in self.svg.iter() if isinstance(n.tag,str)}
        original_fingerprints={n:fingerprint(n) for n in originals}
        def restore_geometry():
            for n,attrs in originals.items():
                if n is not self.svg and n.getparent() is None:continue
                for key,value in attrs.items():
                    if value is None:n.attrib.pop(key,None)
                    else:n.attrib[key]=value
        if not o.output_dir:raise inkex.AbortExtension('Укажите output_dir для результатов и QA.')
        if not all(math.isfinite(v) and v>0 for v in [o.font_size,o.min_font_size,o.stroke_width,o.flatness]) or o.min_area<0 or o.min_width<0:
            raise inkex.AbortExtension('Размеры/допуски должны быть конечными положительными числами; пороги — неотрицательными.')
        if o.micro_policy=='merge' and not o.allow_geometry_change:
            raise inkex.AbortExtension('Merge требует явного allow_geometry_change=true; preserve_geometry по умолчанию.')
        out=Path(o.output_dir).resolve();out.mkdir(parents=True,exist_ok=True)
        trace=[]
        def write(name,data):
            (out/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        def command(args):
            r=subprocess.run([str(v) for v in args],capture_output=True,text=True,encoding='utf-8',errors='replace',env=env,timeout=60)
            trace.append(dict(args=[str(v) for v in args],code=r.returncode,stdout=r.stdout,stderr=r.stderr));write('commands.json',trace)
            if r.returncode:raise inkex.AbortExtension(r.stderr)
            return r.stdout
        vb=[float(v) for v in self.svg.get('viewBox','').replace(',',' ').split()]
        if not vb and self.svg.get('width') and self.svg.get('height'):
            vb=[0,0,inkex.units.convert_unit(self.svg.get('width'),'px'),inkex.units.convert_unit(self.svg.get('height'),'px')]
            self.svg.set('viewBox',' '.join(f'{v:g}' for v in vb))
        if len(vb)!=4 or min(vb[2:])<=0:raise inkex.AbortExtension('Нужен корректный artwork viewBox.')
        width=inkex.units.convert_unit(self.svg.get('width',str(vb[2])),'px')
        height=inkex.units.convert_unit(self.svg.get('height',str(vb[3])),'px')
        sx,sy=width/vb[2],height/vb[3]
        if abs(sx-sy)>1e-6:raise inkex.AbortExtension('Сначала нормализуйте соотношение viewport/viewBox без искажения геометрии.')
        if self.svg.xpath('//svg:use|//svg:image'):raise inkex.AbortExtension('use/image требуют предварительной явной нормализации.')
        input_file=getattr(o,'input_file',None)
        source=Path(str(getattr(input_file,'name',input_file))) if input_file else None
        source_bytes=source.read_bytes() if source and source.is_file() else inkex.etree.tostring(self.svg)
        source_sha=hashlib.sha256(source_bytes).hexdigest()
        (out/'source.svg').write_bytes(source_bytes)
        regions=[];excluded=[]
        allowed={'path','rect','circle','ellipse','polygon','polyline'}
        for node in self.svg.iter():
            if not isinstance(node,inkex.ShapeElement) or inkex.etree.QName(node).localname not in allowed:continue
            if any(inkex.etree.QName(p).localname in ['defs','clipPath','mask'] for p in node.iterancestors()):continue
            style=node.specified_style()
            if style.get('display')=='none' or style.get('visibility')=='hidden':continue
            for ancestor in [node,*node.iterancestors()]:
                st=ancestor.specified_style()
                if any(st.get(k,'none')!='none' for k in ['clip-path','mask','filter']):
                    raise inkex.AbortExtension('clip/mask/filter требует нормализации: '+str(node.get('id')))
            fill=str(style.get('fill','#000000'))
            if fill=='none':continue
            if fill.startswith('url('):raise inkex.AbortExtension('Градиентная/шаблонная заливка не является одним цветом зоны.')
            if fill=='currentColor':fill=str(style.get('color','#000000'))
            rgba=list(inkex.Color(fill).to_rgba())
            def opacity(v):return float(str(v).rstrip('%'))/(100 if str(v).endswith('%') else 1)
            alpha=rgba[3]*opacity(style.get('fill-opacity',1))
            for ancestor in [node,*node.iterancestors()]:alpha*=opacity(ancestor.cascaded_style().get('opacity',1))
            if alpha<=0:excluded.append(dict(id=node.get('id'),reason='Прозрачная область'));continue
            g=geometry(node,o.flatness)
            rid=node.get('id') or 'zone-'+hashlib.sha256((str(node.path)+fill).encode()).hexdigest()[:12]
            node.set('id',rid)
            rgb=tuple(round(alpha*c+(1-alpha)*255) for c in rgba[:3])
            color='#'+''.join(f'{c:02x}' for c in rgb)
            regions.append(dict(node=node,id=rid,geometry=g,color=color,alpha=alpha,sources=[rid],fingerprint=original_fingerprints[node]))
        if not regions:raise inkex.AbortExtension('Нет видимых залитых областей.')
        if len({r['id'] for r in regions})!=len(regions):raise inkex.AbortExtension('Повторяющиеся ID областей.')
        for i,r in enumerate(regions):
            if r['alpha']<1 and any(r['geometry'].intersection(t['geometry']).area>o.flatness and t['color']!='#ffffff' for t in regions[:i]):
                raise inkex.AbortExtension('Полупрозрачная зона над цветным фоном требует нормализации видимых цветов: '+r['id'])
        before_union=unary_union([r['geometry'] for r in regions]);merges=[];warnings=[]
        def micro(r):
            coords=list(r['geometry'].minimum_rotated_rectangle.exterior.coords)
            narrow=min(math.dist(coords[i],coords[i+1]) for i in range(4))
            return r['geometry'].area<o.min_area or narrow<o.min_width
        if o.micro_policy=='merge':
            if any(r['geometry'].intersection(t['geometry']).area>o.flatness for i,r in enumerate(regions) for t in regions[i+1:]):
                raise inkex.AbortExtension('Merge требует неперекрывающиеся зоны; сначала нормализуйте paint order.')
            for r in sorted(list(regions),key=lambda r:(r['geometry'].area,r['id'])):
                if r not in regions or not micro(r):continue
                adjacent=[t for t in regions if t is not r and r['geometry'].boundary.intersection(t['geometry'].boundary).length>o.flatness]
                same=[t for t in adjacent if t['color']==r['color']]
                adjacent=same or adjacent
                if not adjacent:warnings.append(dict(zone_id=r['id'],reason='Для merge нет смежной зоны; сохранена и отмечена'));continue
                target=max(adjacent,key=lambda t:(r['geometry'].boundary.intersection(t['geometry'].boundary).length,t['id']))
                target['geometry']=target['geometry'].union(r['geometry']);target['sources']+=r['sources']
                target['node'].getparent().remove(target['node']);r['node'].getparent().remove(r['node'])
                node=inkex.PathElement();node.set('id',target['id']);node.path=path_from_geometry(target['geometry'])
                node.style={'fill':target['color'],'fill-rule':'evenodd'};self.svg.append(node);target['node']=node
                merges.append(dict(source=r['id'],target=target['id'],original_color=r['color'],new_color=target['color'],area=r['geometry'].area));regions.remove(r)
        colors=sorted({r['color'] for r in regions})
        palette_file=Path(o.palette_map) if o.palette_map else out/'palette_map.json'
        if o.palette_map and not palette_file.is_file():
            raise inkex.AbortExtension('Переданная карта палитры не найдена: '+str(palette_file))
        numbers=json.loads(palette_file.read_text(encoding='utf-8')).get('colors') if palette_file.exists() else {}
        if (not isinstance(numbers,dict) or any(type(n) is not int or n<1 for n in numbers.values())
                or len(set(numbers.values()))!=len(numbers)):
            raise inkex.AbortExtension('Некорректная карта color → положительный уникальный номер.')
        for color in colors:
            if color not in numbers:numbers[color]=max(numbers.values(),default=0)+1
        source_manifest=Path(o.artwork_manifest) if o.artwork_manifest else (source.parent/'artwork_regions.manifest.json' if source else out/'unused.json')
        known={}
        if o.artwork_manifest and not source_manifest.is_file():
            raise inkex.AbortExtension('Переданный artwork manifest не найден: '+str(source_manifest))
        if source_manifest.exists():known={z['zone_id']:z['color_id'] for z in json.loads(source_manifest.read_text(encoding='utf-8')).get('zones',[])}
        group=inkex.Group();group.set('id','mosaic-labels');self.svg.append(group)
        labels=[];occupied=Polygon()
        for r in reversed(regions):
            r['visible']=r['geometry'].difference(occupied);occupied=occupied.union(r['geometry'])
        for r in regions:
            node=r['node']
            scales=np.linalg.svd(np.asarray(node.composed_transform().matrix)[:,:2],compute_uv=False)
            if scales[-1]<=1e-12:raise inkex.AbortExtension('Вырожденное преобразование: '+r['id'])
            local_width=o.stroke_width/float(scales[0])
            r['stroke_range']=[local_width*float(scales[-1]),o.stroke_width]
            node.style=inkex.Style({'fill':'none','stroke':'#888888','stroke-width':str(local_width),'stroke-linejoin':'round'})
            if micro(r) and o.micro_policy=='flag':warnings.append(dict(zone_id=r['id'],reason='Микрообласть сохранена'))
            if r['visible'].is_empty:
                warnings.append(dict(zone_id=r['id'],reason='Полностью перекрыта; исходная геометрия сохранена'));continue
            for index,component in enumerate(get_parts(r['visible']),1):
                if not isinstance(component,Polygon) or component.area<=0:continue
                point=polylabel(component,tolerance=min(o.flatness,0.01));radius=point.distance(component.boundary)
                font=max(o.min_font_size,min(o.font_size,radius*1.1))
                text=inkex.TextElement();text.set('id',f"label-{r['id']}-{index}");text.set('x',str(point.x));text.set('y',str(point.y))
                text.text=str(numbers[r['color']]);text.style={'font-size':str(font),'font-family':'DejaVu Sans','fill':'#777777','text-anchor':'middle','dominant-baseline':'central'}
                text.set('data-zone-id',r['id']);group.append(text)
                labels.append(dict(element=text,region=r,component=component,anchor=[point.x,point.y],callout=False,font=font))
        # Нормализация только стилей групп, без преобразования контуров.
        for node in [self.svg,*self.svg.xpath('//svg:g')]:
            own=node.cascaded_style()
            if 'opacity' in own and opacity(own['opacity'])>0:
                node.style['opacity']='1'
                if 'opacity' in node.attrib:node.attrib['opacity']='1'
        probe=out/'measurement.svg'
        def measure():
            restore_geometry()
            self.document.write(str(probe),encoding='utf-8',xml_declaration=True)
            values={}
            for line in command([INK,probe,'--query-all']).splitlines():
                row=line.split(',')
                if len(row)==5:
                    try:
                        x,y,w,h=map(float,row[1:]);values[row[0]]=box(vb[0]+x/sx,vb[1]+y/sy,vb[0]+(x+w)/sx,vb[1]+(y+h)/sy)
                    except ValueError:pass
            return values
        boxes=measure();callout_index=0
        for label in labels:
            text=label['element'];inner=label['component'].buffer(-o.stroke_width/2-o.flatness*2)
            for attempt in range(4):
                bb=boxes.get(text.get('id'))
                if bb is not None and inner.covers(bb):break
                if label['font']*0.7>=o.min_font_size:
                    label['font']*=0.7;text.style['font-size']=str(label['font']);boxes=measure();continue
                label['callout']=True;rows=max(1,int(vb[3]/(2*o.min_font_size))-2)
                col,row=divmod(callout_index,rows);callout_index+=1
                x=vb[0]+vb[2]-(3+col*4)*o.min_font_size;y=vb[1]+(2+row*2)*o.min_font_size
                text.set('x',str(x));text.set('y',str(y));text.style['font-size']=str(o.min_font_size);text.set('data-callout','true')
                line=inkex.PathElement();line.set('id','leader-'+text.get('id'))
                line.path=inkex.Path([inkex.paths.Move(*label['anchor']),inkex.paths.Line(x,y)])
                line.style={'fill':'none','stroke':'#888888','stroke-width':str(o.stroke_width)};line.set('data-zone-id',label['region']['id']);group.insert(0,line)
                boxes=measure();break
        restore_geometry()
        final=out/'structural_layout.svg';self.document.write(str(final),encoding='utf-8',xml_declaration=True)
        checks=[];label_data=[];used=[]
        for label in labels:
            key=label['element'].get('id');bb=boxes.get(key);point=label['anchor']
            valid=label['component'].contains(inkex_point_to_shapely(point)) and bb is not None
            if bb is not None:
                valid=valid and (box(vb[0],vb[1],vb[0]+vb[2],vb[1]+vb[3]).covers(bb) if label['callout'] else label['component'].buffer(-o.stroke_width/2-o.flatness*2).covers(bb))
                valid=valid and all(bb.intersection(other).area==0 for other in used);used.append(bb)
            checks.append(valid)
            label_data.append(dict(label_id=key,zone_id=label['region']['id'],number=numbers[label['region']['color']],anchor=point,callout=label['callout'],bbox=list(bb.bounds) if bb is not None else None,valid=valid))
        exact=all(fingerprint(r['node'])==r['fingerprint'] for r in regions) if not merges else False
        conserved=before_union.symmetric_difference(unary_union([r['geometry'] for r in regions])).area
        geometry_ok=exact if not merges else conserved<=o.flatness
        qa=dict(status='PASS' if all(checks) and geometry_ok else 'FAIL',preserve_geometry=not merges,geometry_exact=exact,
                merge_conserved_area_error=conserved,viewBox=vb,regions=len(regions),labels=label_data,warnings=warnings,merges=merges,
                flatness=o.flatness,source_sha256=source_sha,visual='Осмотреть preview_overlay.png отдельно; численный QA не доказывает читаемость всех callouts.')
        qa['stroke_artwork_ranges']={r['id']:r['stroke_range'] for r in regions}
        write('palette_map.json',dict(colors=numbers,zones=[dict(zone_id=r['id'],color_id=known.get(r['id'],'color-'+r['color'][1:]),color=r['color'],number=numbers[r['color']],source_ids=r['sources']) for r in sorted(regions,key=lambda r:r['id'])]))
        write('qa_summary.json',qa)
        command([INK,final,'--export-filename='+str(out/'preview_overlay.png'),'--export-width=1200','--export-background=white','--export-background-opacity=1'])
        write('manifest.json',dict(schema_version='1.0',coordinate_domain='A',
              source=str(source) if source else 'stdin SVG',
              objects=[dict(id=r['id'],zone_id=r['id'],color_id=known.get(r['id'],'color-'+r['color'][1:]),
                            number=numbers[r['color']],source_ids=r['sources']) for r in sorted(regions,key=lambda r:r['id'])],
              provenance=dict(producer='tools/extensions/mosaic_labeler.py',version='1.1',
                              engines='inkex + Shapely + native Inkscape; commands.json'),
              warnings=warnings,qa_ref='qa_summary.json',
              purpose='Бриф 05: контуры и номера художественных зон',source_sha256=source_sha,viewBox=vb,
              output=['structural_layout.svg','palette_map.json','qa_summary.json','preview_overlay.png'],
              method='inkex geometry/styles + Shapely polygonize/polylabel/union + настоящий Inkscape glyph bbox/render',
              parameters=dict(micro_policy=o.micro_policy,min_area=o.min_area,min_width=o.min_width,font_size=o.font_size,min_font_size=o.min_font_size,stroke_width=o.stroke_width,flatness=o.flatness),
              limitations=['PDF/физические единицы не назначаются.','clip/mask/filter/use/gradient требуют явной нормализации.','Полупрозрачное смешение с цветным фоном диагностируется.']))
        if qa['status']!='PASS':raise inkex.AbortExtension('QA не пройден; сохранены отчёт и диагностические результаты.')

def inkex_point_to_shapely(point):
    from shapely.geometry import Point
    return Point(*point)

if __name__=='__main__':
    MosaicLabeler().run()

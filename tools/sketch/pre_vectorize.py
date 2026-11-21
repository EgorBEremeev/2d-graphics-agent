"""Связка готовых raster/trace/SVG операций для художественных зон."""
import argparse
import hashlib
import importlib.metadata as metadata
import json
from pathlib import Path
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

import numpy as np
from PIL import Image,ImageOps
from shapely.geometry import Polygon,box
from shapely.ops import unary_union
import vtracer

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from tools.inkscape.runtime import run_isolated
INK=ROOT/'.tools-graphics/inkscape/bin/inkscape.com'
INKPY=INK.parent/'python.exe'
POT=ROOT/'.tools-graphics/potrace-1.16/potrace.exe'
NS='http://www.w3.org/2000/svg'
ET.register_namespace('',NS)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--role',choices=['silhouette','separators','unknown'],required=True)
    parser.add_argument('--boundary-policy',choices=['nearest-zone'])
    parser.add_argument('--threshold',type=int,default=128)
    parser.add_argument('--max-mismatch',type=float,default=0.01)
    parser.add_argument('--area-tolerance',type=float,default=0.1)
    a=parser.parse_args()
    if not 0<=a.threshold<=255 or not 0<=a.max_mismatch<=1 or a.area_tolerance<0:
        parser.error('Порог/допуск вне диапазона')
    src=a.input.resolve();out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
    original=out/('source.original'+src.suffix.lower())
    if src==original:parser.error('Вход должен находиться отдельно от рабочей копии')
    shutil.copyfile(src,original)
    sha=hashlib.sha256(src.read_bytes()).hexdigest()
    image=ImageOps.exif_transpose(Image.open(src)).convert('RGBA')
    background=Image.new('RGBA',image.size,'white');background.alpha_composite(image)
    image=background.convert('RGB');image.save(out/'source.png')
    w,h=image.size
    trace=[]
    def write(name,value):
        (out/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    def run(args):
        r=run_isolated([str(v) for v in args],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=90)
        trace.append(dict(args=[str(v) for v in args],code=r.returncode,stdout=r.stdout,stderr=r.stderr))
        write('commands.json',trace);r.check_returncode()
        return r.stdout
    def normalize(file):
        data=out/(file.stem+'-geometry.json')
        run([INKPY,ROOT/'tools/sketch/normalize_svg.py',file,data])
        return json.loads(data.read_text(encoding='utf-8'))
    def render(file,name):
        run([INK,file,'--export-filename='+str(out/name),'--export-width='+str(w),'--export-height='+str(h),'--export-background=white','--export-background-opacity=1'])
    def svg(name,paths):
        doc=ET.Element('{'+NS+'}svg',{'width':str(w),'height':str(h),'viewBox':f'0 0 {w} {h}'})
        for i,p in enumerate(paths,1):
            ET.SubElement(doc,'{'+NS+'}path',{'id':p.get('id',f'zone-{i:03}'),'d':p['d'],'fill':p['fill'],'fill-rule':'evenodd'})
        ET.ElementTree(doc).write(out/name,encoding='utf-8',xml_declaration=True)
    def review(reason):
        if (out/'artwork_regions.svg').exists():
            raise RuntimeError('Для неоднозначного нового режима выберите чистый каталог; прежний принятый SVG сохранён.')
        report=dict(status='NEEDS_REVIEW',reason=reason,role=a.role,viewBox=[0,0,w,h])
        write('qa_summary.json',report)
        write('manifest.json',dict(purpose='Разбор неоднозначного эскиза без выдуманной геометрии',source=str(src),sha256=sha,qa=report,outputs=['source.png','qa_summary.json']))
        print(json.dumps(report,ensure_ascii=False));return 3
    if a.role=='unknown':return review('Нужно определить, являются ли линии материалом, разделителями или декором.')
    native_versions=dict(Inkscape=run([INK,'--version']).strip(),Potrace=run([POT,'--version']).splitlines()[0])
    black=np.asarray(image.convert('L'))<a.threshold
    binary=Image.fromarray(np.where(black,0,255).astype('uint8'))
    binary.convert('1').save(out/'mask.pbm')
    binary.save(out/'mask.png')
    candidates=[]
    if a.role=='silhouette':
        run([POT,out/'mask.pbm','--svg','--output',out/'potrace.svg','--turdsize','0','--alphamax','0','--opttolerance','0'])
        vtracer.convert_image_to_svg_py(str(out/'mask.png'),str(out/'vtracer.svg'),colormode='binary',mode='polygon',filter_speckle=0)
        trace.append(dict(api='vtracer.convert_image_to_svg_py',input='mask.png',output='vtracer.svg',colormode='binary',mode='polygon',filter_speckle=0))
        for name in ['potrace','vtracer']:
            paths=normalize(out/(name+'.svg'))
            paths=[dict(p,fill='#000000') for p in paths]
            svg(name+'-normalized.svg',paths)
            render(out/(name+'-normalized.svg'),name+'.png')
            mask=np.asarray(Image.open(out/(name+'.png')).convert('L'))<128
            candidates.append(dict(tool=name,mismatch=float(np.mean(mask!=black)),paths=len(paths)))
        chosen=min(candidates,key=lambda c:(c['mismatch'],c['paths'],c['tool']!='potrace'))
        dark=normalize(out/(chosen['tool']+'-normalized.svg'))
        # Готовый Boolean создаёт белые компоненты, сохраняя отверстия.
        compound=' '.join(p['d'] for p in dark)
        svg('white-input.svg',[dict(id='frame',d=f'M0 0H{w}V{h}H0Z',fill='#ffffff'),dict(id='ink',d=compound,fill='#000000')])
        run([INK,out/'white-input.svg','--actions=select-by-id:frame,ink;path-difference;path-split;export-filename:'+str(out/'white.svg')+';export-do'])
        white=[dict(p,fill='#ffffff') for p in normalize(out/'white.svg')]
        paths=white+[dict(p,fill='#000000') for p in dark]
    else:
        if a.boundary_policy!='nearest-zone':return review('Для разделителей нужно явное правило прохождения границы через толщину штриха.')
        from scipy import ndimage
        labels,count=ndimage.label(~black)
        if count<2:return review('Линии не отделяют замкнутую внутреннюю область; автоматическое замыкание не разрешено.')
        nearest=ndimage.distance_transform_edt(labels==0,return_distances=False,return_indices=True)
        labels=labels[tuple(nearest)]
        # Сегментация готовым scipy; векторизует готовый VTracer, не проектный алгоритм.
        colors={i:((i*67)%200+25,(i*97)%200+25,(i*131)%200+25) for i in range(1,count+1)}
        colored=np.zeros((h,w,3),dtype=np.uint8)
        for i,color in colors.items():colored[labels==i]=color
        Image.fromarray(colored).save(out/'segmented.png')
        vtracer.convert_image_to_svg_py(str(out/'segmented.png'),str(out/'segmented.svg'),colormode='color',hierarchical='cutout',mode='polygon',filter_speckle=0,color_precision=8,layer_difference=1)
        trace.append(dict(api='vtracer.convert_image_to_svg_py',input='segmented.png',output='segmented.svg',colormode='color',hierarchical='cutout',mode='polygon',filter_speckle=0))
        paths=normalize(out/'segmented.svg');chosen=dict(tool='scipy labels → VTracer cutout')
    # Устойчивый порядок зон; цвета не объединяют отдельные компоненты.
    def geometry(p):
        g=Polygon()
        for ring in p['rings']:
            if len(ring)>=3:g=g.symmetric_difference(Polygon(ring))
        return g
    pairs=sorted([(p,geometry(p)) for p in paths],key=lambda pg:(pg[0]['fill'],*pg[1].bounds))
    paths=[dict(p,id=f'zone-{i:03}') for i,(p,g) in enumerate(pairs,1)]
    svg('artwork_regions.svg',paths)
    render(out/'artwork_regions.svg','preview.png')
    # Проверка сохранённого файла независимо от сборки DOM.
    saved=normalize(out/'artwork_regions.svg')
    geoms=[geometry(p) for p in saved]
    overlap=sum(x.intersection(y).area for i,x in enumerate(geoms) for y in geoms[i+1:])
    coverage=unary_union(geoms).symmetric_difference(box(0,0,w,h)).area
    checks=dict(closed=all(p['closed'] for p in saved),valid=all(g.is_valid for g in geoms),
                coverage=coverage<=a.area_tolerance,overlap=overlap<=a.area_tolerance,
                image_coordinates=True)
    if a.role=='silhouette':
        final=np.asarray(Image.open(out/'preview.png').convert('L'))<128
        checks['mask_mismatch']=float(np.mean(final!=black))<=a.max_mismatch
    else:
        final=np.asarray(Image.open(out/'preview.png').convert('RGB'))
        checks['segmentation_mismatch']=float(np.mean(np.any(final!=colored,axis=2)))<=a.max_mismatch
    # Overlay границ, а не ложная разница условных цветов зон и чёрных штрихов.
    contour=ET.parse(out/'artwork_regions.svg')
    for node in contour.getroot():
        node.set('fill','none');node.set('stroke','#000000');node.set('stroke-width','0.4')
    contour.write(out/'contours.svg',encoding='utf-8',xml_declaration=True)
    render(out/'contours.svg','contours.png')
    edge=Image.open(out/'contours.png').convert('L').point(lambda n:255 if n<220 else 0)
    overlay=image.copy();overlay.paste(Image.new('RGB',(w,h),'red'),mask=edge)
    overlay.save(out/'preview_overlay.png')
    qa=dict(status='PASS' if all(checks.values()) else 'FAIL',checks=checks,regions=len(paths),
            overlap_area=overlap,uncovered_or_external_area=coverage,candidates=candidates,chosen=chosen,
            max_mismatch=a.max_mismatch,area_tolerance=a.area_tolerance,
            visual='Требуется осмотр preview_overlay.png; численный PASS не заменяет семантическую оценку.')
    write('qa_summary.json',qa)
    palette={c:f'color-{i:03}' for i,c in enumerate(sorted({p['fill'] for p in paths}),1)}
    manifest=dict(domain='artwork',source=dict(path=str(src),sha256=sha),image_size=[w,h],viewBox=[0,0,w,h],
                  artwork_to_image=[1,0,0,1,0,0],line_role=a.role,boundary_policy=a.boundary_policy,
                  parameters=dict(threshold=a.threshold,max_mismatch=a.max_mismatch,area_tolerance=a.area_tolerance),
                  zones=[dict(zone_id=p['id'],color_id=palette[p['fill']],fill=p['fill']) for p in paths],
                  palette=palette,tools={n:metadata.version(n) for n in ['pillow','vtracer','shapely']},
                  native_versions=native_versions,coordinate_reference='source.png после отображения EXIF; source.original сохраняет исходные байты',
                  ambiguities=[],qa=qa)
    manifest.update(schema_version='1.0', coordinate_domain='A',
                    image_to_artwork=[1,0,0,1,0,0],
                    objects=[dict(id=z['zone_id'], **z) for z in manifest['zones']],
                    provenance=dict(producer='tools/sketch/pre_vectorize.py', version='1.1',
                                    engines=manifest['tools'], native_versions=native_versions),
                    workflow=dict(role=a.role, trace=chosen['tool'],
                                  stages=['Pillow mask', 'Potrace/VTracer', 'native SVG normalization', 'visible regions']),
                    warnings=[], qa_ref='qa_summary.json')
    write('artwork_regions.manifest.json',manifest)
    write('manifest.json',dict(purpose='Подготовка художественных зон из эскиза',source=manifest['source'],
                              outputs=['artwork_regions.svg','artwork_regions.manifest.json','qa_summary.json','preview_overlay.png'],
                              limitations=['Физические размеры, плитки, швы и PDF не назначаются.','Role и boundary-policy — семантические параметры, их выбор требует осмотра источника.']))
    print(json.dumps(qa,ensure_ascii=False));return 0 if qa['status']=='PASS' else 2

if __name__=='__main__':
    sys.exit(main())

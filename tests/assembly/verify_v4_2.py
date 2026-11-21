"""A4 presentation export и адресные отказы; прежняя сложная легенда переиспользуется."""
import argparse
import copy
import json
from pathlib import Path
import subprocess
import sys
import fitz
from lxml import etree as ET

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tests/agent'))
from validate_contracts import validate
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True)
a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
cli=ROOT/'tools/coloring/package_coloring.py';source=ROOT/'tests/fixtures/assembly/three-colors.svg'
width,height=210*96/25.4,297*96/25.4
layout=json.loads((ROOT/'tools/coloring/layout.example.json').read_text(encoding='utf-8'))
layout.update(page=dict(width=width,height=height,unit='px',margin=30),
              artwork_panel=dict(x=30,y=30,width=width-60,height=500,fit='contain'),
              legend=dict(x=30,y=600,width=width-60,height=450,columns=2,swatch_size=24,font_size=18,font_family='DejaVu Sans',gap=10),
              title='Палитра контрольной схемы',notes='Художественный лист A4. Масштаб изделия не задан.')
palette=dict(colors={'#c03030':1,'#3050c0':2,'#e5ba30':3},labels={'#c03030':'Красный','#3050c0':'Синий','#e5ba30':'Золотистый'},
             zones=[dict(zone_id=z,color_id=z,color=c,number=n) for z,c,n in [('red','#c03030',1),('blue','#3050c0',2),('yellow','#e5ba30',3)]])
def write(name,data):
    path=a.out/name;path.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8');return path
lp=write('layout.json',layout);pp=write('palette.json',palette);original=source.read_bytes();palette_bytes=pp.read_bytes()
command=[sys.executable,'-X','utf8',str(cli),'--artwork',str(source),'--palette',str(pp),'--layout',str(lp),
         '--out-svg',str(a.out/'sheet.svg'),'--out-png',str(a.out/'preview.png'),'--out-pdf',str(a.out/'sheet.pdf'),'--export-width','1000']
r=subprocess.run(command,capture_output=True,text=True,encoding='utf-8');assert r.returncode==0,r.stderr
assert source.read_bytes()==original and pp.read_bytes()==palette_bytes
manifest=json.loads((a.out/'sheet.manifest.json').read_text(encoding='utf-8'));assert validate(manifest)=='envelope-1.0/P'
assert len(manifest['pages'])==1 and len(manifest['swatches'])==3
result=ET.parse(str(a.out/'sheet.svg'));src=ET.fromstring(original)
for node in src.iter():
    if node.get('id'):
        saved=result.xpath('//*[@id=$id]',id=node.get('id'));assert len(saved)==1 and dict(saved[0].attrib)==dict(node.attrib)
with fitz.open(a.out/'sheet.pdf') as doc:
    assert len(doc)==1
    page=doc[0];mm=[page.rect.width*25.4/72,page.rect.height*25.4/72]
    assert abs(mm[0]-210)<0.02 and abs(mm[1]-297)<0.02,mm
    assert 'Красный' in page.get_text() and 'Золотистый' in page.get_text()
    page.get_pixmap(matrix=fitz.Matrix(1.5,1.5)).save(a.out/'pdf-preview.png')
negative=[]
for name in ['missing-color-id','invalid-layout','duplicate-id']:
    art,pat,lay=source,pp,lp
    if name=='missing-color-id':
        bad=copy.deepcopy(palette);del bad['zones'][0]['color_id'];pat=write('invalid-palette.json',bad)
    elif name=='invalid-layout':
        bad=copy.deepcopy(layout);bad['legend']['y']=30;lay=write('invalid-layout.json',bad)
    else:
        art=a.out/'duplicate.svg';art.write_bytes(original.replace(b'id="blue"',b'id="red"'))
    r=subprocess.run([sys.executable,'-X','utf8',str(cli),'--artwork',str(art),'--palette',str(pat),'--layout',str(lay),'--out-svg',str(a.out/f'{name}.svg')],capture_output=True,text=True,encoding='utf-8')
    assert r.returncode==2 and not (a.out/f'{name}.svg').exists(),(name,r.stderr)
    negative.append(dict(case=name,status='PASS',error=r.stderr.strip()))
report=dict(status='PASS',command=command,svg_source_preserved=True,swatches=3,pdf_page_mm=mm,negative=negative,
            visual='UNPROVEN до осмотра SVG preview и PDF render',scope='A→P presentation; не масштаб изделия 1:1')
write('qa.json',report);print(json.dumps(report,ensure_ascii=False))

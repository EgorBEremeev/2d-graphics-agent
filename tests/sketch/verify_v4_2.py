"""Адресная приёмка envelope и криволинейного повтора после изменения manifest writer."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
from lxml import etree as ET
import numpy as np
from PIL import Image
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.inkscape.runtime import run_isolated
sys.path.insert(0, str(ROOT/'tests/agent'))
from validate_contracts import validate

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--out',type=Path,required=True)
p.add_argument('--verify-only',action='store_true',help='Проверить сохранённые результаты без повторного pipeline')
a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
results=[]
for name in ['A','curve']:
    source=a.out/(name+'.png')
    out=a.out/name
    if not a.verify_only:
        r=run_isolated([str(ROOT/'.tools-graphics/inkscape/bin/inkscape.com'),str(ROOT/'tests/fixtures/sketch'/f'{name}.svg'),
                        '--export-filename='+str(source)],capture_output=True)
        assert r.returncode==0
        r=subprocess.run([sys.executable,'-X','utf8',str(ROOT/'tools/sketch/pre_vectorize.py'),str(source),'--output',str(out),'--role','silhouette'],capture_output=True,text=True,encoding='utf-8')
        assert r.returncode==0,r.stderr
    data=json.loads((out/'artwork_regions.manifest.json').read_text(encoding='utf-8'))
    assert validate(data)=='envelope-1.0/A'
    assert data['image_to_artwork']==data['artwork_to_image']==[1,0,0,1,0,0]
    assert [z['id'] for z in data['objects']]==[z['zone_id'] for z in data['zones']]
    assert data['qa']['regions']==(5 if name=='A' else 4)
    assert data['qa']['status']=='PASS'
    svg=ET.parse(str(out/'artwork_regions.svg'))
    if name=='curve':
        black=svg.xpath('//*[local-name()="path" and @fill="#000000"]')
        assert len(black)==3
        original=np.asarray(Image.open(source).convert('L'))<128
        rendered=np.asarray(Image.open(out/'preview.png').convert('L'))<128
        first=original ^ ndimage.binary_erosion(original)
        second=rendered ^ ndimage.binary_erosion(rendered)
        edge_error=max(float(ndimage.distance_transform_edt(~first)[second].max()),
                       float(ndimage.distance_transform_edt(~second)[first].max()))
        assert edge_error<=1.5,edge_error
        node_counts=[len(node.get('d')) for node in black]
    else: node_counts=[];edge_error=0
    results.append(dict(case=name,status='PASS',regions=len(data['zones']),curve_path_lengths=node_counts,max_edge_error_px=edge_error,
                        mismatch=data['qa']['chosen']['mismatch'],contract='envelope-1.0/A'))
(a.out/'qa.json').write_text(json.dumps(dict(status='PASS',cases=results,visual='UNPROVEN до осмотра overlay'),ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(results,ensure_ascii=False))

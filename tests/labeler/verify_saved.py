"""Независимые инварианты сохранённого SVG: исходные атрибуты, ID, номера."""
import argparse
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as E

GEOM=('d','x','y','width','height','cx','cy','rx','ry','r','points','transform')
def saved_geometry(path):
    root=E.parse(path).getroot();result={}
    def visit(node,parents):
        if node.tag.rsplit('}',1)[-1] in ('path','rect','circle','ellipse','polygon','polyline') and node.get('id'):
            result[node.get('id')]=(node.tag,{k:node.get(k) for k in GEOM},parents)
        for child in node:visit(child,parents+[node.get('transform')])
    visit(root,[])
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    before=saved_geometry(a.source);after=saved_geometry(a.output)
    assert all(after.get(k)==v for k,v in before.items()),'Сохранённая геометрия/цепочка предков изменилась'
    source=E.parse(a.source).getroot();svg=E.parse(a.output).getroot()
    if source.get('viewBox'):assert source.get('viewBox')==svg.get('viewBox')
    ids=[n.get('id') for n in svg.iter() if n.get('id')];assert len(ids)==len(set(ids))
    palette=json.loads((a.output.parent/'palette_map.json').read_text(encoding='utf-8'))
    zones={z['zone_id']:z['number'] for z in palette['zones']}
    labels=[n for n in svg.iter() if n.tag.endswith('}text') and n.get('data-zone-id')]
    assert labels and all(''.join(n.itertext())==str(zones[n.get('data-zone-id')]) for n in labels)
    report=dict(status='PASS',preserved_input_ids=sorted(before),unique_ids=len(ids),labels=len(labels),
                source_sha256=hashlib.sha256(a.source.read_bytes()).hexdigest(),output_sha256=hashlib.sha256(a.output.read_bytes()).hexdigest(),
                limitations=['Геометрические атрибуты и номера проверены независимо; визуальная читаемость отдельно.'])
    (a.output.parent/'independent-qa.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))

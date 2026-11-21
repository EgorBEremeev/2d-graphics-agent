"""Нормализация результата трассировщика готовым inkex, не SVG-парсер проекта."""
import argparse
import copy
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'.tools-graphics/inkscape/share/inkscape/extensions'))
import inkex
from inkex import bezier

p=argparse.ArgumentParser()
p.add_argument('source',type=Path)
p.add_argument('output',type=Path)
p.add_argument('--flatness',type=float,default=0.005)
a=p.parse_args()
root=inkex.load_svg(str(a.source)).getroot()
result=[]
for node in root.xpath('//svg:path'):
    style=node.specified_style()
    color=str(style.get('fill','#000000'))
    if color=='none':continue
    path=node.path.transform(node.composed_transform())
    csp=copy.deepcopy(path.to_superpath())
    rings=[]
    for sub in csp:
        one=[sub]
        bezier.cspsubdiv(one,a.flatness)
        rings.append([list(s[1]) for s in one[0]])
    result.append(dict(source_id=node.get('id'),d=str(path),fill=color,
                       closed=all(sub[-1].letter in 'zZ' for sub in path.break_apart()),rings=rings))
a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

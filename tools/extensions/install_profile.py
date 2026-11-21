"""Установка только в отдельный профиль внутри проекта и проверка Inkscape."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
p=argparse.ArgumentParser();p.add_argument('--profile',type=Path,required=True);a=p.parse_args()
profile=a.profile.resolve()
if not profile.is_relative_to(ROOT):p.error('Профиль должен быть внутри текущего проекта.')
ext=profile/'extensions';ext.mkdir(parents=True,exist_ok=True)
shutil.copyfile(ROOT/'tools/extensions/mosaic_labeler.inx',ext/'mosaic_labeler.inx')
target=ROOT/'tools/extensions/mosaic_labeler.py'
(ext/'mosaic_labeler.py').write_text('import runpy\nrunpy.run_path('+repr(str(target))+", run_name='__main__')\n",encoding='utf-8')
sys.path.insert(0,str(ROOT/'.tools-graphics/inkscape/share/inkscape/extensions'))
from lxml import etree
schema=etree.RelaxNG(etree.parse(str(ROOT/'.tools-graphics/inkscape/share/inkscape/extensions/inkex/tester/inkscape.extension.rng')))
schema.assertValid(etree.parse(str(ext/'mosaic_labeler.inx')))
env=dict(os.environ,INKSCAPE_PROFILE_DIR=str(profile))
r=subprocess.run([str(ROOT/'.tools-graphics/inkscape/bin/inkscape.com'),'--user-data-directory'],capture_output=True,text=True,encoding='utf-8',env=env)
assert r.returncode==0 and Path(r.stdout.strip()).resolve()==profile,(r.stdout,r.stderr)
print(json.dumps(dict(profile=str(profile),schema='PASS',inkscape_profile=r.stdout.strip(),entry=str(ext/'mosaic_labeler.py')),ensure_ascii=False))

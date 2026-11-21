"""Адресная проверка envelope и обязательности явно переданных карт labeler."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
from verify_saved import saved_geometry

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tests/agent'))
from validate_contracts import validate
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True)
a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
cli=ROOT/'tools/extensions/mosaic_labeler.py';fix=ROOT/'tests/fixtures/labeler'
results=[]

def run(name,fixture,extra=(),success=True):
    out=a.out/name
    r=subprocess.run([sys.executable,'-X','utf8',str(cli),str(fix/fixture),'--output_dir',str(out),
                      '--output',str(out/'structural_layout.svg'),*map(str,extra)],capture_output=True,text=True,encoding='utf-8',errors='replace')
    assert (r.returncode==0)==success,(name,r.stderr)
    if success:
        manifest=json.loads((out/'manifest.json').read_text(encoding='utf-8'))
        assert validate(manifest)=='envelope-1.0/A'
        qa=json.loads((out/'qa_summary.json').read_text(encoding='utf-8'))
        assert qa['status']=='PASS' and qa['geometry_exact'] and all(x['valid'] for x in qa['labels'])
        before,after=saved_geometry(fix/fixture),saved_geometry(out/'structural_layout.svg')
        assert all(after.get(k)==v for k,v in before.items())
        results.append(dict(case=name,status='PASS',regions=qa['regions'],labels=len(qa['labels'])))
        return json.loads((out/'palette_map.json').read_text(encoding='utf-8'))
    assert not (out/'palette_map.json').exists()
    results.append(dict(case=name,status='PASS',expected_failure=r.stderr.strip()))

run('colors','colors.svg')
palette=a.out/'provided.json';palette.write_text(json.dumps({'colors':{'#72ba84':41}}),encoding='utf-8');before=palette.read_bytes()
mapped=run('mapped-complex','complex.svg',['--palette_map',palette,'--min_font_size','4'])
assert mapped['colors']['#72ba84']==41 and palette.read_bytes()==before
run('missing-map','colors.svg',['--palette_map',a.out/'does-not-exist.json'],False)
bad=a.out/'boolean-number.json';bad.write_text('{"colors":{"#ff0000":true}}',encoding='utf-8')
run('boolean-number','colors.svg',['--palette_map',bad],False)
run('missing-manifest','colors.svg',['--artwork_manifest',a.out/'missing-artwork.json'],False)
(a.out/'qa.json').write_text(json.dumps(dict(status='PASS',cases=results,visual='UNPROVEN до осмотра previews'),ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(results,ensure_ascii=False))

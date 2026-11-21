"""Проверка жизненного цикла служебных файлов, без оценки графических алгоритмов."""
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from tools.inkscape.runtime import temporary_environment,CACHE

try:
    with temporary_environment() as env:
        temporary=Path(env['TEMP']).parent
        Path(env['INKSCAPE_PROFILE_DIR']).mkdir()
        raise RuntimeError('Проверка очистки после исключения')
except RuntimeError:
    pass
assert not temporary.exists()
for fixture,success in [('colors.svg',True),('unsupported.svg',False)]:
    with temporary_environment() as env:
        work=Path(env['TEMP']).parent;out=work/'output'
        result=subprocess.run([sys.executable,str(ROOT/'tools/extensions/mosaic_labeler.py'),
                               str(ROOT/'tests/fixtures/labeler'/fixture),'--output_dir',str(out),
                               '--output',str(out/'structural_layout.svg')],env=env,
                              capture_output=True,text=True,encoding='utf-8',errors='replace')
        assert (result.returncode==0)==success,(fixture,result.stderr)
        assert not (out/'profile').exists()
    assert not work.exists()
assert not list((ROOT/'artifacts').rglob('preferences.xml'))
assert not list(CACHE.iterdir())
print('PASS: после успеха, ошибки CLI и исключения временные каталоги удалены; artifacts без служебных профилей.')

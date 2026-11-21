"""Временная среда Inkscape с очисткой после операции, включая ошибку."""
from contextlib import contextmanager
import os
from pathlib import Path
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[2]
CACHE=ROOT/'.cache/graphics'

@contextmanager
def temporary_environment(base=None):
    CACHE.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='inkscape-',dir=CACHE) as folder:
        work=Path(folder);tmp=work/'tmp';tmp.mkdir()
        yield dict(os.environ if base is None else base,
                   INKSCAPE_PROFILE_DIR=str(work/'profile'),TEMP=str(tmp),TMP=str(tmp))

def run_isolated(args,*,env=None,**kwargs):
    with temporary_environment(env) as runtime:
        return subprocess.run(args,env=runtime,**kwargs)

"""Вызов нативного Inkscape с временным профилем и проверкой экспорта."""
import os
from pathlib import Path
import shutil
import subprocess

from tools.inkscape.runtime import run_isolated

ROOT = Path(__file__).resolve().parents[2]


def find_inkscape(explicit=None):
    local = ROOT / ".tools-graphics/inkscape/bin/inkscape.com"
    program = explicit or os.environ.get("INKSCAPE_BIN")
    if not program:
        program = local if local.is_file() else "inkscape"
    program = str(program)
    path = Path(program).expanduser()
    if path.is_file():
        return str(path.resolve())
    found = shutil.which(program)
    if found:
        return str(Path(found).resolve())
    raise FileNotFoundError("Укажите исполняемый файл Inkscape через --inkscape или INKSCAPE_BIN")


def export(inkscape, source, output, *options, env=None):
    if not source.is_file():
        raise FileNotFoundError(source)
    if output.exists():
        raise FileExistsError(output)
    command = [inkscape, str(source.resolve()), *options, f"--export-filename={output.resolve()}"]
    kwargs = dict(capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
    result = (
        run_isolated(command, **kwargs) if env is None
        else subprocess.run(command, env=env, **kwargs)
    )
    if result.returncode or not output.is_file() or not output.stat().st_size:
        raise RuntimeError(f"Экспорт Inkscape завершился без результата ({result.returncode}): {result.stderr.strip()}")

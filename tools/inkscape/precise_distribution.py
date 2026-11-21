"""Передаёт допуск готовому расширению Inkscape, сохраняя его алгоритмы."""
from pathlib import Path
import math
import os
import sys

ROOT = Path(__file__).resolve().parents[2]
EXT = Path(os.environ.get('INKSCAPE_EXTENSIONS_DIR', ROOT/'.tools-graphics/inkscape/share/inkscape/extensions'))
sys.path.insert(0, str(EXT))
import inkex
from distribute_along_path import DistributeAlongPath
from pathmodifier import Diffeo


class PreciseDistribution(DistributeAlongPath):
    def __init__(self):
        super().__init__()
        self.arg_parser.add_argument('--linearization-tolerance', type=float, default=1e-9,
                                     help='Допуск штатного Diffeo.linearize; положительное конечное число')

    def linearize(self, path, tolerance=None):
        value = self.options.linearization_tolerance
        if not math.isfinite(value) or value <= 0:
            raise inkex.AbortExtension('Допуск должен быть положительным конечным числом')
        return Diffeo.linearize(path, tolerance=value)


if __name__ == '__main__':
    PreciseDistribution().run()

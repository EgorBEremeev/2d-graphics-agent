# Инструменты 2D Graphics Agent

Фактическая подготовленная среда записывается в [карте среды](../docs/environment/2d-environment.md); общая подготовка описана в [setup](../docs/environment/setup.md). Для подробностей о поддержанных операциях открой соответствующую строку [матрицы](../docs/agent/capability-matrix.md).

| Операция | Рабочая точка входа |
|---|---|
| Синхронизировать D/O | [agent/sync_instructions.py](agent/sync_instructions.py) |
| Трассировать контрастный эскиз | [sketch/pre_vectorize.py](sketch/pre_vectorize.py) и [навык](../.agents/skills/sketch-mosaic-pre-vectorizer/SKILL.md) |
| Пронумеровать готовые SVG-зоны | [extensions/mosaic_labeler.py](extensions/mosaic_labeler.py) и [навык](../.agents/skills/inkscape-cli-mosaic-labeler/SKILL.md) |
| Собрать лист с палитрой и легендой | [coloring/package_coloring.py](coloring/package_coloring.py) и [навык](../.agents/skills/document-assembly/SKILL.md) |
| Изогнуть полосу по эллипсу или распределить объекты по кривой | [inkscape/bend_ellipse.py](inkscape/bend_ellipse.py) · [inkscape/precise_distribution.py](inkscape/precise_distribution.py) |
| Разместить страницы SVG на PDF-листах 1:1 | [printing/svg_1to1_pdf.py](printing/svg_1to1_pdf.py) с `source.svg --output result.pdf --page-mm 297 210 --margin-mm 10` |
| Разбить рисунок заданной ширины на листы | [printing/svg_poster_pdf.py](printing/svg_poster_pdf.py) с обязательным `--font-file <TTF>` |

Печатная утилита принимает один или несколько SVG с физическими `width` и `height` и один новый путь PDF. Каждый SVG даёт одну страницу, центральная обрезка требует `--crop`. Фактическую печать оценивай по контрольному отпечатку. Утилита `svg_1to1_pdf.py` ищет Inkscape через `--inkscape`, `INKSCAPE_BIN`, локальную установку или PATH; poster использует проектный `.tools-graphics/inkscape/bin/inkscape.com`. Обе запускаются из графического venv.

## Требования переносимых модулей

Это требования конкретных маршрутов, а не обязательная установка для любой задачи. Закреплённые версии пакетов и их транзитивных зависимостей находятся в [requirements-graphics.txt](../requirements-graphics.txt); plotter использует отдельный [requirements-plotter.txt](../requirements-plotter.txt). Исполнитель подготовки проверяет совместимость выбранной поставки и фактические версии, затем записывает результат в карту среды.

| Модуль или возможность | Необходимые средства, ресурсы и размещение |
|---|---|
| Синхронизация D/O | Python со стандартной библиотекой; каноны и `.codex/config.toml` остаются по существующим путям. |
| Native SVG и рендер | Полная официальная поставка [Inkscape](https://inkscape.org/release/) (GPL-2.0-or-later) с ресурсами и DLL; проектная точка входа `.tools-graphics/inkscape/bin/inkscape.com`. `native.py` допускает также явный `--inkscape`, `INKSCAPE_BIN` и PATH. |
| Трассировка | `pre_vectorize.py` использует проектный Python 3.12 в `.venv-graphics`, NumPy, Pillow, Shapely, VTracer, Inkscape и [Potrace](https://potrace.sourceforge.net/) (GPL-2.0-or-later) по `.tools-graphics/potrace-1.16/potrace.exe`. Для нормализации нужны входящие в поставку Inkscape `bin/python.exe` и `share/inkscape/extensions`; встроенный Python не смешивается с пакетами venv. VTracer — [официальный проект](https://github.com/visioncortex/vtracer), MIT. |
| Нумерация | `mosaic_labeler.py` использует `.venv-graphics/Scripts/python.exe`, Inkscape и поставляемый им inkex из `.tools-graphics/inkscape/share/inkscape/extensions`; в venv нужны lxml, cssselect, scour, six, NumPy и Shapely. Для предусмотренного шрифта DejaVu Sans — [официальный источник](https://dejavu-fonts.github.io/) и [лицензия](https://dejavu-fonts.github.io/License.html); шрифт подбирается по задаче. |
| Установка расширения | Только по запросу: проектный Python с lxml, полная поставка Inkscape и `tools/extensions/install_profile.py --profile <абсолютный-путь-в-проекте>`. Рекомендуемый постоянный профиль — `.tools-graphics/inkscape-mosaic-profile`; установка в пользовательский AppData не требуется. |
| Компоновка | Python 3.12 и lxml; для preview/export — Inkscape по проектному пути либо явно через `--inkscape`. Шрифт определяется входным layout, пригодность для текста проверяется на итоговом preview. Для отдельной проверки PDF нужен PyMuPDF. |
| Распределение и изгиб | Python и зависимости inkex из закреплённых requirements, полная поставка Inkscape со штатными `distribute_along_path`, `pathmodifier` и `patternalongpath` в `.tools-graphics/inkscape/share/inkscape/extensions`. `precise_distribution.py` учитывает `INKSCAPE_EXTENSIONS_DIR`; `bend_ellipse.py` использует проектный путь. |
| Выпуск 1:1 | `svg_1to1_pdf.py`: Python, defusedxml, PyMuPDF и совместимый Inkscape. `svg_poster_pdf.py`: Python, PyMuPDF, Pillow, проектный Inkscape и выбранный TTF через обязательный `--font-file`. [PyMuPDF](https://pymupdf.readthedocs.io/) распространяется на условиях AGPL/commercial; применимость лицензии следует проверить. |
| Геометрия/CAD и plotter | Для соответствующей задачи ezdxf и Shapely — в графическом venv; vpype и rectpack — в отдельном `.venv-graphics/plotter` из plotter requirements. Источники: [ezdxf](https://github.com/mozman/ezdxf) (MIT), [Shapely](https://github.com/shapely/shapely) (BSD-3-Clause), [vpype](https://github.com/abey79/vpype) (MIT), [rectpack](https://github.com/secnot/rectpack) (Apache-2.0). |
| Временная среда | `tools/inkscape/runtime.py` создаёт TemporaryDirectory в `.cache/graphics`, передаёт отдельные TEMP/TMP и INKSCAPE_PROFILE_DIR; установка дополнительного графического компонента для него не требуется. |

Для сопровождения тестов, если это отдельно требуется: трассировка использует lxml, NumPy, Pillow и SciPy; компоновка дополнительно PyMuPDF; `geometry-check.py` — ezdxf и Shapely. `verify_saved.py` и `validate(data)` используют стандартный Python. Тесты не являются обязательной частью подготовки обычной графической задачи.
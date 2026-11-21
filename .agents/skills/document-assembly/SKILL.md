---
name: document-assembly
description: Собрать готовую SVG-схему и карту цветов в редактируемый лист с заголовком, образцами и легендой. Использовать для компоновки готовых компонентов; не для векторизации, нумерации новых зон или физической раскладки тайлов.
---

# Сборка художественного листа

Нужны готовый SVG с viewBox, palette_map.json с colors и явными zones, layout.json и пути выходов. Осмотри исходник и сохрани его неизменным. Это A→P: размер страницы и fit в рамку не определяют размер изделия.

Исполнитель — существующий [package_coloring.py](../../../tools/coloring/package_coloring.py), параметризованный в v4.1; lxml собирает XML, настоящий Inkscape измеряет текст и экспортирует. JSON harness не импортирует исходную схему, clipboard/GUI не используются. Пределы — [матрица](../../../docs/agent/capability-matrix.md).

```powershell
& '.\.venv-graphics\Scripts\python.exe' 'tools\coloring\package_coloring.py' --artwork $inputSvg --palette $paletteFile --layout $layoutFile --out-svg $outputSvg --out-png $outputPng
```

Пути — параметры задания. Layout начни с [layout.example.json](../../../tools/coloring/layout.example.json); schema — [layout.schema.json](../../../tools/coloring/layout.schema.json). Обязательны page width/height/unit=px/margin, artwork_panel x/y/width/height, legend x/y/width/height/columns/swatch_size/font_size/font_family/gap. Единицы — page px; scale contain сохраняет пропорции. title и notes необязательны. `--title`, `--cols`, `--swatch-size` переопределяют config. `--export-width` влияет только на PNG (default 1600). `--out-pdf` создаёт presentation PDF. Физический print profile и tiles-manifest пока отклоняются; B→P 1:1 UNPROVEN.

Палитра: colors HEX→номер, zones zone_id/color_id/color/number, необязательные labels HEX→название. Раздельные зоны одного цвета сохраняются. Missing IDs, неверные номера, дубликаты, пересечение панелей и выход за поля — ошибка с ненулевым exit; выходы создаются после успешного измерения/render. Легенда переносится в дополнительные листы с суффиксом -p2 и далее. Assembly manifest содержит mapping и page list.

Импорт сохраняет source IDs, геометрию, локальные defs, clip/mask, group transforms, inline/inherited styles. Сгенерированные ID выбираются без коллизий. Stylesheet style, filters, raster image, script/active content и внешние ресурсы отклоняются с UNSUPPORTED_SVG_FEATURE: требуется предварительная нормализация. Шрифт указывается в layout; пригодность выбранного шрифта/кириллицы проверь на итоговом preview. Файловая запись и нулевой exit не заменяют осмотр листа.

Передай SVG всех страниц, preview/export и .manifest.json. Осмотри конечные страницы: вся палитра и подписи читаемы, легенда не перекрывает artwork, ничего не обрезано. При изменении компоновщика выполняй tests/assembly/verify_v4_2.py: A4, три цвета, PDF и неверный вход. Обычный принятый маршрут не требует повторного help/discovery или QA каждой внутренней команды. Временная среда очищается runtime.py.

Старый позиционный directory-вызов намеренно заменён явными параметрами: прежний код содержал имя/размеры единственной работы. Для миграции укажи её structural_layout.svg и palette_map.json, новый layout и новые выходы. Историческая приёмка содержала пример прежней работы; исходник не перезаписывается.

## Пригодность профиля и fallback

Версия 1.0 принимает page units px, contain без деформации и overflow=new_page. Поля document_kind/физические mm из примера брифа не являются скрытыми alias этого CLI. Для листа A4 в презентационном профиле задай page width=210*96/25.4 и height=297*96/25.4: это размер бумаги через 96 page units на дюйм, без назначения физического масштаба исходному artwork. Производственные tiles-manifest и physical_1_to_1 требуют отдельного ещё не принятого B→P маршрута.

При неизвестной SVG-конструкции используй подтверждённую нормализацию либо квалифицированный отказ; при LAYOUT_OVERFLOW увеличь панель/число листов или явно измени типографику. Шрифты в manifest — запрошенные имена, renderer может подставить системный шрифт; наличие кириллицы и внешний вид проверяются на конечном preview. В принятом fixture проверен DejaVu Sans. Отсутствие нужного шрифта не разрешает молча обещать идентичный вид на другой машине.

Презентационный PDF создаётся настоящим native exporter. Если PDF заказан, осмотри сохранённый PDF независимым reader/render; соответствие бумаге не доказывает 1:1 изделия. Для многостраничной легенды CLI выдаёт отдельные page SVG/PNG/PDF и полный список в manifest; объединённый многостраничный PDF не заявлен. Повторная запись неизменного годного листа допустима; новый тест идемпотентности нужен при изменении overwrite/export контракта.

Адресный новый A4/три цвета/PDF/invalid-input набор — tests/assembly/verify_v4_2.py --out <каталог artifacts>. Сложная легенда, другой viewBox и предыдущая реальная работа проверялись при исходной приёмке v4.1; данный набор их не покрывает. В обычном задании эти наборы повторно не запускаются.

# Project Brief — `vector-svg-to-numbered-contours`

**Версия:** 4.2 · **Дата:** 11.11.2026  
**Тип:** самостоятельное задание на альтернативный project Domain Skill  
**Проект:** `C:\gitCreative\solo-learn-mosaic` · **Приоритет:** адаптация существующего `paintbynumbersgenerator` с повторным использованием downstream-алгоритмов.

**Режим проверок:** штатный вызов уже подтверждённого маршрута не сопровождается повторным `--help`, discovery, хешированием промежуточных файлов, DOM-diff после каждой команды или независимым рендером каждой стадии. Тестовые fixtures ниже предназначены для **однократной приёмки нового/изменённого навыка** и адресной регрессии после изменения его контракта. В обычном задании выполняется минимальная проверка конечного результата; промежуточная диагностика — при неизвестном интерфейсе, наблюдаемом сбое или реальном риске потери геометрии/масштаба. Не создавать подробный QA-log при штатном успешном исполнении.

## 1. Назначение, входной профиль, альтернативность

Сформировать контурную схему с **номерами цветов** непосредственно из уже готового цветного SVG, сохранив художественные области и их локальные координаты. Для реализации приоритетно адаптировать проверенную ветвь `paintbynumbersgenerator` (оригинал `drakarah/paintbynumbersgenerator` или технически подходящий форк) через новый **векторный вход после raster segmentation**, повторно используя применимые downstream процедуры определения контуров, расположения меток, палитры и экспорта.

Это альтернатива `inkscape-cli-mosaic-labeler`, а **не** обязательная стадия после него. Одну и ту же схему нельзя пропускать через два labelers последовательно. Этот skill не распознаёт фотомозаику, не разрезает форму на физические плитки, не создаёт затирку, не масштабирует под печать и не компонует готовый лист с легендой.

## 2. I/O и инварианты

**Вход:** `artwork_regions.svg`, цветной `vtracer_output.svg` либо эквивалентный SVG с замкнутыми видимыми областями, palette metadata/manifest при наличии; optional `palette_map.json`, `preserve_geometry` (default), policies for tiny zones `keep/merge/flag`, local text and stroke settings in SVG user units/relative size. Вход считается художественной геометрией (домен A) даже если SVG имеет `width/height` с печатными единицами — физические размеры не используются без отдельного print job.

**Выходы:**

- `structural_layout.svg`: редактируемые контурные области, зоны с прежними IDs/геометрией, отдельный слой numbered labels/callouts; цветовой fill может быть отключён в итоговой схеме, но палитра остаётся в данных.
- `palette_map.json`: стабильное отображение `color_id/palette_id → number/color sample/display text`, не зависящее от порядка traversal DOM.
- `qa_summary.json`: количественная проверка областей, geometry diffs и непомещающихся меток, ошибки/ambiguities, provenance, статус.
- `preview_overlay.png`: визуальный overlay между исходными границами и итоговыми контурами/метками.

Дополнительный `mosaic_final_contour_scheme.pdf` — только при самостоятельном print profile/заказе, с явным A→P mapping, а не скрытым «1:1». Разделённые области одного цвета получают один номер палитры, но остаются разными геометрическими зонами. `zone_id` не равен `tile_id`.

## 3. Стратегия адаптации и выбор исходного движка

**Preflight:** проверить фактическую работу/версию установленного Codex, Node runtime, существующие project skills, `AGENTS.md`, capability matrix, местные форки, лицензии и текущий `package.json`/lock. Не менять глобальные `node_modules` и пользовательский runtime без разрешения. Выбрать reproducible fork/base commit только после испытания действующего raster-mode и анализа внутреннего pipeline.

**Разобрать реальный код до изменения:** вход raster, faceting/segmentation, внутренние модели (`Facet`, `FacetResult` или фактически используемые в этой версии), построение границ/соседей, palette/color index, поиск позиций меток, SVG renderer и CLI argument parsing. Имена `FacetBorderTracer`, `FacetBorderSegmenter`, `FacetLabelPlacer` — гипотезы для поиска в исходниках, а не гарантированное API. Особое внимание: какие downstream steps требуют `facetMap`/pixel grid и какие принимают многоугольники/кольца. Составить схему real functions → required data → preserved/adapted components.

**Решение о переиспользовании:** адаптер должен заменить только необходимые входные структуры. Если BorderTracer принципиально raster-specific, допустимо построить **векторное представление совместимых border-segments, rings и adjacency**, не переписывая полезные downstream placement/export. Если действительный upstream не допускает разумной адаптации, обоснованно сравнить с альтернативным `inkscape-cli-mosaic-labeler` и явно остановиться/изменить маршрут; нельзя назвать совершенно новый labeler «адаптацией».

Публичная команда и флаги нового SVG-mode **не существуют**, пока не реализованы и не проверены. Создать явный, видимый в `--help` project CLI interface (имя по текущему CLI), например концептуально `--input-svg`, `--palette`, `--preserve-geometry`, `--output`, но точный синтаксис определяется после просмотра исходников. Старый raster-mode обязан продолжать работать.

## 4. Контракт SVG input adapter

1. Поддерживаемые SVG features: `path`, `rect`/basic shapes, nested `transform`, group style inheritance, `viewBox`, fill opacity, `fill-rule`, complex holes and closed paths. Неподдержанные `use`/CSS gradients/filters/masks/clips — нормализовать существующим проверенным инструментом либо диагностировать до любой порчи геометрии.
2. Использовать существующие parser/geometry libraries, не писать собственный парсер данных `d`/Bezier. Учитывать фактические **видимые** области, а не только XML порядок/статический fill: перекрытия, clipPath, transparent paths и z-order изменяют картину.
3. Сформировать единую внутреннюю модель `zone_id`, кольца/отверстия, цвет/palette_id, adjacency/segment relations, source transform; сохранить точность координат в пределах явного tolerance. Раскрывать transform только контролируемым преобразованием.
4. Сохранить geometry в `preserve_geometry`; отдельный explicit `simplify/merge` меняет её только по заданным порогам и с журналом изменения площади/соседства. Пиксельная растеризация и повторная сегментация **не являются** допустимым дефолтным обходом SVG-adapter.
5. Разные disjoint zones идентичного цвета не сливать по palette_id. Палитра и labels deterministic при одинаковом источнике и config.
6. Label placement должен оставаться строго внутри видимой области (или иметь явную выноску): centroid не достаточен для вогнутой формы; учитывать holes и размер текста/стиля.

## 5. Инструментальные зависимости и границы `cli-anything`

По данным текущей проектной постановки распространённая локальная реализация `cli-anything-inkscape` принимает **собственный JSON**, а не произвольный существующий SVG. Нельзя использовать её для SVG input adaptation, обработки уже полученных цветных SVG или считать её автором native Inkscape path actions. Для самостоятельных операций над SVG использовать проверенный прямой Inkscape CLI, Node SVG parser либо проектный SVG runner. Tool Skill для GIMP не нужен в основном SVG-пути; headless render/QA выполняет фактический renderer, который должен иметь собственный verified invocation.

В route map `vector-svg-to-numbered-contours` публиковать только если реальный SVG-mode прошёл fixture tests. Если adapter отсутствует, status `UNIMPLEMENTED/UNPROVEN`, а не сымитированная интеграция существующего raster CLI. В capability matrix раздельно фиксировать source upstream, адаптированный module entry, upstream preserved functions, project code и tested input/output. Skill обязан честно отличать adapted upstream engine от написанного сейчас SVG input adapter.

## 6. Создание/актуализация SKILL.md

Путь `.agents/skills/vector-svg-to-numbered-contours/SKILL.md`, валидное frontmatter `name`/`description`. Положительный trigger: *colored SVG to numbered contours, vector paint-by-number, facet labels from SVG*. Отрицательный: source photo/sketch segmentation, physical tessellation, page assembly.

Workflow: read source → select known compatible adapter → acquire/reuse stable palette → run SVG-mode → assess finished contours and labels → produce `structural_layout.svg`/palette/preview → targeted replan only on failure. `--help` и CLI preflight повторять лишь при изменении интерфейса. SKILL.md должен называть **реальный**, проверенный project entry point и ограниченные данные в capability matrix. Не копировать полный upstream source в инструкцию.

Не делать массовые изменения `AGENTS.md`: достаточно маршрута «цветной SVG → выбрать один из двух labelers». В новых сессиях Codex может выбирать alternative tool по доказанным критериями качества/совместимости; не заставлять каждый раз запускать оба движка.

## 7. Приёмочные испытания

| Fixture | Проверка |
|---|---|
| V1 — 3 цвета и разные несмежные зоны одного цвета | Количество зон, стабильный единый palette number, отсутствие скрытого merge |
| V2 — общая граница с кривой Безье | Нет сдвоенного бордера, форма сохранена, editable paths |
| V3 — вогнутая область с отверстием | Номер внутри видимого материала, не в hole и не вне фигуры |
| V4 — малая область/узкий коридор | Callout или корректное warning, не пропавший цвет/метка |
| V5 — group transform/CSS/opacity | Правильные видимые зоны, цвет и координаты |
| V6 — настоящий многообъектный VTracer SVG | Реальный SVG input без обязательной raster resegmentation, масштабируемость и полнота labels |
| V7 — оригинальный raster input upstream | Regression: прежняя команда даёт сохранённый результат |
| V8 — invalid/unsupported SVG | Диагностический отказ, источник не испорчен |

**Приёмка новой SVG-адаптации:** на ограниченных fixtures проверить сохранность зон/палитры, корректное положение меток и итоговый preview; compatibility с реально используемым raster-mode — одним регрессионным примером. `--help` и backend trace нужны при создании интерфейса, но не в каждой пользовательской задаче. Хеш не является критерием качества. Требование физической страницы возникает только при отдельном print job и контролируется B/P, не данным skill.

**Поведенческий тест при изменении маршрута:** в общей новой сессии главного Codex естественное задание «из готового цветного SVG сделать контуры с номерами» приводит к реальному выбору и вызову подходящего уже принятого labeler, а не к JSON-only harness и не к новому самописному движку. Если предметный вариант не реализован, честный fallback на альтернативу допустим и должен быть отражён в trace.

## 8. Этапы и поставка

**Stage 1:** inventory и лицензии upstream. **Stage 2:** trace реально используемых алгоритмов и proof-of-adapter. **Stage 3:** минимальный SVG input + real CLI с тестом V1/V2. **Stage 4:** опорные сложные SVG semantics и palette/labels (V3–V6). **Stage 5:** raster regression V7, negative V8, visual QA. **Stage 6:** skill integration и new-session test. **Stage 7:** scoped diff, capability matrix, docs и report. При failing gate устранить причину до перехода.

Выход: действительный project skill, reproducible fork/patch с лицензиями и pin, проверенный CLI + tests, SVG/manifest/QA, evidence включения в главном Codex. Запрещён подменяющий результат — новый Python labeler под старым именем.

## 9. Источники

`https://github.com/drakarah/paintbynumbersgenerator`, `https://github.com/BenjaminSymons/paintbynumbersgenerator`, `https://learn.chatgpt.com/docs/build-skills`, `https://wiki.inkscape.org/wiki/Using_the_Command_Line`; реальные локальные docs/agent/capability-matrix и контракты.

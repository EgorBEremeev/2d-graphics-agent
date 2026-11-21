# Контракты графических данных

Формат и домен независимы: SVG может содержать artwork (A), изделие (B) или страницу (P). PDF сам по себе не доказывает масштаб.

| Домен | Координаты и инварианты | Допустимый переход |
|---|---|---|
| A — artwork | image/viewBox, замкнутые видимые зоны, holes/fill-rule, transforms, zone_id и color_id | A→A: векторизация/нумерация; A→P: лист; A→B: только явные физические параметры |
| B — изделие | mm, tile_id отдельно от zone_id, реальные швы/подрезки/andamento | B→P по отдельному print profile |
| P — документ | page units, page bounds, boxes, легенда и source→destination matrix | Экспорт/печать; 1:1 только по проверенному print profile |

Несмежные зоны одного цвета сохраняют разные zone_id. Нумерация сохраняет форму, transforms и viewBox, назначая стабильный номер цвету; произвольное слияние зон запрещено. Неподдержанные SVG-конструкции нормализуются проверенным средством или отклоняются с ID объекта. IDs и ссылки внутри defs/CSS/clip/mask не должны сталкиваться при компоновке.

## Манифесты и совместимость

Новый общий envelope: `schema_version: "1.0"`, `source` (путь/происхождение), `coordinate_domain: "A"|"B"|"P"`, `viewBox` либо extent, `objects` (ID и mapping), `provenance` (producer/version), `parameters`, `warnings`, `qa_ref`. При нескольких входах source — список. Пример P:

```json
{"schema_version":"1.0","source":["scheme.svg","palette.json"],"coordinate_domain":"P","viewBox":[0,0,1000,800],"objects":[{"id":"artwork","source_viewBox":[10,20,100,50],"matrix":[8,0,0,8,-30,-110]}],"provenance":{"producer":"tools/coloring/package_coloring.py","version":"1.0"},"parameters":{"layout":"layout.json"},"warnings":[],"qa_ref":"qa_summary.json"}
```

Принятый artwork_regions.manifest.json остаётся совместим: `domain: artwork` — alias A, `zones` — предметный objects, `artwork_to_image` — affine [a,b,c,d,e,f], `image_size`, `line_role`, `palette`, `source`, `qa_ref`. Legacy без schema_version читается как v0; новые writers добавляют envelope без удаления прежних полей. Palette допускается как HEX→color_id map или список color_id/fill. Компоненты и отверстия определяются геометрией, не совпадением цвета.

Принятый palette_map.json: `colors: {"#rrggbb": positive_integer}`, `zones: [{zone_id,color_id,color,number,source_ids}]`. Номера уникальны по цветам; каждая зона ссылается на существующий цвет и его номер. Пустая/противоречивая карта — ошибка. Расширение зоны полями не меняет старые поля. Отсутствующие стабильные связи не восстанавливаются по позиции в массиве.

B пока NOT_APPLICABLE: готового генератора тайлов в поставке нет. Его будущий контракт обязан содержать units=mm, artwork_to_manufacturing, tile_id, zone_id, color_id, geometry и seam parameters. Это требование, не доказательство реализации.

## Компоновка

layout.json version 1.0 задаёт page width/height, margin, artwork box, legend box, шрифт/колонки/параметры текста. Единицы обычного листа — page units; source viewBox отображается uniform affine с сохранением пропорций в destination box. Изменение исходных contour/zone_id не требуется. SVG импортируется как изолированный вложенный документ с пространством ID. Неподдержанный импорт отклоняется явно. Print profile задаётся отдельно; обычный лист не является натуральной величиной изделия.

Проверка envelope и совместимого legacy A: функция `validate(data)` в `tests/agent/validate_contracts.py`, используемая проверками соответствующих модулей. Приёмка использует два сохранённых P-результата (обычный и многолистный) и реальный legacy A; отсутствие новых полей в v0 не переименовывается в соответствие v1. Новые writers должны добавлять envelope при изменении своего интерфейса; старые принятые outputs сохраняются.

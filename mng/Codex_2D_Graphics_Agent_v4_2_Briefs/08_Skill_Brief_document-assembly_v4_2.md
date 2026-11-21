# Project Brief — `document-assembly`

**Версия:** 4.2 · **Дата:** 11.11.2026  
**Тип:** самостоятельное задание на новый project Domain Skill и узкий CLI-компоновщик  
**Проект:** `C:\gitCreative\solo-learn-mosaic` · **Существующая точка кандидата:** `tools/coloring/package_coloring.py` (проверить наличие и контракт).  
**Режим:** headless/API, без предположений о GUI clipboard и без интерактивного редактора.

**Режим проверок:** штатный вызов уже подтверждённого маршрута не сопровождается повторным `--help`, discovery, хешированием промежуточных файлов, DOM-diff после каждой команды или независимым рендером каждой стадии. Тестовые fixtures ниже предназначены для **однократной приёмки нового/изменённого навыка** и адресной регрессии после изменения его контракта. В обычном задании выполняется минимальная проверка конечного результата; промежуточная диагностика — при неизвестном интерфейсе, наблюдаемом сбое или реальном риске потери геометрии/масштаба. Не создавать подробный QA-log при штатном успешном исполнении.

## 1. Предмет, результат, ограничения

Создать воспроизводимую компетенцию **сборки итоговых графических листов из уже готовых компонентов**: artwork/контурная схема, таблица палитры, заголовки, пояснения, подписи, легенда, при необходимости технологические таблицы/выписки из manifest, вывод SVG и PNG/PDF. Компоновщик занимается **Document Assembly**, а не восстановлением рисунка, созданием новых художественных зон, нумерацией пустого SVG или физическим размещением тайлов.

Skill должен использовать существующие capabilities/проектные средства. При отсутствии штатной headless операции объединения рисунка и легенды допускается небольшая параметризованная проектная утилита на основе доступного SVG/XML parser и реального renderer; она должна выполнять именно сборку, а не становиться универсальным графическим редактором.

**Ключевая дисциплина:** художественная геометрия A, физическая геометрия изделия B и координаты презентационной страницы P — разные пространства. A→P означает масштабирование художественного изображения **в рамку листа**, не назначение размера будущей плитки. B→P для технологического листа может требовать строго 1:1, при этом необходимо контролировать физический масштаб отдельно от расположения легенды и полей.

## 2. Контракт входа и требований к layout

**Обязательные источники:**

- `--artwork FILE`: принятая редактируемая SVG схема, например `structural_layout.svg` или `final_layout.svg`; source read-only, с уникальными `zone_id` и, при B, `tile_id`.
- `--palette FILE`: `palette_map.json` с детерминированным отображением `color_id/palette_id → palette number, fill/swatch, label`.
- `--layout FILE`: `layout.json` либо аналогичный config, задающий schema version, тип документа, страницы, поля, панели, последовательность секций, ширину/высоту/отступы, правила изменения масштаба, типографику и доступный режим fallback.
- `--out-svg FILE`: финальная редактируемая векторная композиция.

**Необязательные:** `--tiles-manifest FILE` для B, `--out-png`, `--out-pdf`, `--title`, `--cols`, `--swatch-size`, `--export-width`. Не требовать `tiles_manifest` для чисто художественного листа. Не восстанавливать палитру «из номера DOM index», если она задана явно. Прежде чем выводить документ, валидировать согласованность всех referenced IDs.

**Семантика конфигурации:**

```json
{
  "schema_version": "1.0",
  "document_kind": "artwork_sheet",
  "page": {"width": 210, "height": 297, "unit": "mm", "margin": 10},
  "artwork_panel": {"x": 10, "y": 10, "width": 190, "height": 220, "fit": "contain", "allow_distortion": false},
  "legend": {"columns": 2, "swatch_size": 6, "font_size": 9, "overflow": "new_page"},
  "print_profile": {"scale_mode": "presentation", "physical_1_to_1": false}
}
```

Это **пример целевой семантики schema**, а не объявление уже существующего интерфейса. Исполнитель вправе адаптировать названия полей к реально принятому CLI, но обязан предоставить **явную versioned schema**, documented units и валидатор. В примере `page` задан физическим форматом бумаги, но `artwork_panel` — *компоновочное пространство листа*, не физическое изделие. В профиле `document_kind: manufacturing_sheet` `physical_1_to_1: true` разрешён только при наличии B-данных с известными mm и проверяемой шкалой.

**Выходы:** `assembled_sheet.svg` (или явное `--out-svg` имя), опциональные `assembled_preview.png`, `assembled_sheet.pdf`; `assembly_manifest.json` с provenance, page sizes, mapping matrices, sections, output assets, fonts; source hash и QA refs — при явно заданной потребности в целостности/диагностике. `qa_summary.json` — при приёмке реализации или если того требует принятый downstream контракт, не по каждому штатному вызову. Обязательный выход редактируемый; PNG без SVG не удовлетворяет контракту.

## 3. Карта операций и алгоритм сборки

1. **Input Gate:** проверить существование файлов, SVG parse, root `viewBox`, целостность палитры и manifest references, font availability, разрешённые пути, отсутствие XML внешних сущностей/недоверенных remote resources. Вредоносные/неподдержанные SVG active content, скрипты и внешние ссылки не исполнять в компоновщике.
2. **Document Plan:** по конфигу вычислить box model страницы, artwork panel, legend region, экспликации и page breaks. Для сложной легенды допускаются 2+ страниц; данные не обрезать ради одной страницы.
3. **Import Artwork:** внедрить исходный SVG в отдельную группу со стабильным ID и явно рассчитанной матрицей `source viewBox → destination panel`. Пропорции по умолчанию сохраняются (`contain`); деформация возможна только при `allow_distortion=true` с предупреждением и измеренным результатом. Не менять source geometry, порядок и zone IDs.
4. **Resolve Namespaces:** исключить collisions исходных `id`, `defs`, `clipPaths`, patterns, paint servers, filters, `url(#...)`, CSS selectors/inline styles между artwork и документными секциями; применить проверенную библиотечную нормализацию либо завершить с информативным `UNSUPPORTED_SVG_FEATURE`. SVG с nested transforms и стилями наследования обязан проверяться рендером.
5. **Compose Legend:** строить по принятой стабильной palette map, с сохранением номера/цвета/названия и соответствия art; поддержать кириллицу, длинные подписи, пустые optional notes, повторяющиеся цвета, полупрозрачность (если допустима). Текстовые размеры проверять реальным renderer/query либо поддающимся проверке typography engine; фиксированные «магические» координаты недопустимы.
6. **Pagination:** layout engine должен рассчитать пересечения artwork, legend, headers/footers, page bounds, margin и overflow. При длинной таблице — использовать page break, уменьшение/переразмещение по явному правилу или report `LAYOUT_OVERFLOW`, а не невидимые обрезки. В многостраничном SVG profile при невозможности достоверного PDF экспорта по страницам применять отдельные page SVG с manifest.
7. **Render/Export:** финальный SVG открыть независимым headless renderer (например, реально проверенным Inkscape CLI); при запросе создать PNG/PDF, убедиться в реальном наличии и корректном содержании. Код выхода `0` не заменяет проверку наличия конечного SVG/экспорта; на штатных промежуточных операциях отдельный Outcome Gate не выполняется.
8. **Final Check:** на итоговом листе оценить сохранность художественной композиции, полноту палитры/подписей и отсутствие видимой обрезки. Углублённое сравнение геометрии и SVG DOM — при изменении импорта или признаках потери объектов; PDF boxes, размеры и scale — для реально заказанного B→P/print 1:1. Презентационный A→P лист не выдавать за производственную схему.

**Ни один пункт не выполняется через headless `copy`/`paste-in-place`, если локальный action возвращает успех без подтверждённого изменения.** Не уходить в GUI автоматически: заменить маршрут native SVG assembly/runner либо остановиться с диагностикой.

## 4. Ограниченный рефакторинг `package_coloring.py`

1. Инвентаризировать фактический файл и потребителей/тесты; установить, какие параметры уже есть, какие действия жёстко связаны с конкретным рисунком и какой старый output действительно должен сохраняться. Не изменять файл, которого не существует, под ложным видом «рефакторинга»: если отсутствует, зафиксировать `ABSENT` и принять новый допустимый location.
2. Предложить CLI surface с явными параметрами: `--artwork`, `--palette`, `--layout`, `[--tiles-manifest]`, `--out-svg`, `[--out-png]`, `[--out-pdf]`, `[--title]`, `[--cols]`, `[--swatch-size]`, `[--export-width]`. Обязательные признаки `--help`, sensible exit codes, data validation и readable failures. Допустимые имена выходов всегда задаёт job/output profile.
3. Нейтральные defaults (например, `fit=contain`) допускаются, **предметные** defaults (название конкретного рисунка, его палитра, координаты легенды, абсолютный путь к ранее выполненному job) запрещены. Конкретный legacy case поддерживать через явный fixture/profile, не через невидимый fallback.
4. Крупные собственные реализации SVG parser, font renderer, path editor, clipper, PDF engine **не писать**: использовать проверенные существующие библиотеки и реальный renderer. Новый код покрывает arrangement/mapping/validation/CLI. В отчёте указать upstream libraries и вновь созданный orchestration code.
5. При сохранении старых вызовов тестировать именно действующие клиентские сценарии; если они требуют специальных legacy params — описать адаптацию/миграцию, не обещать бинарную совместимость, которая не проверена.
6. Повторный запуск с одними входами и конфигом может выдавать идентичный SVG: это допустимая идемпотентность. Изменившийся hash не доказывает правильную легенду. Повторный прогон нужен при приёмке изменённой логики сохранения, а не в каждой задаче.

## 5. Требования к Agent Skill

Создать `.agents/skills/document-assembly/SKILL.md` с frontmatter `name: document-assembly` и описанием, которое выбирается для *assemble vector artwork with palette legend, compose mosaic sheet, technical sheet packaging, SVG-to-document page layout*. Явно исключить *sketch/photo segmentation, SVG labels generation, physical tile placement*. Это Domain Skill; он может использовать проверенный tool CLI/runner, но не подменяет его собой.

Внутри skill — воспроизводимый цикл `validate ready source → classify A→P / B→P → choose layout profile → invoke package CLI → inspect finished sheet → export → report`. Дополнительный geometry/page QA включать при print 1:1 либо наблюдаемом дефекте; не проверять все DOM-модификации каждого промежуточного шага. Конкретные bin/versions/fallback определяются capability matrix, не навязываются developer-инструкциям. `AGENTS.md` должен лишь маршрутизировать задачи по class Document Assembly, без полного алгоритма.

**Проверить реальный trigger:** новая независимая Codex-сессия получает без имён skills: «Есть готовый контурный рисунок и карта цветов. Собери итоговый лист с образцами цветов, заголовком и легендой». Ожидается selection document-assembly, вызов CLI, absence of interactive GUI, правильный SVG и QA; написание одноразового скрипта под один рисунок при наличии компоновщика — FAIL.

## 6. Acceptance fixtures и outcome

| Fixture | Вход | Измеряемые требования |
|---|---|---|
| A1 — малая палитра | простой SVG, 3 цвета, A4 художественный layout | нет пропавших номеров, все подписи, source outlines unchanged, valid SVG/PNG |
| A2 — сложная палитра | много зон, длинные названия, кириллица, 2+ колонки | отсутствие перекрытий, корректные шрифты и line wrap/page break |
| A3 — другой artwork | другой aspect ratio и `viewBox`, nested styles/defs/transforms | reuse без правки исходного кода, корректное A→P mapping, отсутствие ID collisions |
| A4 — invalid mapping | отсутствующий color_id, malformed layout, дубликат ID | контролируемая ошибка, no corrupted output/source |
| A5 — повторный запуск | те же входы, конфиг и outputs | `UNCHANGED_VALID` либо deterministic valid render; никакого ложного `NO_OP` |
| A6 — headless clipboard action | вызов, возвращающий exit 0 без вставки, если воспроизводим | `NO_OP_UNEXPECTED`, route fallback на project assembler без GUI |
| A7 — manufacturing profile | физическое `final_layout.svg` + `tiles_manifest` с mm | B→P, измеренный 1:1 scale, PDF boxes, отсутствие fit-to-page |
| A8 — previous accepted job | реальный прежний fixture вызов | подтверждённая совместимость либо явный tested legacy profile/migration |

**Приёмка новой реализации:** два разных позитивных художественных input (разные viewBox/сложность легенды) и один негативный mapping-case; использовать реально принятый прежний job для проверки совместимости. Один финальный SVG/preview на каждый fixture и целевые проверки текстовых границ/палитры. Повторный запуск — только при изменении idempotence/overwrite contract; физический print profile — только если B→P входит в изменённую реализацию. Массовые хеши, DOM-diff между всеми стадиями и повторные рендеры не требуются. Поле `--export-width` изменяет только DPI/pixel dimensions preview; не должно менять художественную геометрию.

**PASS** — настоящее работающее CLI, перечисленные результаты и evidence; **FAIL** — hardcoded job values, clipped legend, потеря source, no-op с exit 0 принят за успех, неверный 1:1 print; **UNPROVEN** — неизмеренный вывод; **BLOCKED** — объективная недоступность данных/прав/renderer.

## 7. Этапы и состав поставки

**Stage 1 — Inventory:** код, проекты вызова, capabilities, versions, sources; **Gate:** понятны фактические входы и долговременные use cases.  
**Stage 2 — Interface/schema:** CLI + versioned layout schema, пример A→P; **Gate:** определены единицы и ошибки, нет скрытых job values.  
**Stage 3 — Minimal assembler:** separate artwork group, legend+palette, export; **Gate:** A1/A3.  
**Stage 4 — Typography/pagination:** A2/A4 и независимый preview; **Gate:** нет clipping/коллизий.  
**Stage 5 — Regression/fallback:** реально затронутые A5/A6/A8, optional B→P A7; **Gate:** результат работы и честная совместимость, не обязательный per-operation Outcome Gate.  
**Stage 6 — Skill integration:** валидный SKILL.md, Codex trigger, новая независимая сессия; **Gate:** behavioral evidence.  
**Stage 7 — Final:** docs/CLI help/config, scoped diff, обновлённые только подтверждённые registry entries, immutable sources, tests и report.

**Артефакты:** проектный CLI `tools/coloring/package_coloring.py` либо существующий доказанный эквивалент, layout schema/example, `.agents/skills/document-assembly/SKILL.md`, fixtures/QA, восстановление dependences и точное заключение о поддержке A→P и B→P. Не включать в поставку новую полную систему рендеринга или editor GUI.

## 8. Проверяемые источники

Действительные локальные `docs/agent/capability-matrix.md`, `docs/agent/graphics-data-contracts.md`, реальные CLI `--help`/action list, документация проверенного SVG parser/export; `https://wiki.inkscape.org/wiki/Using_the_Command_Line`, `https://learn.chatgpt.com/docs/build-skills`.

"""Приёмка контрактов на сохранённых результатах; не проверка графического вида."""
import copy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def validate(data):
    version = data.get('schema_version')
    if version is None and data.get('domain') == 'artwork':
        required = {'source', 'viewBox', 'image_size', 'artwork_to_image', 'zones', 'palette'}
        if not required <= data.keys():
            raise ValueError('Неполный legacy artwork contract')
        if len(data['artwork_to_image']) != 6:
            raise ValueError('Неверная affine matrix')
        objects, identity = data['zones'], 'zone_id'
        for zone in objects:
            if data['palette'].get(zone['fill']) != zone['color_id']:
                raise ValueError('Зона не соответствует палитре')
        mode = 'legacy-v0/A'
    else:
        required = {'schema_version', 'source', 'coordinate_domain', 'objects',
                    'provenance', 'parameters', 'warnings', 'qa_ref'}
        if not required <= data.keys() or version != '1.0':
            raise ValueError('Неполный envelope 1.0')
        if data['coordinate_domain'] not in {'A', 'B', 'P'}:
            raise ValueError('Неизвестный домен')
        if not {'producer', 'version'} <= data['provenance'].keys():
            raise ValueError('Отсутствует provenance')
        if not data['source'] or not data['qa_ref']:
            raise ValueError('Нет source/qa_ref')
        if not isinstance(data['warnings'], list):
            raise ValueError('warnings должен быть списком')
        objects, identity = data['objects'], 'id'
        mode = 'envelope-1.0/' + data['coordinate_domain']
    extent = data.get('viewBox', data.get('extent'))
    if not isinstance(extent, list) or len(extent) != 4 or extent[2] <= 0 or extent[3] <= 0:
        raise ValueError('Неверный extent/viewBox')
    ids = [obj[identity] for obj in objects]
    if not ids or len(ids) != len(set(ids)):
        raise ValueError('Пустые или повторяющиеся IDs')
    return mode



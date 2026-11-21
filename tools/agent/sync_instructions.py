"""Синхронизация канонических D/O без изменения остальных TOML-параметров."""
import argparse
from pathlib import Path
import re
import tomllib

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true', help='Обновить runtime-копии')
    args = parser.parse_args()
    config_path = ROOT / '.codex/config.toml'
    old = config_path.read_text(encoding='utf-8')
    config = tomllib.loads(old)
    developer = (ROOT / 'docs/agent/graphics-developer-instructions.md').read_text(encoding='utf-8')
    operations = (ROOT / 'docs/agent/graphics-model-behavior.md').read_text(encoding='utf-8')
    if args.write:
        if "'''" in developer:
            raise ValueError('Канонический текст содержит разделитель TOML')
        pattern = r"(?ms)^developer_instructions\s*=\s*'''\n.*?'''"
        updated, count = re.subn(pattern, lambda _: "developer_instructions = '''\n" + developer + "'''", old)
        if count != 1:
            raise ValueError('Ожидался один multiline literal developer_instructions')
        before = {k: v for k, v in config.items() if k != 'developer_instructions'}
        after = {k: v for k, v in tomllib.loads(updated).items() if k != 'developer_instructions'}
        if before != after:
            raise ValueError('Изменились посторонние TOML-настройки')
        config_path.write_text(updated, encoding='utf-8', newline='\n')
        (ROOT / 'AGENTS.md').write_text(operations, encoding='utf-8', newline='\n')
        config = tomllib.loads(updated)
    assert config['developer_instructions'] == developer, 'D расходится с runtime'
    assert (ROOT / 'AGENTS.md').read_text(encoding='utf-8') == operations, 'O расходится с runtime'
    assert 'model_instructions_file' not in config, 'Обнаружена подмена базовых инструкций'
    print('PASS: TOML, D/O sync; базовые инструкции сохранены')


if __name__ == '__main__':
    main()

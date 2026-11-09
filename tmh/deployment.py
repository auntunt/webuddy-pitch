"""External startup secrets and a read-only inventory of deployment configuration."""
import json
import os
from pathlib import Path


CONFIG_FILES = ('agents.json', 'agent-routes.json', 'autoflow.json',
                'project-tests.json', 'pricing.json', 'datasources.json', 'alerts.json')
SECRET_NAMES = ('TMH_TOKEN', 'TMH_FEISHU_APP_SECRET')


def check_config(data_dir):
    files = []
    for name in CONFIG_FILES:
        path = Path(data_dir) / name
        try:
            value = json.loads(path.read_text(encoding='utf-8'))
        except FileNotFoundError:
            files.append(dict(file=name, state='not_configured'))
        except json.JSONDecodeError as exc:
            bom = path.read_bytes()[:3] == b'\xef\xbb\xbf'
            files.append(dict(file=name, state='bom' if bom else 'invalid_json', line=exc.lineno, column=exc.colno))
        except (OSError, UnicodeError):
            files.append(dict(file=name, state='unreadable'))
        else:
            files.append(dict(file=name, state='valid_object' if isinstance(value, dict) else 'invalid_type'))
    return dict(ok=all(item['state'] in ('not_configured', 'valid_object') for item in files),
                check='json_syntax_and_top_level_type', files=files)


def strip_config_bom(data_dir):
    """Notepad and PowerShell 5 save UTF-8 with a BOM; every platform reader expects plain UTF-8."""
    fixed = []
    for name in CONFIG_FILES:
        path = Path(data_dir) / name
        if path.is_file() and path.read_bytes()[:3] == b'\xef\xbb\xbf':
            path.write_bytes(path.read_bytes()[3:])
            fixed.append(name)
    return fixed


def load_secrets(environment=None):
    """Load supported file-backed startup secrets without printing their values."""
    environment = os.environ if environment is None else environment
    for name in SECRET_NAMES:
        secret_file = environment.get(name + '_FILE')
        if not secret_file:
            continue
        if environment.get(name):
            raise SystemExit('Set only %s or %s_FILE' % (name, name))
        try:
            value = Path(secret_file).read_text(encoding='utf-8').rstrip('\r\n')
        except (OSError, UnicodeError):
            raise SystemExit('Cannot read %s_FILE' % name)
        if not value:
            raise SystemExit('%s_FILE is empty' % name)
        environment[name] = value
        del environment[name + '_FILE']

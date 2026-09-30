"""Application convenience state and exclusive creation of scenario packages."""

import json
import os
import shutil
import tempfile
from pathlib import Path

from . import schema
from .persistence import save_package


def create_package(name, destination):
    """Validate and stage a new package; never merge into an existing directory."""
    scenario = schema.scenario({'version': 1, 'name': name, 'mode': '実行', 'steps': []})
    registry = schema.elements({'version': 1, 'pages': {}})
    schema.validate_package(scenario, registry)
    destination = Path(destination).absolute()
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='.flowtape-new-', dir=destination.parent))
    reserved = False
    try:
        save_package(staging / 'scenario.yaml', scenario, registry)
        # Exclusive reservation also protects against another creator racing us.
        destination.mkdir()
        reserved = True
        for source in staging.iterdir():
            os.replace(source, destination / source.name)
        return destination / 'scenario.yaml'
    except BaseException:
        if reserved:
            shutil.rmtree(destination)
        raise
    finally:
        shutil.rmtree(staging)


class Preferences:
    """Private UI state, deliberately outside scenario/config schemas."""
    def __init__(self, path):
        self.path = Path(path)
        self.config_path = None
        self.recent = []
        self.error = None
        try:
            if self.path.exists():
                obj = json.loads(self.path.read_text(encoding='utf-8'))
                if not isinstance(obj, dict) or obj.get('version') != 1:
                    raise ValueError('invalid preferences version')
                config = obj.get('config_path')
                recent = obj.get('recent', [])
                if config is not None and not isinstance(config, str):
                    raise ValueError('invalid configuration preference')
                if not isinstance(recent, list) or any(not isinstance(p, str) for p in recent):
                    raise ValueError('invalid recent scenarios')
                self.config_path = config
                self.recent = list(dict.fromkeys(recent))[:10]
        except (OSError, ValueError, TypeError):
            self.error = 'アプリ設定を読み込めませんでした。設定とシナリオを選び直してください。'

    def save(self):
        temporary = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=self.path.parent,
                                             prefix='.preferences-', delete=False) as handle:
                temporary = Path(handle.name)
                json.dump({'version': 1, 'config_path': self.config_path, 'recent': self.recent},
                          handle, ensure_ascii=False)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
            self.error = None
        except OSError:
            self.error = 'アプリ設定を保存できませんでした。シナリオの保存には影響しません。'
        finally:
            if temporary is not None:
                try: temporary.unlink(missing_ok=True)
                except OSError: pass

    def remember(self, source):
        source = str(Path(source).resolve())
        self.recent = [source] + [p for p in self.recent if p != source]
        self.recent = self.recent[:10]
        self.save()

    def forget(self, source):
        self.recent = [p for p in self.recent if p != str(source)]
        self.save()

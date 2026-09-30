"""Validated single-file environment persistence; no scenario-local credentials."""

import copy
import os
import tempfile
from pathlib import Path

import yaml

from . import schema
from .errors import FlowTapeError
from .persistence import writer_lock


class EnvironmentStoreError(FlowTapeError):
    pass


def snapshot(path):
    source = Path(path)
    try: return source.read_bytes() if source.exists() else None
    except OSError:
        raise EnvironmentStoreError('ファイルを読み込めません。保存先と権限を確認してください。') from None


def atomic_yaml(path, document, expected):
    """Compare before replacing; stage with user-only permissions and no backups."""
    path = Path(path)
    temporary = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with writer_lock(path):
            if snapshot(path) != expected:
                raise EnvironmentStoreError('ファイルが外部で変更されました。再読込してから保存してください。')
            with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.flowtape-env-', delete=False) as handle:
                temporary = Path(handle.name)
            schema.save_yaml(temporary, document)
            with temporary.open('rb') as handle: os.fsync(handle.fileno())
            saved = temporary.read_bytes()
            os.replace(temporary, path)
            return saved
    except EnvironmentStoreError: raise
    except Exception:
        # Never include values, serialized YAML, or exception details in UI/logs.
        raise EnvironmentStoreError('ファイルを安全に保存できませんでした。元の内容は変更していません。') from None
    finally:
        if temporary is not None:
            try: temporary.unlink(missing_ok=True)
            except OSError: pass


def credential_reference(group, key):
    ref = '${credential.' + group + '.' + key + '}'
    schema.reference_syntax(ref, 'credential reference')
    if not schema.REFERENCE.fullmatch(ref) or schema.REFERENCE.fullmatch(ref).group(1) != 'credential.'+group+'.'+key:
        raise EnvironmentStoreError('参照に使用できないグループ名またはキーです。')
    return ref


class CredentialStore:
    def __init__(self, path):
        self.path = Path(path)
        self.reload()

    def reload(self):
        self.original = snapshot(self.path)
        try:
            self.document = schema.credentials(yaml.load(self.original.decode('utf-8'),Loader=schema.StrictLoader)) if self.original is not None else {'version':1,'credentials':{}}
        except Exception:
            raise EnvironmentStoreError('認証情報ファイルを読み込めません。形式と権限を確認してください。') from None
        return copy.deepcopy(self.document)

    @property
    def groups(self): return self.document['credentials']

    def save(self, trial):
        try: schema.credentials(trial)
        except Exception:
            raise EnvironmentStoreError('認証情報はグループ名・キーと文字列の値で指定してください。') from None
        saved = atomic_yaml(self.path, trial, self.original)
        self.document = copy.deepcopy(trial)
        self.original = saved

    def add(self, group, username, password):
        credential_reference(group, 'password')
        if group in self.groups:
            raise EnvironmentStoreError('同じ名前のグループが存在します。既存グループを選ぶか別名を指定してください。')
        trial = copy.deepcopy(self.document)
        trial['credentials'][group] = {'username':username, 'password':password}
        self.save(trial)

    def update(self, group, changes):
        if group not in self.groups: raise EnvironmentStoreError('グループが見つかりません。再読込してください。')
        trial = copy.deepcopy(self.document)
        trial['credentials'][group].update(changes)
        self.save(trial)

    def remove(self, group):
        if group not in self.groups: raise EnvironmentStoreError('グループが見つかりません。再読込してください。')
        trial = copy.deepcopy(self.document)
        del trial['credentials'][group]
        self.save(trial)
